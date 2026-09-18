"""Pruebas de contratos de IA sin tráfico a proveedores externos."""

import asyncio
import os
import unittest
from unittest.mock import ANY, Mock, patch

from backend.ai.contracts import OrderInterpreter, SpeechToText, VoiceEventPublisher
from backend.ai.factories import create_order_interpreter, create_speech_to_text
from backend.ai.gemini_llm_interpreter import GeminiOrderInterpreter
from backend.ai.groq_llm_interpreter import GroqOrderInterpreter
from backend.ai.list_groq_models import list_groq_models
from backend.ai.openai_llm_interpreter import OpenAIOrderInterpreter
from backend.ai.order_tools_runtime import OrderToolsRuntime
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

    def test_groq_model_list_orders_identifiers_and_closes_client(self) -> None:
        """Lista modelos Groq simulados sin revelar ni requerir una credencial real."""
        client = Mock()
        client.models.list.return_value.data = [
            type("Model", (), {"id": "z-model"})(),
            type("Model", (), {"id": "a-model"})(),
        ]

        with patch(
            "backend.ai.list_groq_models.create_groq_client",
            return_value=client,
        ):
            models = list_groq_models()

        self.assertEqual(models, ["a-model", "z-model"])
        client.close.assert_called_once_with()

    def test_llm_prompts_forbid_clarifications_absent_from_catalog(self) -> None:
        """Impide que los intérpretes inventen variantes al pedir una aclaración."""
        service = OrderService(load_menu("config/menu.json"), Session())
        shared_instruction = OrderToolsRuntime(service).build_system_instruction()
        gemini_interpreter = GeminiOrderInterpreter.__new__(GeminiOrderInterpreter)
        gemini_interpreter.service = service
        gemini_instruction = gemini_interpreter._build_system_instruction()

        for instruction in (shared_instruction, gemini_instruction):
            self.assertIn("variantes ni opciones", instruction)
            self.assertIn("grupos obligatorios", instruction)
            self.assertIn("distinciones", instruction)
            self.assertIn("Agua [id=WATER]", instruction)


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
        with patch("backend.ai.openai_llm_interpreter.create_openai_client", return_value=client):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
            response = interpreter.send_message("Quiero una Burger Clasica con Agua")
        self.assertNotIn("Agregue tu Burger Clasica con Agua.", response)
        self.assertIn("- Burger Clásica. Cantidad: una unidad.", response)
        self.assertNotIn("Precio unitario", response)
        self.assertIn("Bebida: Agua.", response)
        self.assertIn("agregar algún extra", response)
        self.assertIn("confirmar el pedido", response)
        self.assertEqual(response.count("¿Querés"), 1)
        self.assertEqual(service.get_cart().total, 8500)
        self.assertEqual(client.chat.completions.create.call_count, 1)

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
        with patch("backend.ai.openai_llm_interpreter.create_openai_client", return_value=Mock()):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
        error = type("CreditError", (Exception,), {
            "status_code": 429,
            "__str__": lambda self: "credit_balance_exhausted: no credits remaining",
        })()
        result = interpreter._classify_error(error, "OPENAI_INTERPRETATION", False, None)
        self.assertEqual(result.error_type, "CREDIT_BALANCE_EXHAUSTED")
        self.assertFalse(result.retryable)
        self.assertIn("creditos", result.user_message)

    def test_rate_limit_error_exposes_provider_retry_time(self) -> None:
        """Muestra el tiempo de espera que Groq u OpenAI devuelven en headers."""
        service = OrderService(load_menu("config/menu.json"), Session())
        with patch("backend.ai.openai_llm_interpreter.create_openai_client", return_value=Mock()):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
        error = type("RateLimitError", (Exception,), {
            "status_code": 429,
            "response": type("Response", (), {
                "headers": {"retry-after": "12"},
            })(),
            "__str__": lambda self: "rate limit",
        })()

        result = interpreter._classify_error(error, "OPENAI_INTERPRETATION", False, None)

        self.assertEqual(result.retry_after, "12")
        self.assertIn("12", result.user_message)

    def test_openai_factory_uses_only_the_openai_adapter(self) -> None:
        """LLM_PROVIDER=openai selecciona el adaptador sin crear Gemini."""
        service = OrderService(load_menu("config/menu.json"), Session())
        sentinel = object()
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=False), \
             patch("backend.ai.factories.OpenAIOrderInterpreter", return_value=sentinel) as adapter:
            self.assertIs(create_order_interpreter(service), sentinel)
        adapter.assert_called_once_with(service=service, model=ANY)

    def test_runtime_normalizes_currency_thousands_separators(self) -> None:
        """Uniforma comas y espacios Unicode de miles antes de leer importes."""
        service = OrderService(load_menu("config/menu.json"), Session())
        runtime = OrderToolsRuntime(service)

        text = runtime.sanitize_user_text(
            "El total es $9\u202f500 pesos argentinos y el precio base 8,500 pesos argentinos."
        )

        self.assertEqual(
            text,
            "El total es $9.500 pesos argentinos y el precio base $8.500 pesos argentinos.",
        )

    def test_runtime_converts_cart_table_to_readable_list(self) -> None:
        """Convierte una tabla del carrito en una lista apta para pantalla y voz."""
        service = OrderService(load_menu("config/menu.json"), Session())
        runtime = OrderToolsRuntime(service)

        text = runtime.sanitize_user_text(
            "Tu carrito contiene:\n"
            "| Línea | Producto | Cantidad | Modificadores | Precio unitario |\n"
            "|---|---|---|---|---|\n"
            "| 3 | Burger Doble | 1 | Agua, queso | 11.500 pesos argentinos |"
        )

        self.assertNotIn("|", text)
        self.assertNotIn("Línea", text)
        self.assertIn("Burger Doble (cantidad: 1; modificadores: Agua, queso;", text)
        self.assertIn("11.500 pesos argentinos", text)

    def test_runtime_preserves_thousands_and_removes_concatenated_line_numbers(self) -> None:
        """Separa ítems pegados sin confundir miles con números de una lista."""
        service = OrderService(load_menu("config/menu.json"), Session())
        runtime = OrderToolsRuntime(service)

        text = runtime.sanitize_user_text(
            "Burger Clásica – 12.500 pesos argentinos2. "
            "Burger Doble – 10.500 pesos argentinosEl total es 23.000 pesos argentinos"
        )

        self.assertIn("12.500 pesos argentinos", text)
        self.assertIn("Burger Doble", text)
        self.assertIn("23.000 pesos argentinos", text)
        self.assertNotIn("argentinos2.", text)

    def test_runtime_adds_a_contextual_next_step_after_cart_changes(self) -> None:
        """Ofrece extras pendientes y confirmación después de una mutación."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        runtime = OrderToolsRuntime(service)

        text = runtime.ensure_next_step("Agregué la Burger Clásica.", True)

        self.assertNotIn("Agregué la Burger Clásica.", text)
        self.assertIn("- Burger Clásica. Cantidad: una unidad.", text)
        self.assertNotIn("Precio unitario", text)
        self.assertIn("Bebida: Agua.", text)
        self.assertIn("agregar algún extra", text)
        self.assertIn("pedir algo más", text)
        self.assertIn("confirmar el pedido", text)
        self.assertEqual(text.count("¿Querés"), 1)

    def test_runtime_stops_offering_extras_when_all_are_selected(self) -> None:
        """Ofrece continuar o confirmar cuando ya no quedan extras disponibles."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item(
            "BURGER_CLASICA",
            1,
            {
                "drink": "WATER",
                "extra_tomato": "ADD_TOMATO",
                "extra_lettuce": "ADD_LETTUCE",
                "extra_ham": "ADD_HAM",
                "extra_cheese": "ADD_CHEESE",
            },
        )
        runtime = OrderToolsRuntime(service)

        text = runtime.ensure_next_step("Completé los extras.", True)

        self.assertNotIn("agregar algún extra", text)
        self.assertIn("Extras: Tomate, Lechuga, Jamón, Queso.", text)
        self.assertNotIn("Extra de tomate: Tomate", text)
        self.assertIn("pedir algo más", text)
        self.assertIn("confirmar el pedido", text)
        self.assertEqual(text.count("¿Querés"), 1)

    def test_runtime_removes_numbered_choices_and_expands_etcetera(self) -> None:
        """Evita leer numeración de alternativas y abreviaturas técnicas."""
        service = OrderService(load_menu("config/menu.json"), Session())
        runtime = OrderToolsRuntime(service)

        text = runtime.sanitize_user_text(
            "Elegí: 1. Burger Clásica; 2. Burger Doble. También hay etc."
        )

        self.assertNotIn("1.", text)
        self.assertNotIn("2.", text)
        self.assertNotIn("etc.", text)
        self.assertIn("etcétera", text)

    def test_runtime_replaces_empty_cart_reference_with_real_state(self) -> None:
        """Evita una respuesta que promete mostrar el carrito sin detallarlo."""
        service = OrderService(load_menu("config/menu.json"), Session())
        runtime = OrderToolsRuntime(service)

        text = runtime.sanitize_user_text("Tu carrito queda así:")

        self.assertIn("carrito sigue vacío", text)
        self.assertIn("datos obligatorios", text)

    def test_runtime_builds_real_summary_for_incomplete_reference(self) -> None:
        """Completa una referencia vacía usando únicamente el carrito validado."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        runtime = OrderToolsRuntime(service)

        text = runtime.sanitize_user_text("Tu carrito queda así.")

        self.assertIn("Burger Clásica", text)
        self.assertIn("Agua", text)
        self.assertIn("$8.500 pesos argentinos", text)

    def test_runtime_replaces_a_false_empty_cart_claim_with_real_state(self) -> None:
        """Evita que una respuesta del proveedor contradiga el carrito validado."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        runtime = OrderToolsRuntime(service)

        text = runtime.ensure_next_step("Ahora el carrito está vacío.", False)

        self.assertIn("Burger Clásica", text)
        self.assertIn("$8.500", text)
        self.assertNotIn("vacío", text)

    def test_clear_cart_tool_removes_all_lines_in_one_operation(self) -> None:
        """La tool clear_cart vacía varias líneas sin encadenar eliminaciones."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        service.add_item("BURGER_DOBLE", 1, {"drink": "WATER"})
        runtime = OrderToolsRuntime(service)

        result = runtime.execute(type("Call", (), {"name": "clear_cart", "args": {}})())

        self.assertEqual(result["result"]["removed_count"], 2)
        self.assertEqual(service.get_cart().items, [])

    def test_adjust_quantity_tool_applies_a_relative_change(self) -> None:
        """Expone una resta relativa sin convertirla en eliminación de línea."""
        service = OrderService(load_menu("config/menu.json"), Session())
        item = service.add_item("BURGER_DOBLE", 4, {"drink": "WATER"})
        runtime = OrderToolsRuntime(service)

        result = runtime.execute(type("Call", (), {
            "name": "adjust_quantity",
            "args": {"line_id": item.line_id, "delta": -1},
        })())

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["quantity"], 3)
        self.assertEqual(len(service.get_cart().items), 1)
        self.assertEqual(service.get_cart().total, 31500)

    def test_payment_method_aliases_are_normalized(self) -> None:
        """Acepta expresiones conversacionales para tarjeta, QR y caja."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        service.prepare_payment()

        result = service.select_payment_method("pago con tarjeta")

        self.assertEqual(result["payment_method"], "CARD")

    def test_payment_method_selection_from_active_prepares_payment(self) -> None:
        """Una preferencia de pago expresada desde el inicio prepara la sesión."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        runtime = OrderToolsRuntime(service)

        result = runtime.execute(
            type("Call", (), {
                "name": "select_payment_method",
                "args": {"method": "pago con QR"},
            })()
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["payment_method"], "QR")
        self.assertEqual(service.session.state.value, "PAYMENT_PENDING")

    def test_direct_payment_choice_skips_intermediate_selector_event(self) -> None:
        """Una elección explícita desde ACTIVE publica solo el método elegido."""
        events = []
        service = OrderService(
            load_menu("config/menu.json"),
            Session(),
            event_callback=lambda event_type, data: events.append((event_type, data)),
        )
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        events.clear()

        result = service.select_payment_method("en caja")

        self.assertEqual(result["payment_method"], "CASH")
        self.assertEqual([event_type for event_type, _ in events], ["payment.method_selected"])
        event_cart = events[0][1]["cart"]
        self.assertEqual(event_cart["payment_method"], "CASH")
        self.assertEqual(event_cart["order_number"], result["order_number"])

    def test_return_to_payment_methods_tool_preserves_pending_order(self) -> None:
        """La tool de voz vuelve al selector sin habilitar modificaciones."""
        service = OrderService(load_menu("config/menu.json"), Session())
        service.add_item("BURGER_CLASICA", 1, {"drink": "WATER"})
        service.select_payment_method("CARD")
        order_number = service.session.order_number
        runtime = OrderToolsRuntime(service)

        result = runtime.execute(type("Call", (), {
            "name": "return_to_payment_methods",
            "args": {},
        })())

        self.assertTrue(result["ok"])
        self.assertEqual(service.session.state.value, "PAYMENT_PENDING")
        self.assertIsNone(service.session.payment_method)
        self.assertEqual(service.session.order_number, order_number)

    def test_groq_interpreter_uses_the_same_tool_and_service(self) -> None:
        """Groq simulado ejecuta tools sin asumir precios ni estado del dominio."""
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
        with patch("backend.ai.groq_llm_interpreter.create_groq_client", return_value=client):
            interpreter = GroqOrderInterpreter(service, "openai/gpt-oss-20b")
            response = interpreter.send_message("Quiero una Burger Clasica con Agua")
        self.assertNotIn("Agregue tu Burger Clasica con Agua.", response)
        self.assertIn("- Burger Clásica. Cantidad: una unidad.", response)
        self.assertNotIn("Precio unitario", response)
        self.assertIn("Bebida: Agua.", response)
        self.assertIn("agregar algún extra", response)
        self.assertIn("confirmar el pedido", response)
        self.assertEqual(response.count("¿Querés"), 1)
        self.assertEqual(service.get_cart().total, 8500)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(
            client.chat.completions.create.call_args_list[0].kwargs["max_tokens"],
            800,
        )

    def test_openai_interpreter_retries_an_incomplete_response_once(self) -> None:
        """Reprocesa un fragmento sin tools y aplica el pedido una sola vez."""
        service = OrderService(load_menu("config/menu.json"), Session())
        incomplete = type("Response", (), {"choices": [type("Choice", (), {
            "message": type("Message", (), {"content": "Agre", "tool_calls": []})(),
        })()]})()
        tool_response = type("Response", (), {"choices": [type("Choice", (), {
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
        complete = type("Response", (), {"choices": [type("Choice", (), {
            "message": type("Message", (), {
                "content": "Agregué tu Burger Clásica con agua.",
                "tool_calls": [],
            })(),
        })()]})()
        client = Mock()
        client.chat.completions.create.side_effect = [incomplete, tool_response, complete]

        with patch("backend.ai.openai_llm_interpreter.create_openai_client", return_value=client):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
            response = interpreter.send_message("Quiero una hamburguesa simple con agua")

        self.assertNotIn("Agregué tu Burger Clásica con agua.", response)
        self.assertIn("- Burger Clásica. Cantidad: una unidad.", response)
        self.assertNotIn("Precio unitario", response)
        self.assertIn("Bebida: Agua.", response)
        self.assertIn("agregar algún extra", response)
        self.assertIn("confirmar el pedido", response)
        self.assertEqual(response.count("¿Querés"), 1)
        self.assertEqual(service.get_cart().total, 8500)
        self.assertEqual(len(service.get_cart().items), 1)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_openai_interpreter_replaces_a_second_incomplete_response(self) -> None:
        """Evita exponer una cortesía aislada cuando el reintento tampoco sirve."""
        service = OrderService(load_menu("config/menu.json"), Session())
        responses = [
            type("Response", (), {"choices": [type("Choice", (), {
                "message": type("Message", (), {"content": text, "tool_calls": []})(),
            })()]})()
            for text in ("Con gusto", "Claro")
        ]
        client = Mock()
        client.chat.completions.create.side_effect = responses

        with patch("backend.ai.openai_llm_interpreter.create_openai_client", return_value=client):
            interpreter = OpenAIOrderInterpreter(service, "gpt-4.1-mini")
            response = interpreter.send_message("Quiero una hamburguesa simple con agua")

        self.assertIn("No pude completar", response)
        self.assertEqual(service.get_cart().total, 0)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_groq_factory_uses_only_the_groq_adapter(self) -> None:
        """LLM_PROVIDER=groq selecciona el adaptador sin crear Gemini u OpenAI."""
        service = OrderService(load_menu("config/menu.json"), Session())
        sentinel = object()
        with patch.dict(os.environ, {"LLM_PROVIDER": "groq"}, clear=False), \
             patch("backend.ai.factories.GroqOrderInterpreter", return_value=sentinel) as adapter:
            self.assertIs(create_order_interpreter(service), sentinel)
        adapter.assert_called_once_with(service=service, model=ANY)

    def test_vosk_factory_uses_local_model_path_without_cloud_key(self) -> None:
        """Selecciona Vosk con ruta local sin leer una credencial de Gemini."""
        sentinel = object()
        with patch.dict(
            os.environ,
            {"STT_PROVIDER": "vosk", "STT_MODEL_PATH": "models/test"},
            clear=False,
        ), patch(
            "backend.ai.factories.VoskTranscriber",
            return_value=sentinel,
        ) as adapter:
            self.assertIs(create_speech_to_text("session-test"), sentinel)
        adapter.assert_called_once_with(
            session_id="session-test",
            model_path="models/test",
        )

    def test_unimplemented_provider_fails_before_reading_its_credential(self) -> None:
        """Un proveedor futuro explica el límite sin requerir claves inexistentes."""
        with patch.dict(os.environ, {"STT_PROVIDER": "whisper", "LLM_PROVIDER": "anthropic"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "STT_PROVIDER='whisper'.*no tiene un adaptador"):
                create_speech_to_text()
            service = OrderService(load_menu("config/menu.json"), Session())
            with self.assertRaisesRegex(RuntimeError, "LLM_PROVIDER='anthropic'.*no tiene un adaptador"):
                create_order_interpreter(service)


if __name__ == "__main__":
    unittest.main()
