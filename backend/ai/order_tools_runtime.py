"""Logica comun de tools reutilizable por adaptadores LLM."""

import json
import re
from types import SimpleNamespace

from backend.ai.tools import (
    create_add_item_tool,
    create_adjust_quantity_tool,
    create_change_modifier_tool,
    create_clear_cart_tool,
    create_confirm_order_tool,
    create_get_cart_tool,
    create_remove_item_tool,
    create_replace_item_tool,
    create_return_to_order_tool,
    create_return_to_payment_methods_tool,
    create_select_payment_method_tool,
)
from backend.domain.session import SessionState
from backend.logging.event_logger import log_event
from backend.services.order_service import OrderService


class OrderToolsRuntime:
    """Reune prompt, tools y validaciones sin depender de un proveedor LLM."""

    MUTATING_TOOLS = {"add_item", "adjust_quantity", "change_modifier", "replace_item", "remove_item", "clear_cart", "confirm_order", "select_payment_method", "return_to_order", "return_to_payment_methods"}

    def __init__(self, service: OrderService) -> None:
        """Crea las tools ligadas a una sesion y su servicio real.

        Args:
            service: Autoridad transaccional de la sesion actual.
        """
        self.service = service
        self.available_tools = {
            "add_item": create_add_item_tool(service),
            "adjust_quantity": create_adjust_quantity_tool(service),
            "get_cart": create_get_cart_tool(service),
            "change_modifier": create_change_modifier_tool(service),
            "replace_item": create_replace_item_tool(service),
            "remove_item": create_remove_item_tool(service),
            "clear_cart": create_clear_cart_tool(service),
            "confirm_order": create_confirm_order_tool(service),
            "select_payment_method": create_select_payment_method_tool(service),
            "return_to_order": create_return_to_order_tool(service),
            "return_to_payment_methods": create_return_to_payment_methods_tool(service),
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
No inventes precios, descuentos, disponibilidad, stock, productos, grupos, variantes ni opciones. OrderService, las tools y el CATALOGO ACTUAL son la autoridad.
Solo pregunta por grupos obligatorios que existan en el CATALOGO ACTUAL y que el usuario todavia no haya respondido. Al preguntar, ofrece unicamente opciones listadas para ese grupo.
Si el usuario ya indico un producto y todos sus grupos obligatorios mediante nombres o aliases del catalogo, usa add_item inmediatamente. No preguntes subtipos, presentaciones ni distinciones ausentes del catalogo.
No agregues ni reemplaces productos con modificadores obligatorios faltantes: pregunta antes.
No uses add_item para consultar precios o menu. Usa get_cart para consultar el pedido.
Usa change_modifier para modificar o quitar un adicional opcional y replace_item para cambiar producto.
Usa adjust_quantity con delta=-1 si la persona pide quitar una unidad de una línea con varias unidades. Usa remove_item solamente si pide eliminar toda la línea y clear_cart para vaciar todo el carrito de una sola vez.
confirm_order solo prepara pago. En PAYMENT_PENDING usa select_payment_method o return_to_order; no repitas confirm_order.
Si ya hay un método y la persona quiere ver o cambiar las opciones de pago, usa return_to_payment_methods. Usa return_to_order solamente si quiere modificar los productos del carrito.
Para CASH di siempre "En caja". Para CARD indica que debe ingresar el numero de tarjeta.
No uses tablas Markdown ni numeres líneas o alternativas: presentá el carrito como una lista directa.
Nunca digas solamente "el carrito queda así" o "queda de esta forma": enumerá
el contenido real o preguntá explícitamente el modificador obligatorio faltante.
No respondas con fragmentos ni cortesías aisladas: ejecutá la tool necesaria o
formulá una pregunta completa cuando falte un dato obligatorio.
No describas productos como "la opción mejor" ni agregues valoraciones no solicitadas.
Puedes solicitar varias tools distintas en una frase, pero nunca repitas la misma operacion con los mismos argumentos.
Responde siempre en espanol. Mostrá los montos como "$12.500 pesos argentinos": símbolo $, punto de miles y moneda explícita. Nunca muestres IDs internos.

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
        """Oculta IDs técnicos y normaliza moneda para el usuario.

        Args:
            text: Respuesta textual generada por el modelo.

        Returns:
            Texto visible con nombres del menú, pesos argentinos y separadores
            de miles uniformes, incluidas las comas y los separadores Unicode
            generados por algunos modelos.
        """
        replacements = []
        for product in self.service.menu.products.values():
            replacements.append((product.id, product.name))
            for group in product.modifier_groups:
                replacements.append((group.id, group.name))
                replacements.extend((option.id, option.name) for option in group.options)
        for pattern, replacement in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
            text = re.sub(rf"\b{re.escape(pattern)}\b", replacement, text)
        text = re.sub(r"(?<=\d)[\u00a0\u202f ](?=\d)", ".", text)
        text = re.sub(r"(?<=\d),(?=\d{3}\b)", ".", text)
        text = re.sub(
            r"(?:\$|\bARS\b)\s*([0-9][0-9.]*)\s*(?:pesos argentinos)?",
            r"\1 pesos argentinos",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\bUSD\b|\bdolares?\b", "pesos argentinos", text, flags=re.IGNORECASE)
        text = re.sub(r"\befectivo\b", "en caja", text, flags=re.IGNORECASE)
        text = re.sub(r"\betc\.?\b", "etcétera", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*\(la opción\s+[\"“']?mejor[\"”']?\)", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?<![\w$])(\d+(?:\.\d{3})*)\s+pesos argentinos",
            r"$\1 pesos argentinos",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(pesos argentinos)(?=\d+[.)]\s)",
            r"\1\n",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(pesos argentinos)(?=[A-ZÁÉÍÓÚ¿])",
            r"\1. ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"(?<![\d.])\b\d+[.)](?=\s)", "", text)
        text = re.sub(r"[*`]+", "", text)
        normalized = self._normalize_cart_tables(text)
        if re.search(
            r"\b(?:queda|quedó|quedo|está|esta)\s+(?:así|asi)\s*[:.!?]*\s*$",
            normalized,
            flags=re.IGNORECASE,
        ):
            return self._build_cart_summary()
        return normalized

    def ensure_next_step(self, text: str, transaction_applied: bool) -> str:
        """Reemplaza la redacción libre por un resumen y una continuación únicos.

        Args:
            text: Respuesta normalizada del proveedor, conservada si el turno no
                modificó un carrito activo.
            transaction_applied: Indica si el turno cambió realmente el pedido.

        Returns:
            Respuesta original o resumen determinista con extras, continuidad y
            confirmación según el carrito validado.
        """
        cart = self.service.get_cart()
        if cart.items and re.search(
            r"\bcarrito\b.{0,60}\bvac[ií]o\b",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            return self.get_cart_summary()
        if (
            not transaction_applied
            or self.service.session.state is not SessionState.ACTIVE
            or not cart.items
        ):
            return text

        has_available_extra = any(
            not group.required
            and group.id not in item.selected_modifiers
            and any(option.available for option in group.options)
            for item in cart.items
            for group in self.service.menu.get_product(item.product_id).modifier_groups
        )
        summary = "Pedido actualizado.\n" + self.get_cart_summary()
        if has_available_extra:
            question = (
                "¿Querés agregar algún extra, pedir algo más o confirmar el pedido?"
            )
        else:
            question = "¿Querés pedir algo más o confirmar el pedido?"
        return f"{summary}\n{question}"

    def get_cart_summary(self) -> str:
        """Expone un resumen construido desde el carrito validado.

        Returns:
            Descripción visible de las líneas, sus modificadores y el total real.
        """
        return self._build_cart_summary()

    def get_post_mutation_response(self, tool_name: str | None) -> str:
        """Construye una respuesta sin pedir otra redacción al proveedor LLM.

        Args:
            tool_name: Última tool que modificó el pedido durante el turno.

        Returns:
            Confirmación basada en el estado validado, el carrito y la etapa de
            pago actual.
        """
        if self.service.session.state is SessionState.PAYMENT_PENDING:
            if tool_name == "return_to_payment_methods":
                return "Podés elegir QR, tarjeta o en caja."
            if tool_name == "select_payment_method":
                labels = {"QR": "QR", "CARD": "tarjeta", "CASH": "caja"}
                method = self.service.session.payment_method
                return f"Seleccioné el pago en {labels.get(method, 'el método indicado')}."
            return "Pedido preparado. Elegí QR, tarjeta o en caja."
        if tool_name == "clear_cart":
            return "El carrito quedó vacío. Podés empezar un nuevo pedido."
        return self.ensure_next_step("", True)

    def _build_cart_summary(self) -> str:
        """Construye una descripción visible desde el carrito validado.

        Returns:
            Resumen con productos, modificadores y total, o una aclaración si
            todavía no existe ninguna línea validada.
        """
        cart = self.service.get_cart()
        if not cart.items:
            return (
                "El carrito sigue vacío. Todavía no se aplicó ningún cambio; "
                "indicame los datos obligatorios que faltan para agregar el producto."
            )
        lines: list[str] = []
        for item in cart.items:
            details = self.service.menu.get_modifier_details(
                item.product_id,
                item.selected_modifiers,
            )
            required_details = [detail for detail in details if detail["required"]]
            optional_details = [detail for detail in details if not detail["required"]]
            quantity = (
                "una unidad"
                if item.quantity == 1
                else f"{item.quantity} unidades"
            )
            lines.append(f"- {item.product_name}. Cantidad: {quantity}.")
            lines.extend(
                f"  {detail['group_name']}: {detail['option_name']}."
                for detail in required_details
            )
            if optional_details:
                extras = ", ".join(
                    detail["option_name"] for detail in optional_details
                )
                lines.append(f"  Extras: {extras}.")
        total = f"{cart.total:,}".replace(",", ".")
        return "Tu carrito contiene:\n" + "\n".join(lines) + f"\nTotal: ${total} pesos argentinos."

    def _normalize_cart_tables(self, text: str) -> str:
        """Convierte tablas Markdown del carrito en una lista legible.

        Args:
            text: Respuesta del intérprete que puede contener una tabla Markdown.

        Returns:
            Texto con las filas del carrito expresadas como líneas descriptivas.
        """
        lines = text.splitlines()
        normalized: list[str] = []
        index = 0
        while index < len(lines):
            current = lines[index]
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if "|" not in current or not re.search(r"\|?\s*:?-{3,}", next_line):
                normalized.append(current)
                index += 1
                continue
            headers = [cell.strip() for cell in current.strip().strip("|").split("|")]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if len(cells) >= len(headers) and len(cells) >= 5:
                    normalized.append(
                        f"{cells[1]} (cantidad: {cells[2]}; "
                        f"modificadores: {cells[3]}; precio unitario: {cells[4]})."
                    )
                else:
                    normalized.append(lines[index])
                index += 1
        return "\n".join(normalized)
