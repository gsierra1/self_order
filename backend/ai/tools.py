"""Adaptadores entre las tools de Gemini y las reglas de OrderService."""

from backend.services.order_service import OrderService


def _get_missing_required_groups(
    service: OrderService,
    product_id: str,
    selected_modifiers: dict[str, str],
) -> list[dict[str, str]]:
    """Identifica los grupos obligatorios aún no elegidos.

    Args:
        service: Servicio que conserva el catálogo de la sesión.
        product_id: Identificador técnico del producto solicitado.
        selected_modifiers: Opciones ya expresadas por la persona.

    Returns:
        Grupos faltantes con identificador y nombre visible. Si el producto no
        existe, devuelve una lista vacía para que ``OrderService`` informe el
        error correspondiente.
    """
    product = service.menu.get_product(product_id)

    if product is None:
        return []

    return [
        {"id": group.id, "name": group.name}
        for group in product.modifier_groups
        if group.required and group.id not in selected_modifiers
    ]


def _serialize_item_result(
    service: OrderService,
    item,
    status: str | None = None,
) -> dict:
    """Construye una respuesta uniforme para una línea mutada por una tool.

    Args:
        service: Servicio que aporta el total actualizado.
        item: Línea validada por ``OrderService``.
        status: Estado semántico opcional de la operación.

    Returns:
        Datos de la línea y total actual aptos para devolver a Gemini.
    """
    result = {
        "line_id": item.line_id,
        "product_id": item.product_id,
        "product_name": item.product_name,
        "quantity": item.quantity,
        "selected_modifiers": item.selected_modifiers,
        "unit_price": item.unit_price,
        "cart_total": service.get_cart().total,
    }

    if status is not None:
        result["status"] = status

    return result


def create_add_item_tool(service: OrderService):
    """Crea la tool para agregar productos con modificadores del catálogo.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini que no agrega una línea incompleta.
    """

    def add_item(
        product_id: str,
        quantity: int = 1,
        selected_modifiers: dict[str, str] | None = None,
    ) -> dict:
        """Intenta agregar un producto solo cuando la configuración es completa.

        Args:
            product_id: Identificador interno del producto definido en menú.
            quantity: Cantidad de unidades idénticas solicitadas.
            selected_modifiers: Opciones indicadas explícitamente, indexadas
                por grupo. Puede ser ``None`` mientras falten datos.

        Returns:
            Línea agregada y total, o grupos obligatorios faltantes sin mutar
            el carrito.

        Raises:
            ValueError: Si producto, cantidad o modificadores no son válidos.
        """
        modifiers = selected_modifiers or {}
        missing_groups = _get_missing_required_groups(
            service,
            product_id,
            modifiers,
        )

        if missing_groups:
            return {
                "status": "needs_clarification",
                "product_id": product_id,
                "quantity": quantity,
                "missing_modifier_groups": missing_groups,
                "message": (
                    "Faltan modificadores obligatorios. Deben preguntarse "
                    "explícitamente antes de agregar el producto."
                ),
            }

        item = service.add_item(product_id, quantity, modifiers)
        return _serialize_item_result(service, item, "added")

    return add_item


def create_get_cart_tool(service: OrderService):
    """Crea la tool de consulta del carrito real.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def get_cart() -> dict:
        """Obtiene las líneas validadas y el total actual.

        Returns:
            Carrito real mantenido por el backend.
        """
        cart = service.get_cart()
        return {
            "items": [
                _serialize_item_result(service, item)
                for item in cart.items
            ],
            "total": cart.total,
        }

    return get_cart


def create_change_modifier_tool(service: OrderService):
    """Crea la tool que cambia o quita una opción de un grupo.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def change_modifier(
        line_id: int,
        modifier_group_id: str,
        option_id: str | None = None,
    ) -> dict:
        """Cambia una selección o quita una opción opcional.

        Args:
            line_id: Identificador de la línea que se desea modificar.
            modifier_group_id: Grupo de modificadores definido en menú.
            option_id: Nueva opción. ``None`` quita una selección opcional.

        Returns:
            Línea actualizada y total actual del carrito.

        Raises:
            ValueError: Si la línea, el grupo o la opción no son válidos.
        """
        item = service.change_modifier(line_id, modifier_group_id, option_id)
        return _serialize_item_result(service, item)

    return change_modifier


def create_replace_item_tool(service: OrderService):
    """Crea la tool que reemplaza un producto sin perder la línea original.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def replace_item(
        line_id: int,
        new_product_id: str,
        selected_modifiers: dict[str, str] | None = None,
    ) -> dict:
        """Reemplaza un producto cuando están elegidos sus grupos obligatorios.

        Args:
            line_id: Línea que se desea reemplazar.
            new_product_id: Identificador interno del producto de destino.
            selected_modifiers: Opciones indicadas para el producto de destino.

        Returns:
            Línea reemplazada y total, o grupos faltantes sin modificar la
            línea original.

        Raises:
            ValueError: Si la línea, producto o configuración no son válidos.
        """
        modifiers = selected_modifiers or {}
        missing_groups = _get_missing_required_groups(
            service,
            new_product_id,
            modifiers,
        )

        if missing_groups:
            return {
                "status": "needs_clarification",
                "product_id": new_product_id,
                "missing_modifier_groups": missing_groups,
                "message": (
                    "Faltan modificadores obligatorios. Deben preguntarse "
                    "explícitamente antes de reemplazar el producto."
                ),
            }

        item = service.replace_item(line_id, new_product_id, modifiers)
        return _serialize_item_result(service, item, "replaced")

    return replace_item


def create_remove_item_tool(service: OrderService):
    """Crea la tool que elimina una línea del carrito.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def remove_item(line_id: int) -> dict:
        """Elimina una línea validada del pedido.

        Args:
            line_id: Identificador de la línea que se desea eliminar.

        Returns:
            Línea eliminada y total actualizado.

        Raises:
            ValueError: Si no existe una línea con ese identificador.
        """
        item = service.remove_item(line_id)
        return {
            "removed_item": _serialize_item_result(service, item),
            "cart_total": service.get_cart().total,
        }

    return remove_item


def create_confirm_order_tool(service: OrderService):
    """Crea la tool que inicia el pago de demostración.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def confirm_order() -> dict:
        """Prepara el pedido para elegir un método de pago.

        Returns:
            Estado de pago pendiente y número de pedido.

        Raises:
            ValueError: Si el carrito está vacío o la sesión no es editable.
        """
        return service.prepare_payment()

    return confirm_order


def create_select_payment_method_tool(service: OrderService):
    """Crea la tool para seleccionar QR, tarjeta o pago en caja.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def select_payment_method(method: str) -> dict:
        """Selecciona el método de pago del pedido pendiente.

        Args:
            method: Método ``QR``, ``CARD`` o ``CASH``.

        Returns:
            Método seleccionado y número de pedido.

        Raises:
            ValueError: Si el estado o método no son válidos.
        """
        return service.select_payment_method(method)

    return select_payment_method


def create_return_to_order_tool(service: OrderService):
    """Crea la tool que vuelve desde pago a la edición del pedido.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para Gemini.
    """

    def return_to_order() -> dict:
        """Cancela la selección de pago y conserva el carrito.

        Returns:
            Estado del pedido nuevamente editable.

        Raises:
            ValueError: Si no hay un pago pendiente.
        """
        return service.return_to_order()

    return return_to_order
