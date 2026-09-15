"""Invariantes del pedido reutilizadas por los canales de texto y voz."""

import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.ai.tools import create_add_item_tool, create_confirm_order_tool
from backend.ai.errors import classify_gemini_api_error
from backend.ai.orchestrator import OrderConversationOrchestrator
from backend.domain.menu import load_menu
from backend.domain.session import Session
from backend.services.order_service import OrderService


class OrderRulesTests(unittest.TestCase):
    """Protege las reglas transaccionales al agregar un canal de entrada."""

    def setUp(self) -> None:
        """Crea un menú independiente y evita registrar datos sintéticos en logs."""
        self.log_patch = patch("backend.logging.event_logger.LOGGER.disabled", True)
        self.log_patch.start()
        self.service = OrderService(load_menu("config/menu.json"), Session())
        self.options = {"drink": "COCA"}

    def tearDown(self) -> None:
        """Restaura el logging original después de cada prueba."""
        self.log_patch.stop()

    def test_missing_modifiers_do_not_add(self) -> None:
        """La tool informa qué falta y el carrito permanece vacío."""
        result = create_add_item_tool(self.service)("BURGER_CLASICA")
        self.assertEqual(
            result["missing_modifier_groups"],
            [{"id": "drink", "name": "Bebida"}],
        )
        self.assertFalse(self.service.get_cart().items)

    def test_unknown_and_unavailable_product_do_not_add(self) -> None:
        """El servicio rechaza productos fuera de catálogo o indisponibles."""
        with self.assertRaises(ValueError):
            self.service.add_item("PIZZA", 1, self.options)
        self.service.menu.get_product("BURGER_CLASICA").available = False
        with self.assertRaises(ValueError):
            self.service.add_item("BURGER_CLASICA", 1, self.options)
        self.assertFalse(self.service.get_cart().items)

    def test_replacement_validates_before_mutating(self) -> None:
        """Un reemplazo inválido conserva línea, configuración y precio originales."""
        item = self.service.add_item("BURGER_CLASICA", 2, self.options)
        previous = asdict(item)
        with self.assertRaises(ValueError):
            self.service.replace_item(item.line_id, "BURGER_DOBLE", {})
        self.assertEqual(asdict(item), previous)
        self.assertEqual(self.service.get_cart().total, 17000)

    def test_confirmation_blocks_later_changes(self) -> None:
        """Confirmar exige carrito no vacío y bloquea operaciones posteriores."""
        with self.assertRaises(ValueError):
            self.service.confirm_order()
        self.service.add_item("BURGER_CLASICA", 1, self.options)
        self.service.confirm_order()
        with self.assertRaises(ValueError):
            self.service.remove_item(1)

    def test_user_text_hides_internal_modifier_ids_and_dollars(self) -> None:
        """La salida pública usa nombres y moneda argentinos, nunca códigos internos."""
        orchestrator = OrderConversationOrchestrator.__new__(
            OrderConversationOrchestrator
        )
        orchestrator.service = self.service
        text = orchestrator._sanitize_user_text(
            "Elegiste ADD_CHEESE ($9.500) en BURGER_CLASICA; no es USD."
        )
        self.assertEqual(
            text,
            "Elegiste Queso (9.500 pesos argentinos) en Burger Clásica; "
            "no es pesos argentinos.",
        )

    def test_optional_extras_accumulate_and_can_be_removed(self) -> None:
        """Suma extras opcionales y conserva la bebida obligatoria."""
        item = self.service.add_item(
            "BURGER_CLASICA",
            1,
            {
                "drink": "COCA",
                "extra_tomato": "ADD_TOMATO",
                "extra_cheese": "ADD_CHEESE",
            },
        )
        self.assertEqual(item.unit_price, 10500)
        updated = self.service.change_modifier(
            item.line_id,
            "extra_tomato",
            None,
        )
        self.assertEqual(updated.unit_price, 9500)
        self.assertNotIn("extra_tomato", updated.selected_modifiers)

    def test_catalog_exposes_aliases_and_visible_price_details(self) -> None:
        """Mantiene aliases conversacionales y precios para el carrito visible."""
        product = self.service.menu.get_product("BURGER_CLASICA")
        self.assertIn("hamburguesa simple", product.aliases)
        details = self.service.menu.get_modifier_details(
            "BURGER_CLASICA",
            {"drink": "COCA", "extra_cheese": "ADD_CHEESE"},
        )
        self.assertEqual(
            details,
            [
                {
                    "group_name": "Bebida",
                    "option_name": "Coca-Cola",
                    "price_delta": 0,
                },
                {
                    "group_name": "Extra de queso",
                    "option_name": "Queso",
                    "price_delta": 1000,
                },
            ],
        )

    def test_unknown_modifier_group_does_not_add(self) -> None:
        """Rechaza grupos no definidos antes de alterar el carrito."""
        with self.assertRaises(ValueError):
            self.service.add_item(
                "BURGER_CLASICA",
                1,
                {"drink": "COCA", "unknown": "VALUE"},
            )
        self.assertFalse(self.service.get_cart().items)

    def test_orchestrator_executes_multiple_requested_operations(self) -> None:
        """Ejecuta dos tools distintas del mismo turno en el orden recibido."""
        orchestrator = OrderConversationOrchestrator.__new__(
            OrderConversationOrchestrator
        )
        orchestrator.service = self.service
        orchestrator.max_tool_rounds = 5
        orchestrator.available_tools = orchestrator._create_tools()
        first_response = SimpleNamespace(
            function_calls=[
                SimpleNamespace(
                    name="add_item",
                    args={
                        "product_id": "BURGER_CLASICA",
                        "selected_modifiers": {
                            "drink": "COCA",
                            "extra_cheese": "ADD_CHEESE",
                        },
                    },
                ),
                SimpleNamespace(
                    name="add_item",
                    args={
                        "product_id": "BURGER_DOBLE",
                        "selected_modifiers": {"drink": "SPRITE"},
                    },
                ),
            ],
            text=None,
        )
        final_response = SimpleNamespace(function_calls=[], text="Listo")
        orchestrator._send_to_gemini = Mock(
            side_effect=[first_response, final_response]
        )

        response = orchestrator.send_message(
            "Agregá una clásica con queso y Coca, y una doble con Sprite."
        )

        self.assertEqual(response, "Listo")
        self.assertEqual(len(self.service.get_cart().items), 2)
        self.assertEqual(orchestrator._send_to_gemini.call_count, 2)

    def test_orchestrator_rejects_duplicate_operation_in_batch(self) -> None:
        """No ejecuta un lote que repite exactamente la misma operación."""
        orchestrator = OrderConversationOrchestrator.__new__(
            OrderConversationOrchestrator
        )
        orchestrator.service = self.service
        calls = [
            SimpleNamespace(
                name="add_item",
                args={
                    "product_id": "BURGER_CLASICA",
                    "selected_modifiers": {"drink": "COCA"},
                },
            )
        ]

        with self.assertRaises(RuntimeError):
            orchestrator._validate_function_calls(calls + calls, set())

        self.assertFalse(self.service.get_cart().items)

    def test_payment_demo_requires_method_before_closing_session(self) -> None:
        """Genera pedido, método y cierre en tres estados controlados."""
        self.service.add_item("BURGER_CLASICA", 1, self.options)

        pending = self.service.prepare_payment()
        self.assertEqual(self.service.session.state.value, "PAYMENT_PENDING")
        self.assertRegex(pending["order_number"], r"^\d{6}$")
        with self.assertRaises(ValueError):
            self.service.complete_payment()

        selected = self.service.select_payment_method("QR")
        self.assertEqual(selected["payment_method"], "QR")
        completed = self.service.complete_payment()
        self.assertEqual(completed["status"], "confirmed")
        self.assertEqual(self.service.session.state.value, "CONFIRMED")
        with self.assertRaises(ValueError):
            self.service.add_item("BURGER_CLASICA", 1, self.options)

    def test_repeated_payment_confirmation_preserves_pending_order(self) -> None:
        """Una confirmación repetida no cambia ni duplica el pedido pendiente."""
        self.service.add_item("BURGER_CLASICA", 1, self.options)
        first = create_confirm_order_tool(self.service)()

        repeated = create_confirm_order_tool(self.service)()

        self.assertEqual(repeated["status"], "payment_pending")
        self.assertEqual(repeated["order_number"], first["order_number"])
        self.assertEqual(self.service.session.state.value, "PAYMENT_PENDING")

    def test_missing_model_error_names_model_and_voice_operation(self) -> None:
        """La clasificación de 404 explica qué modelo de voz debe corregirse."""
        api_error = SimpleNamespace(
            code=404,
            status="NOT_FOUND",
            message="Model not found",
        )

        result = classify_gemini_api_error(
            api_error,
            model="gemini-3.6-transcribe-live",
            stage="VOICE_TRANSCRIPTION",
            transaction_applied=False,
        )

        self.assertEqual(result.error_type, "MODEL_NOT_FOUND")
        self.assertIn("gemini-3.6-transcribe-live", result.user_message)
        self.assertIn("transcripción en vivo", result.user_message)

    def test_payment_back_restores_editable_order(self) -> None:
        """La vuelta desde pago conserva el carrito y permite modificarlo."""
        self.service.add_item("BURGER_CLASICA", 1, self.options)
        self.service.prepare_payment()
        self.service.select_payment_method("CARD")

        result = self.service.return_to_order()

        self.assertEqual(result["status"], "order_editing")
        self.assertEqual(self.service.session.state.value, "ACTIVE")
        self.assertIsNone(self.service.session.order_number)
        self.service.remove_item(1)
        self.assertFalse(self.service.get_cart().items)
