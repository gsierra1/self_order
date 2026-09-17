"""Prueba de navegador con micrófono sintético y proveedor simulado.

Ejecutar desde la raíz con:
python -m unittest discover -s tests -p browser_voice.py -v.
Requiere Edge instalado y las dependencias de requirements-dev.txt.
"""

import asyncio
import socket
import threading
import time
import unittest
from unittest.mock import patch

import uvicorn
from playwright.sync_api import sync_playwright, expect

import backend.api.app as api
from backend.ai.live_transcriber import LiveTranscriber


class BrowserTranscriber(LiveTranscriber):
    """Espera audio real del navegador pero devuelve una frase controlada."""

    async def transcribe(self, publish) -> str:
        """Comprueba PCM recibido y entrega una solicitud conocida.

        Args:
            publish: Publicador de estados y transcripciones.

        Returns:
            Pedido completo con un extra para verificar etiquetas visibles.
        """
        await publish("voice.ready", {})
        chunk = await self.chunks.get()
        if chunk is None:
            raise ValueError("No se capturó audio.")
        assert len(chunk) == 3200
        await publish("voice.transcript", {"text": "Quiero una Burger Clásica", "final": False})
        while await self.chunks.get() is not None:
            pass
        return "Quiero una Burger Clásica con Coca y queso"


class BrowserAssistant:
    """Orquestador simulado que usa el servicio real y sus eventos."""

    def __init__(self, service, model) -> None:
        """Conserva el servicio real creado por la API.

        Args:
            service: Servicio de pedidos de la sesión.
            model: Modelo ignorado por la simulación.
        """
        self.service = service

    def send_message(self, message: str) -> str:
        """Aplica respuestas simuladas para alta, QR y confirmacion.

        Args:
            message: Texto final de voz o escritura.

        Returns:
            Respuesta de prueba para pantalla y sintesis.
        """
        if message == "confirmar":
            self.service.prepare_payment()
            self.service.select_payment_method("CASH")
            self.service.complete_payment()
            return "Pedido confirmado"
        if message == "Quiero pagar con QR.":
            self.service.select_payment_method("QR")
            return "QR seleccionado"
        self.service.add_item(
            "BURGER_CLASICA",
            1,
            {"drink": "WATER", "extra_cheese": "ADD_CHEESE"},
        )
        return "Agregué tu hamburguesa. El total es 9.500 pesos argentinos."


def create_browser_assistant(service) -> BrowserAssistant:
    """Crea el intérprete simulado sin depender del proveedor configurado.

    Args:
        service: Servicio real construido por la API para la sesión de prueba.

    Returns:
        Intérprete determinista conectado al servicio real.
    """
    return BrowserAssistant(service, model="simulado")


class BrowserVoiceTests(unittest.TestCase):
    """Prueba visible del circuito completo con Edge y dispositivos sintéticos."""

    def test_microphone_to_cart_and_confirmation(self) -> None:
        """Verifica voz, QR demo visible, vuelta al carrito y cierre de pago."""
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(api.app, log_level="error"))
        previous = set(api.sessions)
        with patch("backend.logging.event_logger.LOGGER.disabled", True), \
             patch(
                 "backend.api.app.create_order_interpreter",
                 side_effect=create_browser_assistant,
             ), \
             patch("backend.api.conversation_socket.create_speech_to_text", BrowserTranscriber):
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(.05)
                self.assertTrue(server.started)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="msedge", headless=True, args=[
                        "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                    ])
                    try:
                        page = browser.new_page(permissions=["microphone"])
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.add_init_script("""
                            window.spokenTexts = [];
                            speechSynthesis.speak = utterance => window.spokenTexts.push(utterance.text);
                        """)
                        page.goto(f"http://127.0.0.1:{port}")
                        expect(page.locator("#mic-button")).to_be_enabled()
                        session_id = next(iter(set(api.sessions) - previous))
                        current_socket = api.websocket_manager.connections[session_id]
                        close_future = asyncio.run_coroutine_threadsafe(
                            current_socket.close(code=1012),
                            api.websocket_manager.event_loop,
                        )
                        close_future.result(timeout=5)
                        expected_status = "Conexi" + chr(243) + "n restablecida"
                        expect(page.locator("#system-status")).to_have_text(
                            expected_status,
                            timeout=10000,
                        )
                        page.locator("#mic-button").click()
                        expect(page.locator("#mic-button")).to_have_text("Enviar audio")
                        expect(page.locator("#voice-transcript")).to_contain_text("Quiero una Burger Clásica")
                        expect(page.locator(".cart-item")).to_have_count(0)
                        expect(page.locator("#message-input")).to_be_disabled()
                        page.locator("#mic-button").click()
                        expect(page.locator(".cart-item")).to_have_count(1)
                        expect(page.locator("#cart-total")).to_have_text("ARS 9.500")
                        details = page.locator(".cart-item-details")
                        expect(details).to_contain_text(
                            "Bebida: Agua | Precio base: ARS 8.500"
                        )
                        expect(details).to_contain_text("Extras")
                        expect(details).to_contain_text("Queso · + ARS 1.000")
                        expect(page.locator(".remove-extra-button")).to_have_count(1)
                        page.locator(".remove-extra-button").click()
                        expect(page.locator("#cart-total")).to_have_text("ARS 8.500")
                        expect(page.locator(".cart-item-details")).not_to_contain_text("Queso")
                        expect(page.locator(".remove-extra-button")).to_have_count(0)
                        expect(page.locator(".cart-item-total .remove-item-button")).to_have_count(1)
                        expect(page.locator("#message-input")).to_be_enabled()
                        page.locator("#confirm-cart-button").click()
                        expect(page.locator("#payment-panel")).to_be_visible()
                        page.locator('[data-payment-method="QR"]').click()
                        expect(page.locator(".demo-qr")).to_be_visible()
                        expect(page.locator(".payment-options")).to_be_hidden()
                        expect(page.locator("#payment-panel h3")).to_be_hidden()
                        expect(page.locator(".demo-qr")).to_have_attribute(
                            "src", "/static/assets/qr-demostracion.svg"
                        )
                        page.locator("#payment-back").click()
                        expect(page.locator(".payment-options")).to_be_visible()
                        expect(page.locator("#payment-panel h3")).to_be_visible()
                        expect(page.locator(".demo-qr")).to_have_count(0)
                        page.locator("#payment-back").click()
                        expect(page.locator("#payment-panel")).to_be_hidden()
                        expect(page.locator("#message-input")).to_be_enabled()
                        self.assertEqual(len(page.evaluate("window.spokenTexts")), 2)
                        page.locator("#audio-button").click()
                        page.locator("#message-input").fill("confirmar")
                        page.locator("#send-button").click()
                        expect(page.locator("#session-state")).to_have_text("CONFIRMED")
                        expect(page.locator("#mic-button")).to_be_disabled()
                        expect(page.locator("#message-input")).to_be_disabled()
                        self.assertEqual(len(page.evaluate("window.spokenTexts")), 2)
                        self.assertFalse(errors, errors)
                    finally:
                        browser.close()
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                listener.close()
                for sid in set(api.sessions) - previous:
                    api.sessions.pop(sid)


if __name__ == "__main__":
    unittest.main()
