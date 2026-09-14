"""Invariantes del pedido reutilizadas por los canales de texto y voz."""

import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.ai.tools import create_add_item_tool
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
        self.options = {"size": "LARGE", "drink": "COCA"}

    def tearDown(self) -> None:
        """Restaura el logging original después de cada prueba."""
        self.log_patch.stop()

    def test_missing_modifiers_do_not_add(self) -> None:
        """La tool informa qué falta y el carrito permanece vacío."""
        result = create_add_item_tool(self.service)("COMBO_BIG_MAC", size="LARGE")
        self.assertEqual(result["missing_fields"], ["drink"])
        self.assertFalse(self.service.get_cart().items)

    def test_unknown_and_unavailable_product_do_not_add(self) -> None:
        """El servicio rechaza productos fuera de catálogo o indisponibles."""
        with self.assertRaises(ValueError):
            self.service.add_item("PIZZA", 1, self.options)
        self.service.menu.get_product("COMBO_BIG_MAC").available = False
        with self.assertRaises(ValueError):
            self.service.add_item("COMBO_BIG_MAC", 1, self.options)
        self.assertFalse(self.service.get_cart().items)

    def test_replacement_validates_before_mutating(self) -> None:
        """Un reemplazo inválido conserva línea, configuración y precio originales."""
        item = self.service.add_item("COMBO_BIG_MAC", 2, self.options)
        previous = asdict(item)
        with self.assertRaises(ValueError):
            self.service.replace_item(item.line_id, "COMBO_QUARTER_POUNDER", {})
        self.assertEqual(asdict(item), previous)
        self.assertEqual(self.service.get_cart().total, 25000)

    def test_confirmation_blocks_later_changes(self) -> None:
        """Confirmar exige carrito no vacío y bloquea operaciones posteriores."""
        with self.assertRaises(ValueError):
            self.service.confirm_order()
        self.service.add_item("COMBO_BIG_MAC", 1, self.options)
        self.service.confirm_order()
        with self.assertRaises(ValueError):
            self.service.remove_item(1)

    def test_user_text_hides_internal_modifier_ids_and_dollars(self) -> None:
        """La salida pública usa nombres y moneda argentinos, nunca códigos internos."""
        text = OrderConversationOrchestrator._sanitize_user_text(
            "Elegiste Medium ($12.500) en lugar de LARGE; no es USD."
        )
        self.assertEqual(
            text,
            "Elegiste Mediano (12.500 pesos argentinos) en lugar de Grande; "
            "no es pesos argentinos.",
        )

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
                        "product_id": "COMBO_BIG_MAC",
                        "size": "LARGE",
                        "drink": "COCA",
                    },
                ),
                SimpleNamespace(
                    name="add_item",
                    args={
                        "product_id": "COMBO_QUARTER_POUNDER",
                        "size": "MEDIUM",
                        "drink": "SPRITE",
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
            "Agregá un Big Mac grande con Coca y un Cuarto de Libra mediano "
            "con Sprite."
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
                    "product_id": "COMBO_BIG_MAC",
                    "size": "LARGE",
                    "drink": "COCA",
                },
            )
        ]

        with self.assertRaises(RuntimeError):
            orchestrator._validate_function_calls(calls + calls, set())

        self.assertFalse(self.service.get_cart().items)

    def test_payment_demo_requires_method_before_closing_session(self) -> None:
        """Genera pedido, método y cierre en tres estados controlados."""
        self.service.add_item("COMBO_BIG_MAC", 1, self.options)

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
            self.service.add_item("COMBO_BIG_MAC", 1, self.options)
