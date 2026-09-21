"""Metadatos neutrales de las tools disponibles para cualquier proveedor LLM."""

from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderToolSpec:
    """Describe una operación sin depender del SDK que la publicará.

    Attributes:
        name: Nombre estable usado para ejecutar la tool.
        description: Explicación breve entregada al modelo.
        properties: Parámetros expresados como propiedades JSON Schema.
        required: Parámetros que el proveedor debe exigir.
    """

    name: str
    description: str
    properties: dict
    required: tuple[str, ...] = ()

    def json_schema(self) -> dict:
        """Construye el esquema completo de parámetros de la operación.

        Returns:
            Copia independiente del JSON Schema neutral de la tool.
        """
        return {
            "type": "object",
            "properties": deepcopy(self.properties),
            "required": list(self.required),
            "additionalProperties": False,
        }


STRING_MAP_SCHEMA = {
    "type": "object",
    "additionalProperties": {"type": "string"},
}


ORDER_TOOL_SPECS = (
    OrderToolSpec(
        "add_item",
        "Agrega un producto completo al carrito.",
        {
            "product_id": {"type": "string"},
            "quantity": {"type": "integer", "minimum": 1},
            "selected_modifiers": STRING_MAP_SCHEMA,
        },
        ("product_id",),
    ),
    OrderToolSpec(
        "adjust_quantity",
        "Suma o resta unidades de una línea sin eliminarla completa.",
        {
            "line_id": {"type": "integer"},
            "delta": {
                "type": "integer",
                "description": "Variación relativa; -1 quita una unidad.",
            },
        },
        ("line_id", "delta"),
    ),
    OrderToolSpec("get_cart", "Consulta el carrito validado.", {}),
    OrderToolSpec(
        "change_modifier",
        "Cambia o quita un modificador de una línea.",
        {
            "line_id": {"type": "integer"},
            "modifier_group_id": {"type": "string"},
            "option_id": {"type": ["string", "null"]},
        },
        ("line_id", "modifier_group_id"),
    ),
    OrderToolSpec(
        "replace_item",
        "Reemplaza una línea por otro producto.",
        {
            "line_id": {"type": "integer"},
            "new_product_id": {"type": "string"},
            "selected_modifiers": STRING_MAP_SCHEMA,
        },
        ("line_id", "new_product_id"),
    ),
    OrderToolSpec(
        "remove_item",
        "Elimina una línea completa del carrito.",
        {"line_id": {"type": "integer"}},
        ("line_id",),
    ),
    OrderToolSpec(
        "clear_cart",
        "Elimina todas las líneas del carrito en una sola operación.",
        {},
    ),
    OrderToolSpec(
        "confirm_order",
        "Prepara el pedido para seleccionar el medio de pago.",
        {},
    ),
    OrderToolSpec(
        "select_payment_method",
        "Selecciona QR, tarjeta o pago en caja.",
        {"method": {"type": "string", "enum": ["QR", "CARD", "CASH"]}},
        ("method",),
    ),
    OrderToolSpec(
        "return_to_order",
        "Vuelve a editar el carrito desde la etapa de pago.",
        {},
    ),
    OrderToolSpec(
        "return_to_payment_methods",
        "Descarta el método elegido y vuelve al selector de pago.",
        {},
    ),
)
