"""Regresión local de voz y transporte sin solicitudes al proveedor."""

import asyncio
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from google.genai import types
from starlette.websockets import WebSocketDisconnect

import backend.api.app as api
from backend.api.conversation_socket import _detect_payment_method
from backend.ai.live_transcriber import LiveTranscriber
from backend.ai.errors import AIProviderError
from backend.domain.session import Session
from backend.services.order_service import OrderService


class FakeTranscriber(LiveTranscriber):
    """Transcriptor de prueba que espera audio.stop antes de entregar texto."""

    async def transcribe(self, publish) -> str:
        """Emite una hipótesis y espera el cierre explícito del turno.

        Args:
            publish: Callback de eventos.

        Returns:
            Texto conocido para comprobar el paso al orquestador.
        """
        await publish("voice.ready", {})
        await publish("voice.transcript", {"text": "hipótesis", "final": False})
        while await self.chunks.get() is not None:
            pass
        return "Quiero una Burger Clásica con Coca"


class ConversationTests(unittest.TestCase):
    """Comprueba exclusión de turnos, eventos y cierre del canal de voz."""

    def setUp(self) -> None:
        """Crea servicio real y orquestador simulado sin credenciales ni red."""
        self.log_patch = patch("backend.logging.event_logger.LOGGER.disabled", True)
        self.log_patch.start()
        self.session = Session()
        self.assistant = Mock()
        self.assistant.send_message.return_value = "Respuesta de prueba"
        self.runtime = api.SessionRuntime(
            OrderService(api.menu, self.session), self.assistant,
        )
        api.sessions[self.session.session_id] = self.runtime
        self.client = TestClient(api.app)
        self.fake = patch("backend.api.conversation_socket.create_speech_to_text", FakeTranscriber)
        self.fake.start()
        self.url = f"/ws/sessions/{self.session.session_id}"

    def tearDown(self) -> None:
        """Retira estado y reemplazos utilizados exclusivamente por esta prueba."""
        self.client.close()
        api.sessions.pop(self.session.session_id, None)
        api.websocket_manager.disconnect(self.session.session_id)
        self.fake.stop()
        self.log_patch.stop()

    def test_payment_phrases_are_detected_without_llm(self) -> None:
        """Reconoce las opciones explícitas para evitar latencia del LLM."""
        self.assertEqual(_detect_payment_method("quiero pagar con tarjeta"), "CARD")
        self.assertEqual(_detect_payment_method("prefiero pagar en caja"), "CASH")
        self.assertEqual(_detect_payment_method("pago por QR"), "QR")
        self.assertIsNone(_detect_payment_method("quiero pagar"))

    def start_voice(self, ws) -> None:
        """Inicia voz y verifica que la hipótesis todavía no ejecuta el pedido.

        Args:
            ws: Cliente WebSocket conectado.
        """
        self.assertEqual(ws.receive_json()["type"], "connection.ready")
        ws.send_json({"type": "audio.start"})
        self.assertEqual(ws.receive_json()["type"], "voice.ready")
        self.assertFalse(ws.receive_json()["data"]["final"])
        self.assistant.send_message.assert_not_called()

    def test_final_voice_uses_existing_orchestrator_once(self) -> None:
        """Procesa solo el texto final, sin duplicar por un audio.stop repetido."""
        with self.client.websocket_connect(self.url) as ws:
            self.start_voice(ws)
            ws.send_bytes(b"\x00\x00" * 1600)
            ws.send_json({"type": "audio.stop"})
            ws.send_json({"type": "audio.stop"})
            final = ws.receive_json()
            self.assertTrue(final["data"]["final"])
            self.assertEqual(ws.receive_json()["type"], "assistant.text")
        self.assistant.send_message.assert_called_once_with("Quiero una Burger Clásica con Coca")
        self.assertFalse(self.runtime.turn_lock.locked())
        self.assertNotIn(self.session.session_id, api.websocket_manager.connections)

    def test_cancel_preserves_cart_and_allows_text(self) -> None:
        """Cancelar descarta voz y permite continuar escribiendo en la sesión."""
        with self.client.websocket_connect(self.url) as ws:
            self.start_voice(ws)
            ws.send_json({"type": "audio.cancel"})
            self.assertEqual(ws.receive_json()["type"], "voice.cancelled")
            self.assistant.send_message.assert_not_called()
            self.assertEqual(self.runtime.service.get_cart().total, 0)
            ws.send_json({"type": "user.text", "data": {"message": "hola"}})
            self.assertEqual(ws.receive_json()["type"], "assistant.text")
        self.assistant.send_message.assert_called_once_with("hola")

    def test_http_and_text_blocked_while_recording(self) -> None:
        """La reserva de voz impide procesar una segunda entrada concurrente."""
        with self.client.websocket_connect(self.url) as ws:
            self.start_voice(ws)
            response = self.client.post(
                f"/api/sessions/{self.session.session_id}/messages", json={"message": "hola"},
            )
            self.assertEqual(response.status_code, 409)
            ws.send_json({"type": "user.text", "data": {"message": "hola"}})
            self.assertEqual(ws.receive_json()["type"], "client.error")
        self.assistant.send_message.assert_not_called()
        self.assertFalse(self.runtime.turn_lock.locked())

    def test_disconnect_cancels_recording_and_allows_reconnect(self) -> None:
        """Desconectar limpia transcripción y registro, sin el RuntimeError anterior."""
        with self.client.websocket_connect(self.url) as ws:
            self.start_voice(ws)
        with self.client.websocket_connect(self.url) as ws:
            self.assertEqual(ws.receive_json()["data"]["cart"]["state"], "ACTIVE")
        self.assertFalse(self.runtime.turn_lock.locked())

    def test_rejects_second_socket(self) -> None:
        """Una segunda conexión no reemplaza al destinatario de los eventos."""
        with self.client.websocket_connect(self.url) as ws:
            ws.receive_json()
            with self.assertRaises(WebSocketDisconnect) as error:
                with self.client.websocket_connect(self.url):
                    pass
            self.assertEqual(error.exception.code, 4409)
            ws.send_json({"type": "user.text", "data": {"message": "hola"}})
            self.assertEqual(ws.receive_json()["type"], "assistant.text")

    def test_invalid_json_structure_recovers(self) -> None:
        """JSON sintácticamente válido con forma incorrecta no rompe el canal."""
        with self.client.websocket_connect(self.url) as ws:
            ws.receive_json()
            for payload in [None, [], {"type": "user.text", "data": []}]:
                ws.send_json(payload)
                self.assertEqual(ws.receive_json()["type"], "client.error")
            ws.send_json({"type": "user.text", "data": {"message": "hola"}})
            self.assertEqual(ws.receive_json()["type"], "assistant.text")

    def test_invalid_pcm_cancels_without_mutation(self) -> None:
        """PCM truncado libera la reserva sin ejecutar el orquestador."""
        with self.client.websocket_connect(self.url) as ws:
            self.start_voice(ws)
            ws.send_bytes(b"\x00")
            self.assertEqual(ws.receive_json()["type"], "voice.error")
        self.assistant.send_message.assert_not_called()
        self.assertFalse(self.runtime.turn_lock.locked())

    def test_provider_failure_preserves_text_channel(self) -> None:
        """Una falla de transcripción mantiene el carrito y el canal escrito."""
        with patch.object(FakeTranscriber, "transcribe", new=AsyncMock(side_effect=TimeoutError)):
            with self.client.websocket_connect(self.url) as ws:
                ws.receive_json()
                ws.send_json({"type": "audio.start"})
                self.assertEqual(ws.receive_json()["type"], "voice.error")
                ws.send_json({"type": "user.text", "data": {"message": "hola"}})
                self.assertEqual(ws.receive_json()["type"], "assistant.text")
        self.assistant.send_message.assert_called_once_with("hola")

    def test_missing_voice_model_explains_the_configured_name(self) -> None:
        """Un modelo inexistente informa causa, etapa y nombre sin tocar el pedido."""
        provider_error = AIProviderError(
            provider="Gemini",
            model="gemini-3.6-transcribe-live",
            error_type="MODEL_NOT_FOUND",
            stage="VOICE_TRANSCRIPTION",
            retryable=False,
            transaction_applied=False,
            technical_message="not found",
            user_message="El modelo configurado «gemini-3.6-transcribe-live» no está disponible.",
            status_code=404,
        )
        with patch.object(
            FakeTranscriber,
            "transcribe",
            new=AsyncMock(side_effect=provider_error),
        ):
            with self.client.websocket_connect(self.url) as ws:
                ws.receive_json()
                ws.send_json({"type": "audio.start"})
                event = ws.receive_json()
        self.assertEqual(event["type"], "voice.error")
        self.assertEqual(event["data"]["type"], "MODEL_NOT_FOUND")
        self.assertEqual(event["data"]["stage"], "VOICE_TRANSCRIPTION")
        self.assertIn("gemini-3.6-transcribe-live", event["data"]["message"])
        self.assistant.send_message.assert_not_called()

    def test_frontend_can_remove_an_optional_extra(self) -> None:
        """El endpoint quita solo el extra y conserva la línea validada."""
        item = self.runtime.service.add_item(
            "BURGER_CLASICA",
            1,
            {"drink": "WATER", "extra_cheese": "ADD_CHEESE"},
        )

        response = self.client.delete(
            "/api/sessions/"
            f"{self.session.session_id}/cart/items/{item.line_id}/"
            "modifiers/extra_cheese"
        )

        self.assertEqual(response.status_code, 200)
        cart = response.json()["cart"]
        self.assertEqual(cart["total"], 8500)
        self.assertEqual(cart["items"][0]["selected_modifiers"], {"drink": "WATER"})

    def test_serves_scannable_demo_qr_asset(self) -> None:
        """Entrega el SVG QR local sin depender de un proveedor de pagos."""
        response = self.client.get("/static/assets/qr-demostracion.svg")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<svg", response.text)
        self.assertIn("qr-path", response.text)

    def test_cancel_immediately_releases_reservation(self) -> None:
        """Cancelar sin esperar voice.ready no deja la sesión bloqueada."""
        with self.client.websocket_connect(self.url) as ws:
            ws.receive_json()
            ws.send_json({"type": "audio.start"})
            ws.send_json({"type": "audio.cancel"})
            while ws.receive_json()["type"] != "voice.cancelled":
                pass
            ws.send_json({"type": "user.text", "data": {"message": "hola"}})
            self.assertEqual(ws.receive_json()["type"], "assistant.text")

    def test_confirmed_order_rejects_voice(self) -> None:
        """Un pedido confirmado no permite iniciar una nueva transcripción."""
        self.runtime.service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        self.runtime.service.prepare_payment()
        self.runtime.service.select_payment_method("CASH")
        self.runtime.service.complete_payment()
        with self.client.websocket_connect(self.url) as ws:
            ws.receive_json()
            ws.send_json({"type": "audio.start"})
            self.assertEqual(ws.receive_json()["type"], "client.error")
        self.assistant.send_message.assert_not_called()


class TranscriberTests(unittest.IsolatedAsyncioTestCase):
    """Verifica el protocolo del proveedor con eventos simulados del SDK."""

    async def test_partial_is_not_final_and_generation_complete_finishes(self) -> None:
        """Solo segmentos definitivos forman el texto entregado al pedido."""
        end = asyncio.Event()
        sent = []

        async def send(**kwargs) -> None:
            """Captura envíos y libera respuestas después de activity_end.

            Args:
                **kwargs: Mensaje enviado al SDK.
            """
            sent.append(kwargs)
            if "activity_end" in kwargs:
                end.set()

        async def receive():
            """Emite hipótesis, texto definitivo y cierre del proveedor.

            Yields:
                Respuestas tipadas equivalentes a eventos reales de Live.
            """
            yield types.LiveServerMessage(server_content=types.LiveServerContent(
                interim_input_transcription=types.Transcription(text="pizza"),
            ))
            await end.wait()
            yield types.LiveServerMessage(server_content=types.LiveServerContent(
                input_transcription=types.Transcription(text="Burger Clásica"),
            ))
            yield types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True))

        session = SimpleNamespace(send_realtime_input=send, receive=receive)

        @asynccontextmanager
        async def connect(**kwargs):
            """Simula apertura y cierre de una conexión del SDK.

            Args:
                **kwargs: Configuración de conexión Live.

            Yields:
                Sesión simulada.
            """
            yield session

        client = SimpleNamespace(
            aio=SimpleNamespace(live=SimpleNamespace(connect=connect), aclose=AsyncMock()),
            close=Mock(),
        )
        transcriber = LiveTranscriber()
        transcriber.feed(b"\x00\x00")
        transcriber.finish()
        with patch("backend.ai.live_transcriber.create_gemini_client", return_value=client):
            result = await transcriber.transcribe(AsyncMock())
        self.assertEqual(result, "Burger Clásica")
        self.assertIn("activity_start", sent[0])
        self.assertIn("activity_end", sent[-1])
        client.aio.aclose.assert_awaited_once()
        client.close.assert_called_once()

    async def test_bounds(self) -> None:
        """Limita tamaño de fragmento, duración total y audio después del cierre."""
        for chunk in [b"", b"x", b"x" * 32770]:
            with self.assertRaises(ValueError):
                LiveTranscriber().feed(chunk)
        transcriber = LiveTranscriber()
        transcriber.byte_count = 16000 * 2 * 60
        with self.assertRaises(ValueError):
            transcriber.feed(b"xx")
        transcriber = LiveTranscriber()
        transcriber.finish()
        with self.assertRaises(ValueError):
            transcriber.feed(b"xx")


if __name__ == "__main__":
    unittest.main()
