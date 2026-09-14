"""Adaptador de audio PCM a texto; no tiene acceso al carrito ni a tools."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from google.genai import types

from backend.ai.gemini_client import create_gemini_client
from backend.logging.event_logger import log_event
from config.settings import get_transcription_model


class LiveTranscriber:
    """Transcribe un único turno explícito y limita audio, espera y recursos."""

    def __init__(self, session_id: str | None = None) -> None:
        """Inicializa la cola acotada y el estado de un turno de hasta 60 segundos.

        Args:
            session_id: Identificador de sesión para correlacionar eventos de voz.
        """
        self.session_id = session_id
        self.chunks: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=128)
        self.ended = False
        self.byte_count = 0
        self.processing_order = False

    def feed(self, chunk: bytes) -> None:
        """Encola PCM16 mono a 16 kHz sin bloquear el WebSocket.

        Args:
            chunk: Fragmento binario con muestras de dos bytes.

        Raises:
            ValueError: Si el turno terminó, el audio es inválido o excede límites.
        """
        if self.ended or not chunk or len(chunk) % 2 or len(chunk) > 32768:
            raise ValueError("Fragmento de audio inválido o turno finalizado.")
        self.byte_count += len(chunk)
        if self.byte_count > 16000 * 2 * 60:
            raise ValueError("El turno de voz supera los 60 segundos.")
        try:
            self.chunks.put_nowait(chunk)
        except asyncio.QueueFull as exc:
            raise ValueError("La conexión no permite enviar el audio a tiempo.") from exc

    def finish(self) -> None:
        """Marca el fin del audio una sola vez, conservando el orden de la cola.

        Raises:
            ValueError: Si la cola está llena y no se puede finalizar sin perder audio.
        """
        if self.ended:
            return
        self.ended = True
        try:
            self.chunks.put_nowait(None)
        except asyncio.QueueFull as exc:
            raise ValueError("No se pudo finalizar el audio; volvé a intentar.") from exc

    async def transcribe(
        self, publish: Callable[[str, dict], Awaitable[None]],
    ) -> str:
        """Abre Live, publica avances y devuelve solo la transcripción final.

        Args:
            publish: Callback asíncrono para estados y transcripciones provisionales.

        Returns:
            Texto definitivo del turno; nunca utiliza una hipótesis provisional.

        Raises:
            TimeoutError: Si falla la apertura o el turno no termina a tiempo.
            ValueError: Si no hay transcripción final o el proveedor cierra antes.
            Exception: Si el proveedor o la publicación de eventos fallan.
        """
        client = create_gemini_client()
        started_at = time.perf_counter()
        receiver = None
        final_parts: list[str] = []
        end_sent = asyncio.Event()
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(
                language_codes=["es-419"],
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
            ),
        )
        try:
            async with asyncio.timeout(85):
                async with client.aio.live.connect(
                    model=get_transcription_model(), config=config,
                ) as session:
                    await session.send_realtime_input(activity_start=types.ActivityStart())
                    log_event("INFO", "voice.live_ready", session_id=self.session_id,
                              model=get_transcription_model())

                    async def receive() -> str:
                        """Publica hipótesis y acumula segmentos definitivos hasta cerrar el turno.

                        Returns:
                            Texto final después del marcador de cierre del proveedor.

                        Raises:
                            ValueError: Si el proveedor cierra sin finalizar el turno.
                        """
                        while True:
                            async for response in session.receive():
                                content = response.server_content
                                if content is None:
                                    continue
                                final = content.input_transcription
                                interim = content.interim_input_transcription
                                if final and final.text:
                                    final_parts.append(final.text)
                                if final or interim:
                                    await publish("voice.transcript", {
                                        "text": "".join(final_parts) + (
                                            interim.text or "" if interim else ""
                                        ),
                                        "final": False,
                                    })
                                if end_sent.is_set() and (
                                    content.turn_complete or content.generation_complete
                                    or (final and final.finished)
                                ):
                                    return "".join(final_parts).strip()
                            if end_sent.is_set():
                                raise ValueError("La transcripción terminó sin confirmar el turno.")
                            await asyncio.sleep(0)

                    receiver = asyncio.create_task(receive())
                    await publish("voice.ready", {})
                    while True:
                        chunk = await asyncio.wait_for(self.chunks.get(), timeout=65)
                        if receiver.done():
                            await receiver
                            raise ValueError("La transcripción se cerró antes de terminar el audio.")
                        if chunk is None:
                            break
                        await session.send_realtime_input(audio=types.Blob(
                            data=chunk, mime_type="audio/pcm;rate=16000",
                        ))
                    end_sent.set()
                    audio_finished_at = time.perf_counter()
                    log_event(
                        "INFO",
                        "voice.audio_finished",
                        session_id=self.session_id,
                        audio_bytes=self.byte_count,
                        audio_duration_ms=round((audio_finished_at - started_at) * 1000),
                    )
                    await session.send_realtime_input(activity_end=types.ActivityEnd())
                    text = await asyncio.wait_for(receiver, timeout=20)
                    if not text:
                        raise ValueError("No se reconoció voz. Podés volver a hablar o escribir.")
                    log_event(
                        "INFO",
                        "voice.transcription_finished",
                        session_id=self.session_id,
                        transcript_length=len(text),
                        transcription_duration_ms=round((time.perf_counter() - audio_finished_at) * 1000),
                        total_duration_ms=round((time.perf_counter() - started_at) * 1000),
                    )
                    return text
        finally:
            if receiver is not None:
                receiver.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await receiver
            await client.aio.aclose()
            client.close()
