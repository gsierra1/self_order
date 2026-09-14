"""Invariantes del pedido reutilizadas por los canales de texto y voz."""

import unittest
from dataclasses import asdict
from unittest.mock import patch

from backend.ai.tools import create_add_item_tool
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
