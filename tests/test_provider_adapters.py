"""Pruebas de contratos de IA sin tráfico a proveedores externos."""

import asyncio
import os
import unittest
from unittest.mock import ANY, Mock, patch

from backend.ai.contracts import OrderInterpreter, SpeechToText, VoiceEventPublisher
from backend.ai.factories import create_order_interpreter, create_speech_to_text
from backend.ai.openai_interpreter import OpenAIOrderInterpreter
from backend.domain.menu import load_menu
from backend.domain.session import Session
from backend.services.order_service import OrderService
from config.settings import get_llm_provider, get_stt_provider


class AlternateSpeechToText(SpeechToText):
    """Implementación simulada que representa un proveedor STT futuro."""

    provider_name = "simulado"

    def __init__(self) -> None:
        """Inicializa el estado local del turno de voz simulado."""
        self.chunks: list[bytes] = []
        self.finished = False
        self._processing_order = False

    @property
    def processing_order(self) -> bool:
        """Indica si el texto final ya fue entregado al intérprete.

        Returns:
            Estado actual del procesamiento del turno.
        """
        return self._processing_order

    @processing_order.setter
    def processing_order(self, value: bool) -> None:
        """Actualiza el estado de procesamiento del turno.

        Args:
            value: Estado que debe conservar el adaptador.
        """
        self._processing_order = value

    def feed(self, chunk: bytes) -> None:
        """Guarda un fragmento de audio para la simulación.

        Args:
            chunk: Fragmento PCM controlado por la prueba.

        Raises:
            ValueError: Si el turno fue cerrado antes de recibir el fragmento.
        """
        if self.finished:
            raise ValueError("El turno simulado ya terminó.")
        self.chunks.append(chunk)

    def finish(self) -> None:
        """Marca el final de la entrada de audio simulada."""
        self.finished = True

    def cancel(self) -> None:
        """Descarta el audio controlado que aún no se interpretó."""
        if not self.processing_order:
            self.chunks.clear()
            self.finished = True

    async def transcribe(self, publish: VoiceEventPublisher) -> str:
        """Publica un parcial y devuelve una transcripción conocida.

        Args:
            publish: Callback que recibe los eventos simulados del proveedor.

        Returns:
            Texto final determinista para la prueba de integración del contrato.
        """
        await publish("voice.ready", {})
        await publish("voice.transcript", {"text": "quiero una", "final": False})
        return "Quiero una Burger Clásica con Agua"

    async def close(self) -> None:
        """Cierra el turno simulado sin recursos externos."""
        self.cancel()


class AlternateOrderInterpreter(OrderInterpreter):
    """Intérprete simulado que delega una operación en el servicio real."""

    provider_name = "simulado"

    def __init__(self, service: OrderService) -> None:
        """Conserva la autoridad real que valida el pedido.

        Args:
            service: Servicio de pedidos que debe seguir aplicando las reglas.
        """
        self.service = service

    def send_message(self, message: str) -> str:
        """Simula una intención y la deriva al servicio real.

        Args:
            message: Texto final que se usaría para decidir la operación.

        Returns:
            Respuesta de prueba después de la validación de OrderService.
        """
        self.service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        return "Agregué una Burger Clásica con Agua."

    def close(self) -> None:
        """Cierra la simulación sin conservar recursos externos."""


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    """Demuestra que la unión STT-intérprete no depende de Gemini en el dominio."""

    async def test_alternate_adapters_preserve_order_service_authority(self) -> None:
        """Un adaptador alternativo simulado usa el mismo servicio y sus precios."""
        service = OrderService(load_menu("config/menu.json"), Session())
        stt = AlternateSpeechToText()
        interpreter = AlternateOrderInterpreter(service)
        events: list[tuple[str, dict]] = []

        async def publish(event_type: str, data: dict) -> None:
            """Registra los eventos publicados por el STT simulado.

            Args:
                event_type: Tipo del evento de voz publicado.
                data: Datos del evento de voz publicado.
            """
            events.append((event_type, data))

        stt.feed(b"\x00\x00")
        stt.finish()
        text = await stt.transcribe(publish)
        stt.processing_order = True
        response = interpreter.send_message(text)
        await stt.close()
        interpreter.close()

        self.assertEqual(response, "Agregué una Burger Clásica con Agua.")
        self.assertEqual(service.get_cart().total, 8500)
        self.assertEqual(events[1][1]["final"], False)
        self.assertTrue(stt.processing_order)


class ProviderFactoryTests(unittest.TestCase):
    """Comprueba selección de proveedor sin exigir credenciales no seleccionadas."""


    def test_openai_interpreter_uses_the_same_tool_and_service(self) -> None:
        """OpenAI simulado agrega mediante la tool sin acceder al dominio directo."""
        service = OrderService(load_menu("config/menu.json"), Session())
        first = type("Response", (), {"choices": [type("Choice", (), {
            "message": type("Message", (), {
                "content": None,
                "tool_calls": [type("Call", (), {
                    "id": "call_add",
                    "function": type("Function", (), {
                        "name": "add_item",
                        "arguments": '{"product_id":"BURGER_CLASICA","selected_modifiers":{"drink":"WATER"}}',
                    })(),
                })()],
            })(),
        })()]})()
        second = type("Response", (), {"choices": [type("Choice", (), {
            "message": type("Message", (), {
                "content": "Agregue tu Burger Clasica con Agua.",
                "tool_calls": [],
            })(),
        })()]})()
        client = Mock()
        client.chat.completions.create.side_effect = [first, second]
        with patch("backend.ai.openai_interpreter.create_openai_client", return_value=client):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
            response = interpreter.send_message("Quiero una Burger Clasica con Agua")
        self.assertEqual(response, "Agregue tu Burger Clasica con Agua.")
        self.assertEqual(service.get_cart().total, 8500)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_default_providers_are_gemini(self) -> None:
        """La ausencia de variables conserva el comportamiento anterior con Gemini."""
        with patch.dict(os.environ, {"STT_PROVIDER": "", "LLM_PROVIDER": ""}, clear=False):
            self.assertEqual(get_stt_provider(), "gemini")
            self.assertEqual(get_llm_provider(), "gemini")

    def test_gemini_factories_use_concrete_adapters(self) -> None:
        """Las fábricas seleccionan adaptadores Gemini sin llamar a la red."""
        service = OrderService(load_menu("config/menu.json"), Session())
        stt_sentinel = object()
        interpreter_sentinel = object()
        with patch.dict(os.environ, {"STT_PROVIDER": "gemini", "LLM_PROVIDER": "gemini"}, clear=False), \
             patch("backend.ai.factories.GeminiLiveTranscriber", return_value=stt_sentinel) as stt_class, \
             patch("backend.ai.factories.GeminiOrderInterpreter", return_value=interpreter_sentinel) as llm_class:
            self.assertIs(create_speech_to_text("session-test"), stt_sentinel)
            self.assertIs(create_order_interpreter(service), interpreter_sentinel)
        stt_class.assert_called_once_with(session_id="session-test")
        llm_class.assert_called_once_with(service=service, model=ANY)

    def test_openai_credit_balance_error_is_not_reported_as_temporary(self) -> None:
        """Un 429 sin creditos explica facturacion y no recomienda reintentar."""
        service = OrderService(load_menu("config/menu.json"), Session())
        with patch("backend.ai.openai_interpreter.create_openai_client", return_value=Mock()):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
        error = type("CreditError", (Exception,), {
            "status_code": 429,
            "__str__": lambda self: "credit_balance_exhausted: no credits remaining",
        })()
        result = interpreter._classify_error(error, "OPENAI_INTERPRETATION", False, None)
        self.assertEqual(result.error_type, "CREDIT_BALANCE_EXHAUSTED")
        self.assertFalse(result.retryable)
        self.assertIn("creditos", result.user_message)

    def test_openai_factory_uses_only_the_openai_adapter(self) -> None:
        """LLM_PROVIDER=openai selecciona el adaptador sin crear Gemini."""
        service = OrderService(load_menu("config/menu.json"), Session())
        sentinel = object()
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=False), \
             patch("backend.ai.factories.OpenAIOrderInterpreter", return_value=sentinel) as adapter:
            self.assertIs(create_order_interpreter(service), sentinel)
        adapter.assert_called_once_with(service=service, model=ANY)

    def test_unimplemented_provider_fails_before_reading_its_credential(self) -> None:
        """Un proveedor futuro explica el límite sin requerir claves inexistentes."""
        with patch.dict(os.environ, {"STT_PROVIDER": "vosk", "LLM_PROVIDER": "anthropic"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "STT_PROVIDER='vosk'.*no tiene un adaptador"):
                create_speech_to_text()
            service = OrderService(load_menu("config/menu.json"), Session())
            with self.assertRaisesRegex(RuntimeError, "LLM_PROVIDER='anthropic'.*no tiene un adaptador"):
                create_order_interpreter(service)


if __name__ == "__main__":
    unittest.main()
