"""Adaptador STT local con Vosk para audio PCM16 de 16 kHz."""

import asyncio
import json
import threading
import time
import re
from pathlib import Path

from vosk import KaldiRecognizer, Model

from backend.ai.contracts import (
    SpeechToTextConfigurationError,
    SpeechToTextFinalizationTimeout,
    VoiceEventPublisher,
)
from backend.logging.event_logger import log_event
from backend.ai.pcm_streaming_turn import PcmStreamingSpeechToText

_MODEL_CACHE: dict[str, Model] = {}
_MODEL_LOCK = threading.Lock()

_MENU_SPEECH_CORRECTIONS = {
    "debida": "bebida",
    "esprit": "Sprite",
    "espirit": "Sprite",
    "esperais": "Sprite",
    "esperáis": "Sprite",
    "esperaís": "Sprite",
    "espiral": "Sprite",
    "concurre": "QR",
    "q erre": "QR",
}


def _load_model(model_path: str) -> Model:
    """Carga una vez el modelo Vosk solicitado y lo conserva en memoria.

    Args:
        model_path: Directorio local que contiene los archivos descomprimidos del
            modelo Vosk.

    Returns:
        Modelo Vosk reutilizable por los turnos de voz posteriores.

    Raises:
        RuntimeError: Si falta la ruta, no es un directorio o Vosk no puede abrir
            el modelo local.

    Effects:
        Puede cargar el modelo en memoria durante la primera llamada para una ruta.
    """
    if not model_path:
        raise RuntimeError(
            "Falta VOSK_MODEL_PATH para usar Vosk. Descargá y descomprimí un "
            "modelo Vosk antes de seleccionarlo."
        )
    path = Path(model_path).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError(
            "VOSK_MODEL_PATH no apunta a un directorio de modelo Vosk válido."
        )
    cache_key = str(path)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(cache_key)
        if model is not None:
            return model
        try:
            model = Model(cache_key)
        except Exception as exc:
            raise RuntimeError(
                "Vosk no pudo abrir el modelo local configurado. Revisá "
                "VOSK_MODEL_PATH y que el modelo esté descomprimido."
            ) from exc
        _MODEL_CACHE[cache_key] = model
        return model


def _read_result(result: str, field: str) -> str:
    """Extrae de forma segura texto reconocido desde una respuesta JSON de Vosk.

    Args:
        result: JSON devuelto por Vosk para un parcial o segmento reconocido.
        field: Clave esperada, por ejemplo ``partial`` o ``text``.

    Returns:
        Texto reconocido sin espacios externos, o una cadena vacía si falta o la
        respuesta no tiene el formato esperado.
    """
    try:
        value = json.loads(result).get(field, "")
    except (TypeError, json.JSONDecodeError):
        return ""
    return value.strip() if isinstance(value, str) else ""


def _normalize_menu_vocabulary(text: str) -> str:
    """Corrige variantes frecuentes del STT para términos visibles del menú.

    La corrección se limita a variantes acústicas observadas de palabras del
    menú. No agrega productos, modificadores ni operaciones: el intérprete y
    ``OrderService`` continúan validando el pedido completo.

    Args:
        text: Hipótesis parcial o texto final producido por Vosk.

    Returns:
        Texto con equivalencias acotadas de vocabulario del menú.
    """
    normalized = text
    for spoken, canonical in _MENU_SPEECH_CORRECTIONS.items():
        normalized = re.sub(
            rf"\b{re.escape(spoken)}\b",
            canonical,
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


class VoskTranscriber(PcmStreamingSpeechToText):
    """Implementa SpeechToText local con Vosk y un modelo instalado por la persona usuaria."""

    provider_name = "vosk"

    def __init__(self, session_id: str | None, model_path: str) -> None:
        """Inicializa el turno sin cargar el modelo hasta que comience a transcribir.

        Args:
            session_id: Identificador de sesión utilizado para correlacionar logs.
            model_path: Directorio local del modelo Vosk seleccionado en .env.
        """
        super().__init__(
            session_id,
            queue_full_message=(
                "La transcripción local no procesa el audio a tiempo."
            ),
        )
        self.model_path = model_path

    async def transcribe(self, publish: VoiceEventPublisher) -> str:
        """Reconoce audio localmente, publica parciales y devuelve texto final.

        Args:
            publish: Callback asíncrono usado para disponibilidad y avances de voz.

        Returns:
            Texto final reconocido por Vosk después de recibir ``audio.stop``.

        Raises:
            RuntimeError: Si falta o no se puede abrir el modelo local de Vosk.
            SpeechToTextFinalizationTimeout: Si no se recibe el final del audio
                en el tiempo límite.
            ValueError: Si el turno finaliza sin texto reconocible.

        Effects:
            Carga el modelo una vez por ruta y procesa cada fragmento fuera del
            hilo asíncrono principal.
        """
        started_at = time.perf_counter()
        try:
            model = await asyncio.to_thread(_load_model, self.model_path)
        except RuntimeError as exc:
            raise SpeechToTextConfigurationError(
                "Vosk no pudo preparar el modelo local. Revisá VOSK_MODEL_PATH y "
                "que el modelo esté descargado y descomprimido."
            ) from exc
        recognizer = await asyncio.to_thread(KaldiRecognizer, model, 16000)
        final_parts: list[str] = []
        last_partial = ""
        await publish("voice.ready", {})
        log_event(
            "INFO",
            "voice.vosk_ready",
            session_id=self.session_id,
            model_path=str(Path(self.model_path).expanduser()),
        )
        try:
            while True:
                chunk = await asyncio.wait_for(self.chunks.get(), timeout=65)
                if chunk is None:
                    break
                accepted = await asyncio.to_thread(recognizer.AcceptWaveform, chunk)
                if accepted:
                    segment = _normalize_menu_vocabulary(
                        _read_result(await asyncio.to_thread(recognizer.Result), "text"),
                    )
                    if segment:
                        final_parts.append(segment)
                else:
                    partial = _normalize_menu_vocabulary(
                        _read_result(
                            await asyncio.to_thread(recognizer.PartialResult),
                            "partial",
                        ),
                    )
                    visible_text = " ".join([*final_parts, partial]).strip()
                    if visible_text and visible_text != last_partial:
                        last_partial = visible_text
                        await publish("voice.transcript", {
                            "text": visible_text,
                            "final": False,
                        })
        except TimeoutError as exc:
            raise SpeechToTextFinalizationTimeout(
                "Vosk no recibió el final del audio a tiempo.",
            ) from exc
        final_segment = _normalize_menu_vocabulary(
            _read_result(
                await asyncio.to_thread(recognizer.FinalResult),
                "text",
            ),
        )
        if final_segment:
            final_parts.append(final_segment)
        text = " ".join(final_parts).strip()
        if not text:
            raise ValueError("Vosk no reconoció voz. Podés volver a hablar o escribir.")
        log_event(
            "INFO",
            "voice.vosk_transcription_finished",
            session_id=self.session_id,
            transcript_length=len(text),
            audio_bytes=self.byte_count,
            total_duration_ms=round((time.perf_counter() - started_at) * 1000),
        )
        return text
