from backend.services.order_service import OrderService


def create_add_item_tool(service: OrderService):
    """
    Crea una función que permite a Gemini agregar productos al carrito.

    La tool admite modificadores incompletos para poder representar solicitudes
    del usuario en las que todavía falta información obligatoria. Si no se
    especifica tamaño o bebida, la función informa qué datos faltan y no
    modifica el carrito.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para ser utilizada como tool de Gemini.
    """

    def add_item(
        product_id: str,
        quantity: int = 1,
        size: str | None = None,
        drink: str | None = None,
    ) -> dict:
        """
        Intenta agregar un producto del menú al carrito de la sesión actual.

        El producto solamente se agrega cuando se conocen todos los
        modificadores obligatorios. La función nunca asigna automáticamente
        tamaño o bebida cuando el usuario no los especificó.

        Args:
            product_id: Identificador interno del producto, por ejemplo
                "COMBO_BIG_MAC" o "COMBO_QUARTER_POUNDER".
            quantity: Cantidad de unidades idénticas que se desean agregar.
                Si el usuario pide un producto en singular, puede utilizarse 1.
            size: Tamaño explícitamente seleccionado por el usuario.
                Los valores disponibles actualmente son "MEDIUM" y "LARGE".
                Debe ser None si el usuario todavía no indicó un tamaño.
            drink: Bebida explícitamente seleccionada por el usuario.
                Los valores disponibles actualmente son "COCA" y "SPRITE".
                Debe ser None si el usuario todavía no indicó una bebida.

        Returns:
            Diccionario con el CartItem creado y el total actualizado si la
            configuración está completa. Si faltan modificadores obligatorios,
            devuelve qué campos deben preguntarse al usuario sin modificar el
            carrito.

        Raises:
            ValueError: Si el producto, la cantidad o alguno de los
                modificadores proporcionados no son válidos.
        """
        missing_fields = []

        if size is None:
            missing_fields.append("size")

        if drink is None:
            missing_fields.append("drink")

        if missing_fields:
            return {
                "status": "needs_clarification",
                "product_id": product_id,
                "quantity": quantity,
                "missing_fields": missing_fields,
                "message": (
                    "Faltan modificadores obligatorios. "
                    "Deben preguntarse explícitamente al usuario antes "
                    "de agregar el producto."
                ),
            }

        item = service.add_item(
            product_id=product_id,
            quantity=quantity,
            selected_modifiers={
                "size": size,
                "drink": drink,
            },
        )

        return {
            "status": "added",
            "line_id": item.line_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "selected_modifiers": item.selected_modifiers,
            "unit_price": item.unit_price,
            "cart_total": service.get_cart().total,
        }

    return add_item

def create_get_cart_tool(service: OrderService):
    """
    Crea una función que permite a Gemini consultar el carrito actual.

    La función generada actúa como adaptador entre Gemini y OrderService.
    Gemini no reconstruye el carrito a partir de su memoria conversacional,
    sino que consulta el estado real mantenido por el backend.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para ser utilizada como tool de Gemini.
    """

    def get_cart() -> dict:
        """
        Obtiene el estado actual del carrito de la sesión.

        Returns:
            Diccionario con los CartItem actualmente presentes en el carrito
            y el total calculado del pedido.
        """
        cart = service.get_cart()

        return {
            "items": [
                {
                    "line_id": item.line_id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "selected_modifiers": item.selected_modifiers,
                    "unit_price": item.unit_price,
                }
                for item in cart.items
            ],
            "total": cart.total,
        }

    return get_cart

def create_change_modifier_tool(service: OrderService):
    """
    Crea una función que permite a Gemini modificar una opción de un CartItem.

    La función actúa como adaptador entre Gemini y OrderService. Recibe una
    referencia concreta a una línea del carrito y delega en el servicio la
    validación del grupo y de la opción seleccionada.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para ser utilizada como tool de Gemini.
    """

    def change_modifier(
        line_id: int,
        modifier_group_id: str,
        option_id: str,
    ) -> dict:
        """
        Cambia un modificador de una línea existente del carrito.

        Args:
            line_id: Identificador de la línea del carrito que se desea
                modificar.
            modifier_group_id: Identificador del grupo de modificadores,
                por ejemplo "size" o "drink".
            option_id: Identificador de la nueva opción seleccionada,
                por ejemplo "LARGE", "COCA" o "SPRITE".

        Returns:
            Información estructurada del CartItem actualizado y del total
            actual del carrito.

        Raises:
            ValueError: Si la línea indicada no existe.
            ValueError: Si el producto asociado no existe.
            ValueError: Si el grupo de modificadores no es válido.
            ValueError: Si la opción seleccionada no pertenece al grupo.
        """
        item = service.change_modifier(
            line_id=line_id,
            modifier_group_id=modifier_group_id,
            option_id=option_id,
        )

        return {
            "line_id": item.line_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "selected_modifiers": item.selected_modifiers,
            "unit_price": item.unit_price,
            "cart_total": service.get_cart().total,
        }

    return change_modifier

def create_replace_item_tool(service: OrderService):
    """
    Crea una función que permite a Gemini reemplazar un producto del carrito.

    La función actúa como adaptador entre Gemini y OrderService. Recibe la
    línea que se desea reemplazar, el nuevo producto y su configuración.
    La validación y la modificación efectiva del carrito permanecen bajo
    responsabilidad de OrderService.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para ser utilizada como tool de Gemini.
    """

    def replace_item(
        line_id: int,
        new_product_id: str,
        size: str,
        drink: str,
    ) -> dict:
        """
        Reemplaza un producto existente por otro producto del menú.

        La operación conserva el line_id y la cantidad de la línea original.
        El nuevo producto y todos sus modificadores se validan antes de
        modificar el CartItem existente.

        Args:
            line_id: Identificador de la línea del carrito que se desea
                reemplazar.
            new_product_id: Identificador interno del nuevo producto, por
                ejemplo "COMBO_BIG_MAC" o "COMBO_QUARTER_POUNDER".
            size: Tamaño seleccionado para el nuevo producto. Los valores
                disponibles actualmente son "MEDIUM" y "LARGE".
            drink: Bebida seleccionada para el nuevo producto. Los valores
                disponibles actualmente son "COCA" y "SPRITE".

        Returns:
            Información estructurada del CartItem reemplazado y del total
            actualizado del carrito.

        Raises:
            ValueError: Si la línea indicada no existe.
            ValueError: Si el nuevo producto no existe o no está disponible.
            ValueError: Si falta algún modificador obligatorio.
            ValueError: Si alguna opción seleccionada no es válida.
        """
        item = service.replace_item(
            line_id=line_id,
            new_product_id=new_product_id,
            selected_modifiers={
                "size": size,
                "drink": drink,
            },
        )

        return {
            "line_id": item.line_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "quantity": item.quantity,
            "selected_modifiers": item.selected_modifiers,
            "unit_price": item.unit_price,
            "cart_total": service.get_cart().total,
        }

    return replace_item

def create_remove_item_tool(service: OrderService):
    """
    Crea una función que permite a Gemini eliminar una línea del carrito.

    La función actúa como adaptador entre Gemini y OrderService. Gemini
    identifica la línea que el usuario desea eliminar y OrderService realiza
    la validación y modificación efectiva del carrito.

    Args:
        service: Servicio de pedidos asociado a la sesión actual.

    Returns:
        Función preparada para ser utilizada como tool de Gemini.
    """

    def remove_item(line_id: int) -> dict:
        """
        Elimina una línea existente del carrito.

        Args:
            line_id: Identificador de la línea del carrito que se desea
                eliminar.

        Returns:
            Información estructurada del CartItem eliminado y del total
            actualizado del carrito.

        Raises:
            ValueError: Si la línea indicada no existe en el carrito.
        """
        item = service.remove_item(line_id=line_id)

        return {
            "removed_item": {
                "line_id": item.line_id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "selected_modifiers": item.selected_modifiers,
                "unit_price": item.unit_price,
            },
            "cart_total": service.get_cart().total,
        }

    return remove_item

def create_confirm_order_tool(service: OrderService):
        """
        Crea una función que permite a Gemini confirmar el pedido actual.

        La función actúa como adaptador entre Gemini y OrderService. Gemini puede
        interpretar que el usuario desea finalizar el pedido, pero la validación
        y confirmación efectiva permanecen bajo responsabilidad del backend.

        Args:
            service: Servicio de pedidos asociado a la sesión actual.

        Returns:
            Función preparada para ser utilizada como tool de Gemini.
        """

        def confirm_order() -> dict:
            """
            Confirma el pedido correspondiente al carrito de la sesión actual.

            En esta prueba de concepto, la confirmación es local. En una
            implementación productiva, OrderService deberá delegar esta operación
            al sistema DEX/POS correspondiente.

            Returns:
                Resultado estructurado de la confirmación del pedido.

            Raises:
                ValueError: Si el carrito está vacío y no puede confirmarse.
            """
            return service.confirm_order()

        return confirm_order