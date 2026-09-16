"""Logica comun de tools reutilizable por adaptadores LLM."""

import json
import re
from types import SimpleNamespace

from backend.ai.tools import (
    create_add_item_tool,
    create_change_modifier_tool,
    create_confirm_order_tool,
    create_get_cart_tool,
    create_remove_item_tool,
    create_replace_item_tool,
    create_return_to_order_tool,
    create_select_payment_method_tool,
)
from backend.logging.event_logger import log_event
from backend.services.order_service import OrderService


class OrderToolsRuntime:
    """Reune prompt, tools y validaciones sin depender de un proveedor LLM."""

    MUTATING_TOOLS = {"add_item", "change_modifier", "replace_item", "remove_item", "confirm_order", "select_payment_method", "return_to_order"}

    def __init__(self, service: OrderService) -> None:
        """Crea las tools ligadas a una sesion y su servicio real.

        Args:
            service: Autoridad transaccional de la sesion actual.
        """
        self.service = service
        self.available_tools = {
            "add_item": create_add_item_tool(service),
            "get_cart": create_get_cart_tool(service),
            "change_modifier": create_change_modifier_tool(service),
            "replace_item": create_replace_item_tool(service),
            "remove_item": create_remove_item_tool(service),
            "confirm_order": create_confirm_order_tool(service),
            "select_payment_method": create_select_payment_method_tool(service),
            "return_to_order": create_return_to_order_tool(service),
        }

    def build_system_instruction(self) -> str:
        """Construye el contexto de menu y reglas valido para cualquier LLM.

        Returns:
            Instruccion de sistema que limita al modelo a tools autorizadas.
        """
        catalog = []
        for product in self.service.menu.products.values():
            catalog.append(f"- {product.name}: product_id={product.id}, ARS {product.base_price}, {'disponible' if product.available else 'agotado'}")
            if product.aliases:
                catalog.append(f"  - Alias: {', '.join(product.aliases)}")
            for group in product.modifier_groups:
                options = ", ".join(f"{option.name} [id={option.id}] (+ARS {option.price_delta}, {'disponible' if option.available else 'agotado'})" for option in group.options)
                catalog.append(f"  - {group.name} [grupo={group.id}] ({'obligatorio' if group.required else 'opcional'}): {options}")
        return """Sos la interfaz conversacional de un autoservicio de pedidos.
Interpreta al usuario y usa tools solo cuando corresponde.
No inventes precios, descuentos, disponibilidad ni stock. OrderService y las tools son la autoridad.
No agregues ni reemplaces productos con modificadores obligatorios faltantes: pregunta antes.
No uses add_item para consultar precios o menu. Usa get_cart para consultar el pedido.
Usa change_modifier para modificar o quitar un adicional opcional, replace_item para cambiar producto y remove_item para quitar una linea.
confirm_order solo prepara pago. En PAYMENT_PENDING usa select_payment_method o return_to_order; no repitas confirm_order.
Para CASH di siempre "En caja". Para CARD indica que debe ingresar el numero de tarjeta.
Puedes solicitar varias tools distintas en una frase, pero nunca repitas la misma operacion con los mismos argumentos.
Responde siempre en espanol, con puntos de miles y "pesos argentinos". Nunca muestres IDs internos.

CATALOGO ACTUAL:
""" + "\n".join(catalog)

    def validate_calls(self, calls: list[SimpleNamespace], executed: set) -> None:
        """Evita repetir una operacion dentro del mismo turno.

        Args:
            calls: Tools propuestas por el proveedor actual.
            executed: Firmas ya ejecutadas en el turno.

        Raises:
            RuntimeError: Si una tool repite nombre y argumentos.
        """
        batch = set()
        for call in calls:
            signature = (call.name, json.dumps(call.args, sort_keys=True, ensure_ascii=False))
            if signature in executed or signature in batch:
                raise RuntimeError("El modelo intento repetir una operacion. Se detuvo para evitar duplicados.")
            batch.add(signature)

    def execute(self, call: SimpleNamespace) -> dict:
        """Ejecuta una tool autorizada y conserva errores de validacion.

        Args:
            call: Nombre y argumentos solicitados por el proveedor.

        Returns:
            Resultado estructurado de la tool sin ocultar una validacion fallida.

        Raises:
            RuntimeError: Si se solicita una tool fuera de la lista autorizada.
            Exception: Si ocurre una falla interna inesperada.
        """
        tool = self.available_tools.get(call.name)
        if tool is None:
            raise RuntimeError(f"Tool no autorizada: {call.name}")
        try:
            return {"ok": True, "result": tool(**call.args)}
        except ValueError as exc:
            log_event("WARN", "tool.validation_error", session_id=self.service.session.session_id, tool=call.name, arguments=call.args, error=str(exc))
            return {"ok": False, "error": str(exc)}

    def did_mutate(self, tool_name: str, result: dict) -> bool:
        """Indica si un resultado de tool cambio el estado del pedido.

        Args:
            tool_name: Tool que se ejecuto.
            result: Resultado estructurado de su ejecucion.

        Returns:
            True si la operacion aplico una mutacion real.
        """
        if not result.get("ok") or tool_name not in self.MUTATING_TOOLS:
            return False
        payload = result.get("result", {})
        if tool_name == "add_item":
            return payload.get("status") == "added"
        if tool_name == "confirm_order":
            return payload.get("status") != "payment_pending"
        return True

    def sanitize_user_text(self, text: str) -> str:
        """Oculta IDs tecnicos y formatos monetarios no aptos para el usuario.

        Args:
            text: Respuesta textual generada por el modelo.

        Returns:
            Texto visible con nombres del menu y pesos argentinos.
        """
        replacements = []
        for product in self.service.menu.products.values():
            replacements.append((product.id, product.name))
            for group in product.modifier_groups:
                replacements.append((group.id, group.name))
                replacements.extend((option.id, option.name) for option in group.options)
        for pattern, replacement in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
            text = re.sub(rf"\b{re.escape(pattern)}\b", replacement, text)
        text = re.sub(r"\$\s*([0-9][0-9.]*)", r"\1 pesos argentinos", text)
        text = re.sub(r"\bUSD\b|\bdolares?\b", "pesos argentinos", text, flags=re.IGNORECASE)
        return re.sub(r"\befectivo\b", "en caja", text, flags=re.IGNORECASE)
