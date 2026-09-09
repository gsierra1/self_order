from backend.domain.cart_item import CartItem
from backend.domain.menu import Menu
from backend.domain.session import Session


class OrderService:
    def __init__(self, menu: Menu, session: Session):
        self.menu = menu
        self.session = session

    def add_item(
        self,
        product_id: str,
        quantity: int,
        selected_modifiers: dict[str, str],
    ) -> CartItem:

        product = self.menu.get_product(product_id)

        if product is None:
            raise ValueError(f"Product not found: {product_id}")

        if not product.available:
            raise ValueError(f"Product unavailable: {product_id}")

        unit_price = product.base_price

        for group in product.modifier_groups:
            selected_option_id = selected_modifiers.get(group.id)

            if group.required and selected_option_id is None:
                raise ValueError(
                    f"Required modifier missing: {group.id}"
                )

            if selected_option_id is None:
                continue

            selected_option = next(
                (
                    option
                    for option in group.options
                    if option.id == selected_option_id
                ),
                None,
            )

            if selected_option is None:
                raise ValueError(
                    f"Invalid option '{selected_option_id}' "
                    f"for modifier '{group.id}'"
                )

            unit_price += selected_option.price_delta

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        next_line_id = (
            max(
                (item.line_id for item in self.session.cart.items),
                default=0,
            )
            + 1
        )

        cart_item = CartItem(
            line_id=next_line_id,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            selected_modifiers=selected_modifiers.copy(),
            unit_price=unit_price,
        )

        self.session.cart.items.append(cart_item)

        return 
    
    def remove_item(self, line_id: int) -> CartItem:
        """
        Elimina un CartItem del carrito de la sesión actual.

        Args:
            line_id: Identificador único de la línea del carrito que se desea
                eliminar.

        Returns:
            El CartItem que fue eliminado del carrito.

        Raises:
            ValueError: Si no existe ningún CartItem con el line_id indicado.
        """
        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(f"Cart item not found: {line_id}")

        self.session.cart.items.remove(cart_item)

        return cart_item

    def change_quantity(self, line_id: int, quantity: int) -> CartItem:
        """
        Modifica la cantidad de un CartItem del carrito actual.

        Args:
            line_id: Identificador único de la línea del carrito cuya cantidad
                se desea modificar.
            quantity: Nueva cantidad de unidades para ese CartItem.

        Returns:
            El CartItem actualizado con la nueva cantidad.

        Raises:
            ValueError: Si la cantidad no es mayor que cero o si no existe
                ningún CartItem con el line_id indicado.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(f"Cart item not found: {line_id}")

        cart_item.quantity = quantity

        return cart_item

    def change_modifier(
    self,
    line_id: int,
    modifier_group_id: str,
    option_id: str,
) -> CartItem:
        """
        Modifica un modificador de un CartItem y recalcula su precio unitario.

        Args:
            line_id: Identificador único de la línea del carrito que se desea
                modificar.
            modifier_group_id: Identificador del grupo de modificadores a cambiar,
                por ejemplo "size" o "drink".
            option_id: Identificador de la nueva opción seleccionada dentro del
                grupo, por ejemplo "LARGE" o "SPRITE".

        Returns:
            El CartItem actualizado con el nuevo modificador y precio unitario.

        Raises:
            ValueError: Si no existe el CartItem, el producto asociado no existe
                en el menú, el grupo de modificadores no existe o la opción
                seleccionada no es válida.
        """
        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(f"Cart item not found: {line_id}")

        product = self.menu.get_product(cart_item.product_id)

        if product is None:
            raise ValueError(
                f"Product not found in menu: {cart_item.product_id}"
            )

        modifier_group = next(
            (
                group
                for group in product.modifier_groups
                if group.id == modifier_group_id
            ),
            None,
        )

        if modifier_group is None:
            raise ValueError(
                f"Modifier group not found: {modifier_group_id}"
            )

        selected_option = next(
            (
                option
                for option in modifier_group.options
                if option.id == option_id
            ),
            None,
        )

        if selected_option is None:
            raise ValueError(
                f"Invalid option '{option_id}' "
                f"for modifier '{modifier_group_id}'"
            )

        new_modifiers = cart_item.selected_modifiers.copy()
        new_modifiers[modifier_group_id] = option_id

        new_unit_price = product.base_price

        for group in product.modifier_groups:
            selected_id = new_modifiers.get(group.id)

            if selected_id is None:
                continue

            option = next(
                (
                    candidate
                    for candidate in group.options
                    if candidate.id == selected_id
                ),
                None,
            )

            if option is None:
                raise ValueError(
                    f"Invalid option '{selected_id}' "
                    f"for modifier '{group.id}'"
                )

            new_unit_price += option.price_delta

        cart_item.selected_modifiers = new_modifiers
        cart_item.unit_price = new_unit_price

        return cart_item

    def replace_item(
    self,
    line_id: int,
    new_product_id: str,
    selected_modifiers: dict[str, str],
) -> CartItem:
        """
        Reemplaza el producto base de un CartItem por otro producto validado.

        La operación conserva el line_id y la cantidad del CartItem original.
        Todas las validaciones del nuevo producto se realizan antes de modificar
        el carrito, de forma que el CartItem original permanezca intacto si el
        reemplazo no es válido.

        Args:
            line_id: Identificador único de la línea del carrito que se desea
                reemplazar.
            new_product_id: Identificador interno del nuevo producto en el menú.
            selected_modifiers: Modificadores seleccionados para el nuevo
                producto, por ejemplo {"size": "LARGE", "drink": "SPRITE"}.

        Returns:
            El CartItem actualizado con el nuevo producto, modificadores y precio.

        Raises:
            ValueError: Si no existe el CartItem, el nuevo producto no existe o
                no está disponible, falta un modificador obligatorio o alguna
                opción seleccionada no es válida.
        """
        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(f"Cart item not found: {line_id}")

        new_product = self.menu.get_product(new_product_id)

        if new_product is None:
            raise ValueError(f"Product not found: {new_product_id}")

        if not new_product.available:
            raise ValueError(f"Product unavailable: {new_product_id}")

        new_unit_price = new_product.base_price

        for group in new_product.modifier_groups:
            selected_option_id = selected_modifiers.get(group.id)

            if group.required and selected_option_id is None:
                raise ValueError(
                    f"Required modifier missing: {group.id}"
                )

            if selected_option_id is None:
                continue

            selected_option = next(
                (
                    option
                    for option in group.options
                    if option.id == selected_option_id
                ),
                None,
            )

            if selected_option is None:
                raise ValueError(
                    f"Invalid option '{selected_option_id}' "
                    f"for modifier '{group.id}'"
                )

            new_unit_price += selected_option.price_delta

        # Todas las validaciones terminaron correctamente.
        # Recién ahora se modifica el CartItem original.
        cart_item.product_id = new_product.id
        cart_item.product_name = new_product.name
        cart_item.selected_modifiers = selected_modifiers.copy()
        cart_item.unit_price = new_unit_price

        return cart_item

    def clear_cart(self) -> list[CartItem]:
        """
        Elimina todos los CartItem del carrito de la sesión actual.

        Returns:
            Lista con los CartItem que fueron eliminados del carrito.
            Si el carrito ya estaba vacío, devuelve una lista vacía.
        """
        removed_items = self.session.cart.items.copy()

        self.session.cart.items.clear()

        return removed_items

    def get_cart(self):
        """
        Devuelve el carrito actual de la sesión.

        Returns:
            El Cart asociado a la sesión actual, con todos sus CartItem
            y el total calculado a partir de ellos.
        """
        return self.session
        
    def confirm_order(self) -> dict:
        """
        Confirma localmente el pedido de la sesión actual.

        Esta implementación corresponde a la prueba de concepto. Valida que el
        carrito contenga al menos un producto y devuelve un resultado estructurado
        que posteriormente podrá ser utilizado por el frontend.

        En una implementación productiva, esta operación deberá enviar el pedido
        validado al sistema DEX/POS correspondiente.

        Returns:
            Diccionario con el estado de confirmación, el identificador de la
            sesión y el total del pedido.

        Raises:
            ValueError: Si el carrito está vacío.
        """
        cart = self.session.cart

        if not cart.items:
            raise ValueError("Cannot confirm an empty cart")

        return {
            "status": "confirmed",
            "session_id": self.session.session_id,
            "total": cart.total,
        }