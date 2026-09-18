"""Pruebas unitarias del adaptador STT local de Vosk sin modelo descargado."""

import asyncio
import unittest
from unittest.mock import patch

from backend.ai.contracts import SpeechToTextConfigurationError
from backend.ai.vosk_transcriber import VoskTranscriber, _normalize_menu_vocabulary


class FakeRecognizer:
    """Simula resultados incrementales de Vosk para probar el protocolo local."""

    def __init__(self) -> None:
        """Inicializa el contador de fragmentos reconocidos."""
        self.calls = 0

    def AcceptWaveform(self, chunk: bytes) -> bool:
        """Alterna entre un parcial y un segmento final simulado.

        Args:
            chunk: Fragmento PCM de prueba recibido por el reconocedor.

        Returns:
            False para el primer fragmento y True para el segundo.
        """
        self.calls += 1
        return self.calls == 2

    def PartialResult(self) -> str:
        """Devuelve una hipótesis local controlada.

        Returns:
            JSON compatible con la respuesta parcial de Vosk.
        """
        return '{"partial": "quiero una burger"}'

    def Result(self) -> str:
        """Devuelve un segmento reconocido controlado.

        Returns:
            JSON compatible con un segmento definitivo de Vosk.
        """
        return '{"text": "quiero una burger clasica"}'

    def FinalResult(self) -> str:
        """Devuelve el cierre definitivo del reconocimiento simulado.

        Returns:
            JSON compatible con el cierre de Vosk.
        """
        return '{"text": "con agua"}'


class VoskTranscriberTests(unittest.IsolatedAsyncioTestCase):
    """Verifica que Vosk cumpla el contrato SpeechToText sin usar un modelo real."""

    async def test_publishes_partial_and_returns_final_text(self) -> None:
        """Publica una hipótesis y solo entrega texto completo después de audio.stop."""
        transcriber = VoskTranscriber("session-test", "models/fake")
        events: list[tuple[str, dict]] = []

        async def publish(event_type: str, data: dict) -> None:
            """Conserva eventos publicados por el adaptador bajo prueba.

            Args:
                event_type: Tipo de evento de voz enviado por el adaptador.
                data: Datos serializables asociados al evento.
            """
            events.append((event_type, data))

        transcriber.feed(b"\x00\x00" * 1600)
        transcriber.feed(b"\x00\x00" * 1600)
        transcriber.finish()
        recognizer = FakeRecognizer()
        with patch("backend.ai.vosk_transcriber._load_model", return_value=object()), patch(
            "backend.ai.vosk_transcriber.KaldiRecognizer",
            return_value=recognizer,
        ):
            text = await transcriber.transcribe(publish)

        self.assertEqual(text, "quiero una burger clasica con agua")
        self.assertEqual(events[0], ("voice.ready", {}))
        self.assertIn(
            ("voice.transcript", {"text": "quiero una burger", "final": False}),
            events,
        )

    async def test_invalid_model_configuration_does_not_start_voice(self) -> None:
        """Explica la configuración inválida antes de publicar disponibilidad."""
        transcriber = VoskTranscriber("session-test", "models/missing")

        async def publish(event_type: str, data: dict) -> None:
            """Falla si Vosk publicara eventos antes de validar el modelo.

            Args:
                event_type: Tipo de evento inesperado.
                data: Datos inesperados asociados al evento.

            Raises:
                AssertionError: Siempre, porque no debe haber eventos disponibles.
            """
            raise AssertionError(f"Evento inesperado: {event_type} {data}")

        with patch(
            "backend.ai.vosk_transcriber._load_model",
            side_effect=RuntimeError("modelo ausente"),
        ):
            with self.assertRaises(SpeechToTextConfigurationError):
                await transcriber.transcribe(publish)

    def test_normalizes_observed_menu_words_without_inventing_an_operation(self) -> None:
        """Corrige variantes de bebida y conserva el resto de la transcripción."""
        text = _normalize_menu_vocabulary(
            "quiero otra burguer doble pero la debida tiene que ser esperáis",
        )

        self.assertEqual(
            text,
            "quiero otra burguer doble pero la bebida tiene que ser Sprite",
        )


if __name__ == "__main__":
    unittest.main()
