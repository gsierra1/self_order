from backend.domain.cart import Cart
from backend.domain.cart_item import CartItem
from backend.domain.menu import Menu
from backend.domain.session import Session, SessionState
from backend.logging.event_logger import log_event
from collections.abc import Callable
from uuid import uuid4

class OrderService:
    """
    Gestiona las operaciones transaccionales asociadas a un pedido.

    El servicio mantiene la lógica de validación y modificación del carrito.
    El intérprete LLM y las interfaces externas pueden solicitar operaciones,
    pero este servicio constituye la autoridad sobre el estado real del pedido.
    """

    def __init__(
        self,
        menu: Menu,
        session: Session,
        event_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        """
        Inicializa el servicio transaccional de pedidos.

        Args:
            menu: Menú utilizado para validar productos y configuraciones.
            session: Sesión cuyo carrito será administrado.
            event_callback: Función opcional utilizada para publicar cambios de
                estado hacia otros componentes del sistema.
        """
        self.menu = menu
        self.session = session
        self.event_callback = event_callback

    def _get_cart_snapshot(self) -> dict:
        """
        Construye una representación estructurada del carrito actual.

        El snapshot se publica hacia la interfaz y también permite reconstruir
        cómo quedó el pedido después de una operación exitosa.

        Returns:
            Diccionario con productos, total, estado y datos de pago actuales.
        """
        cart = self.session.cart

        return {
            "items": [
                {
                    "line_id": item.line_id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "base_price": (
                        self.menu.get_product(item.product_id).base_price
                    ),
                    "selected_modifiers": (
                        item.selected_modifiers.copy()
                    ),
                    "selected_modifier_details": (
                        self.menu.get_modifier_details(
                            item.product_id,
                            item.selected_modifiers,
                        )
                    ),
                    "unit_price": item.unit_price,
                }
                for item in cart.items
            ],
            "total": cart.total,
            "state": self.session.state.value,
            "order_number": self.session.order_number,
            "payment_method": self.session.payment_method,
        }
    
    def _emit_event(
        self,
        event_type: str,
        data: dict,
    ) -> None:
        """
        Publica un evento hacia un componente externo, si existe un callback.

        Un fallo del mecanismo de publicación no revierte ni interrumpe una
        operación transaccional que ya fue validada correctamente.

        Args:
            event_type: Tipo semántico del evento.
            data: Información estructurada asociada al evento.
        """
        if self.event_callback is None:
            return

        try:
            self.event_callback(
                event_type,
                data,
            )

        except Exception as exc:
            log_event(
                "ERROR",
                "event.publish_error",
                exception=exc,
                session_id=self.session.session_id,
                event_type=event_type,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )

    def _log_cart_updated(
        self,
        action: str,
        *,
        line_id: int | None = None,
    ) -> None:
        """
        Registra y publica una modificación exitosa del carrito.

        Args:
            action: Operación que produjo el cambio, por ejemplo "add_item",
                "remove_item" o "change_modifier".
            line_id: Identificador de la línea afectada, si corresponde.
        """
        snapshot = self._get_cart_snapshot()

        log_event(
            "INFO",
            "cart.updated",
            session_id=self.session.session_id,
            action=action,
            line_id=line_id,
            cart=snapshot,
        )

        self._emit_event(
            "cart.updated",
            {
                "action": action,
                "line_id": line_id,
                "cart": {
                    "items": snapshot["items"],
                    "total": snapshot["total"],
                    "state": snapshot["state"],
                },
            },
        )

    def _ensure_active(self) -> None:
        """
        Verifica que la sesión todavía admita modificaciones.

        Raises:
            ValueError: Si el pedido ya fue confirmado.
        """
        if self.session.state != SessionState.ACTIVE:
            log_event(
                "WARN",
                "session.modification_blocked",
                session_id=self.session.session_id,
                session_state=self.session.state.value,
            )

            raise ValueError(
                "The order has already been confirmed and cannot be modified"
            )

    def _next_line_id(self) -> int:
        """Reserva un identificador de línea que no se reutiliza en la sesión.

        Returns:
            Identificador entero nuevo para un ``CartItem``.

        Effects:
            Incrementa el contador de la sesión únicamente cuando se necesita
            crear una línea distinta, incluso si luego se elimina otra línea.
        """
        line_id = self.session.next_line_id
        self.session.next_line_id += 1
        return line_id

    def _merge_identical_item(self, cart_item: CartItem) -> CartItem:
        """Consolida una línea modificada si ahora coincide con otra existente.

        Args:
            cart_item: Línea cuya configuración ya fue validada y actualizada.

        Returns:
            La línea que conserva la cantidad total. Puede ser ``cart_item`` si
            no existe otra configuración idéntica.

        Effects:
            Suma cantidades y retira ``cart_item`` cuando una modificación o un
            reemplazo producen la misma configuración que una línea previa.
        """
        matching_item = next(
            (
                item
                for item in self.session.cart.items
                if item is not cart_item
                and item.product_id == cart_item.product_id
                and item.selected_modifiers == cart_item.selected_modifiers
                and item.unit_price == cart_item.unit_price
            ),
            None,
        )
        if matching_item is None:
            return cart_item
        matching_item.quantity += cart_item.quantity
        self.session.cart.items.remove(cart_item)
        return matching_item

    def _validate_cart_before_payment(self) -> None:
        """Comprueba que las líneas existentes sigan disponibles antes de pagar.

        Una fuente de catálogo futura puede cambiar disponibilidad mientras el
        usuario aún revisa el pedido. El precio ya aceptado se conserva, pero el
        producto y cada opción seleccionada deben seguir siendo válidos.

        Raises:
            ValueError: Si un producto u opción del carrito dejó de estar
                disponible o ya no pertenece al catálogo.
        """
        for item in self.session.cart.items:
            product = self.menu.get_product(item.product_id)
            if product is None:
                raise ValueError(
                    f"El producto «{item.product_name}» ya no está disponible"
                )
            if not product.available:
                raise ValueError(
                    f"El producto «{product.name}» ya no está disponible en este momento"
                )
            self._calculate_unit_price(product, item.selected_modifiers)

    def _calculate_unit_price(
        self,
        product,
        selected_modifiers: dict[str, str],
    ) -> int:
        """Valida modificadores de un producto y calcula su precio unitario.

        Args:
            product: Producto del catálogo cuya configuración se valida.
            selected_modifiers: Opciones elegidas, indexadas por identificador
                de grupo de modificadores.

        Returns:
            Precio base más los adicionales de las opciones seleccionadas.

        Raises:
            ValueError: Si se recibe un grupo desconocido, falta un grupo
                obligatorio o una opción no pertenece a su grupo.
        """
        group_ids = {group.id for group in product.modifier_groups}
        unknown_groups = set(selected_modifiers) - group_ids

        if unknown_groups:
            raise ValueError(
                f"Unknown modifier group: {sorted(unknown_groups)[0]}"
            )

        unit_price = product.base_price

        for group in product.modifier_groups:
            selected_option_id = selected_modifiers.get(group.id)

            if group.required and selected_option_id is None:
                raise ValueError(f"Required modifier missing: {group.id}")

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

            if not selected_option.available:
                raise ValueError(
                    f"La opción «{selected_option.name}» de "
                    f"«{group.name}» no está disponible en este momento"
                )

            unit_price += selected_option.price_delta

        return unit_price

    def add_item(
        self,
        product_id: str,
        quantity: int,
        selected_modifiers: dict[str, str],
    ) -> CartItem:
        """
        Agrega un producto validado al carrito de la sesión actual.

        Busca el producto en el menú, verifica su disponibilidad, valida los
        modificadores seleccionados y calcula el precio unitario. Si ya existe
        una línea con el mismo producto y configuración, suma la cantidad en esa
        línea; en caso contrario crea un CartItem con un line_id nuevo.

        El carrito solo se modifica después de que todas las validaciones hayan
        finalizado correctamente.

        Args:
            product_id: Identificador interno del producto dentro del menú.
            quantity: Cantidad de unidades idénticas que se desean agregar.
            selected_modifiers: Modificadores seleccionados para el producto.
                Las claves representan grupos y los valores las opciones
                elegidas. Los grupos y las opciones válidas se obtienen del
                catálogo, por ejemplo ``{"drink": "COCA"}``.

        Returns:
            El CartItem creado o consolidado con una línea idéntica.

        Raises:
            ValueError: Si el producto no existe en el menú.
            ValueError: Si el producto no está disponible.
            ValueError: Si falta un modificador obligatorio.
            ValueError: Si alguna opción seleccionada no es válida para su grupo.
            ValueError: Si la cantidad indicada no es mayor que cero.
        """
        self._ensure_active()

        product = self.menu.get_product(
            product_id
        )

        if product is None:
            raise ValueError(
                f"Product not found: {product_id}"
            )

        if not product.available:
            raise ValueError(
                f"El producto «{product.name}» no está disponible en este momento"
            )

        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ValueError(
                "Quantity must be a positive integer"
            )

        unit_price = self._calculate_unit_price(
            product,
            selected_modifiers,
        )

        matching_item = next(
            (
                item
                for item in self.session.cart.items
                if item.product_id == product.id
                and item.selected_modifiers == selected_modifiers
                and item.unit_price == unit_price
            ),
            None,
        )

        if matching_item is not None:
            matching_item.quantity += quantity
            self._log_cart_updated(
                "add_item",
                line_id=matching_item.line_id,
            )
            return matching_item

        cart_item = CartItem(
            line_id=self._next_line_id(),
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            selected_modifiers=(
                selected_modifiers.copy()
            ),
            unit_price=unit_price,
        )

        self.session.cart.items.append(
            cart_item
        )

        self._log_cart_updated(
            "add_item",
            line_id=cart_item.line_id,
        )

        return cart_item

    def remove_item(
        self,
        line_id: int,
    ) -> CartItem:
        """
        Elimina un CartItem del carrito de la sesión actual.

        Args:
            line_id: Identificador único de la línea que se desea eliminar.

        Returns:
            El CartItem eliminado.

        Raises:
            ValueError: Si no existe un CartItem con el line_id indicado.
        """
        self._ensure_active()

        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(
                f"Cart item not found: {line_id}"
            )

        self.session.cart.items.remove(
            cart_item
        )

        self._log_cart_updated(
            "remove_item",
            line_id=cart_item.line_id,
        )

        return cart_item

    def change_quantity(
        self,
        line_id: int,
        quantity: int,
    ) -> CartItem:
        """
        Modifica la cantidad de un CartItem.

        Args:
            line_id: Identificador único de la línea que se desea modificar.
            quantity: Nueva cantidad de unidades.

        Returns:
            El CartItem actualizado.

        Raises:
            ValueError: Si la cantidad no es mayor que cero.
            ValueError: Si no existe el CartItem indicado.
        """
        self._ensure_active()

        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ValueError(
                "Quantity must be a positive integer"
            )

        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(
                f"Cart item not found: {line_id}"
            )

        cart_item.quantity = quantity

        self._log_cart_updated(
            "change_quantity",
            line_id=cart_item.line_id,
        )

        return cart_item

    def adjust_quantity(
        self,
        line_id: int,
        delta: int,
    ) -> CartItem:
        """Suma o resta unidades de una línea sin eliminarla por accidente.

        Args:
            line_id: Identificador único de la línea que se desea ajustar.
            delta: Variación relativa; un valor positivo suma unidades y uno
                negativo las resta.

        Returns:
            El CartItem con su cantidad actualizada.

        Raises:
            ValueError: Si la variación es cero, la línea no existe o el
                resultado sería menor o igual que cero.
        """
        self._ensure_active()

        if not isinstance(delta, int) or isinstance(delta, bool) or delta == 0:
            raise ValueError("Quantity adjustment cannot be zero")

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

        new_quantity = cart_item.quantity + delta
        if new_quantity <= 0:
            raise ValueError(
                "The adjustment would remove the complete line; use remove_item"
            )

        cart_item.quantity = new_quantity
        self._log_cart_updated(
            "adjust_quantity",
            line_id=cart_item.line_id,
        )
        return cart_item

    def change_modifier(
        self,
        line_id: int,
        modifier_group_id: str,
        option_id: str | None,
    ) -> CartItem:
        """
        Modifica un modificador y recalcula el precio unitario.

        Args:
            line_id: Identificador único de la línea que se desea modificar.
            modifier_group_id: Grupo de modificadores definido por el menú.
            option_id: Nueva opción del grupo. Si es ``None``, se elimina una
                selección opcional existente.

        Returns:
            El CartItem actualizado.

        Raises:
            ValueError: Si la línea, producto, grupo u opción no son válidos,
                o si se intenta quitar un modificador obligatorio.
        """
        self._ensure_active()

        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(
                f"Cart item not found: {line_id}"
            )

        product = self.menu.get_product(
            cart_item.product_id
        )

        if product is None:
            raise ValueError(
                f"Product not found in menu: "
                f"{cart_item.product_id}"
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
                f"Modifier group not found: "
                f"{modifier_group_id}"
            )

        new_modifiers = (
            cart_item.selected_modifiers.copy()
        )

        if option_id is None:
            if modifier_group.required:
                raise ValueError(
                    f"Required modifier cannot be removed: {modifier_group_id}"
                )
            new_modifiers.pop(modifier_group_id, None)
        else:
            new_modifiers[modifier_group_id] = option_id

        new_unit_price = self._calculate_unit_price(product, new_modifiers)

        cart_item.selected_modifiers = new_modifiers
        cart_item.unit_price = new_unit_price
        cart_item = self._merge_identical_item(cart_item)

        self._log_cart_updated(
            "change_modifier",
            line_id=cart_item.line_id,
        )

        return cart_item

    def replace_item(
        self,
        line_id: int,
        new_product_id: str,
        selected_modifiers: dict[str, str],
    ) -> CartItem:
        """
        Reemplaza el producto base de un CartItem por otro producto.

        Todas las validaciones se realizan antes de modificar la línea
        existente para preservar la atomicidad de la operación.

        Args:
            line_id: Línea del carrito que se desea reemplazar.
            new_product_id: Identificador interno del nuevo producto.
            selected_modifiers: Configuración del nuevo producto.

        Returns:
            El CartItem actualizado.

        Raises:
            ValueError: Si la línea, producto o configuración no son válidos.
        """
        self._ensure_active()

        cart_item = next(
            (
                item
                for item in self.session.cart.items
                if item.line_id == line_id
            ),
            None,
        )

        if cart_item is None:
            raise ValueError(
                f"Cart item not found: {line_id}"
            )

        new_product = self.menu.get_product(
            new_product_id
        )

        if new_product is None:
            raise ValueError(
                f"Product not found: {new_product_id}"
            )

        if not new_product.available:
            raise ValueError(
                f"El producto «{new_product.name}» no está disponible en este momento"
            )

        new_unit_price = self._calculate_unit_price(
            new_product,
            selected_modifiers,
        )

        # Todas las validaciones terminaron correctamente.
        # Recién ahora se modifica la línea original.

        cart_item.product_id = new_product.id
        cart_item.product_name = new_product.name
        cart_item.selected_modifiers = selected_modifiers.copy()
        cart_item.unit_price = new_unit_price
        cart_item = self._merge_identical_item(cart_item)

        self._log_cart_updated(
            "replace_item",
            line_id=cart_item.line_id,
        )

        return cart_item

    def clear_cart(self) -> list[CartItem]:
        """
        Elimina todos los CartItem del carrito actual.

        Returns:
            Lista con los CartItem eliminados. Si el carrito ya estaba vacío,
            devuelve una lista vacía.
        """
        self._ensure_active()

        removed_items = (
            self.session.cart.items.copy()
        )

        self.session.cart.items.clear()

        self._log_cart_updated(
            "clear_cart"
        )

        return removed_items

    def get_cart(self) -> Cart:
        """
        Devuelve el carrito actual de la sesión.

        Esta operación permanece permitida incluso después de confirmar el
        pedido porque no modifica el estado transaccional.

        Returns:
            Cart asociado a la sesión actual.
        """
        return self.session.cart

    def prepare_payment(self, publish_event: bool = True) -> dict:
        """Prepara el pedido para seleccionar un método de pago.

        Genera el número de pedido en backend y bloquea nuevas modificaciones
        mientras la persona elige cómo pagar.

        Args:
            publish_event: Indica si debe publicarse la pantalla intermedia con
                todos los métodos. Se desactiva cuando el usuario ya eligió uno.

        Returns:
            Estado de pago pendiente, número de pedido y métodos disponibles.

        Raises:
            ValueError: Si el carrito está vacío o la sesión no está activa.
        """
        self._ensure_active()
        if not self.session.cart.items:
            raise ValueError("Cannot prepare payment for an empty cart")
        self._validate_cart_before_payment()

        self.session.state = SessionState.PAYMENT_PENDING
        self.session.order_number = str(uuid4().int % 900000 + 100000)
        self.session.payment_method = None
        snapshot = self._get_cart_snapshot()
        log_event(
            "INFO",
            "payment.pending",
            session_id=self.session.session_id,
            order_number=self.session.order_number,
            total=self.session.cart.total,
        )
        if publish_event:
            self._emit_event(
                "payment.pending",
                {
                    "cart": snapshot,
                    "order_number": self.session.order_number,
                    "payment_methods": ["QR", "CARD", "CASH"],
                },
            )
        return {
            "status": "payment_pending",
            "order_number": self.session.order_number,
            "payment_methods": ["QR", "CARD", "CASH"],
            "total": self.session.cart.total,
        }

    def select_payment_method(self, method: str) -> dict:
        """Selecciona el método de pago para un pedido pendiente.

        Args:
            method: Método ``QR``, ``CARD`` o ``CASH``.

        Returns:
            Método seleccionado y número de pedido.

        Raises:
            ValueError: Si el método no es válido o la sesión no puede iniciar
                ni continuar el flujo de pago.
        """
        method_aliases = {
            "TARJETA": "CARD",
            "CARD": "CARD",
            "CREDITO": "CARD",
            "CRÉDITO": "CARD",
            "EFECTIVO": "CASH",
            "CAJA": "CASH",
            "EN CAJA": "CASH",
            "CASH": "CASH",
            "QR": "QR",
        }
        normalized_input = method.strip().upper().replace("PAGO CON ", "")
        normalized = method_aliases.get(normalized_input, normalized_input)
        if normalized not in {"QR", "CARD", "CASH"}:
            raise ValueError("Unsupported payment method")
        if self.session.state == SessionState.ACTIVE:
            self.prepare_payment(publish_event=False)
        elif self.session.state != SessionState.PAYMENT_PENDING:
            raise ValueError("The order is not waiting for payment")
        self.session.payment_method = normalized
        log_event(
            "INFO",
            "payment.method_selected",
            session_id=self.session.session_id,
            order_number=self.session.order_number,
            payment_method=normalized,
        )
        snapshot = self._get_cart_snapshot()
        self._emit_event(
            "payment.method_selected",
            {
                "method": normalized,
                "order_number": self.session.order_number,
                "cart": snapshot,
            },
        )
        return {
            "status": "payment_method_selected",
            "payment_method": normalized,
            "order_number": self.session.order_number,
        }

    def return_to_order(self) -> dict:
        """Devuelve una sesión pendiente de pago a la edición del carrito.

        Returns:
            Estado activo con el carrito conservado.

        Raises:
            ValueError: Si la sesión no está esperando un método de pago.
        """
        if self.session.state != SessionState.PAYMENT_PENDING:
            raise ValueError("The order is not waiting for payment")
        self.session.state = SessionState.ACTIVE
        self.session.order_number = None
        self.session.payment_method = None
        snapshot = self._get_cart_snapshot()
        log_event(
            "INFO",
            "payment.cancelled",
            session_id=self.session.session_id,
        )
        self._emit_event("payment.cancelled", {"cart": snapshot})
        return {"status": "order_editing", "cart": snapshot}

    def return_to_payment_methods(self, publish_event: bool = True) -> dict:
        """Descarta el método elegido y conserva el pedido pendiente de pago.

        Args:
            publish_event: Indica si debe notificarse el cambio por WebSocket.
                El endpoint HTTP lo desactiva porque ya devuelve el snapshot.

        Returns:
            Estado pendiente, número de pedido y métodos disponibles para que
            la interfaz vuelva a mostrar el selector.

        Raises:
            ValueError: Si la sesión no está pendiente de pago o todavía no se
                había seleccionado un método.
        """
        if self.session.state != SessionState.PAYMENT_PENDING:
            raise ValueError("The order is not waiting for payment")
        if self.session.payment_method is None:
            raise ValueError("No payment method is selected")
        self.session.payment_method = None
        snapshot = self._get_cart_snapshot()
        log_event(
            "INFO",
            "payment.method_cleared",
            session_id=self.session.session_id,
            order_number=self.session.order_number,
        )
        if publish_event:
            self._emit_event(
                "payment.pending",
                {
                    "cart": snapshot,
                    "order_number": self.session.order_number,
                    "payment_methods": ["QR", "CARD", "CASH"],
                },
            )
        return {
            "status": "payment_pending",
            "order_number": self.session.order_number,
            "payment_methods": ["QR", "CARD", "CASH"],
        }

    def complete_payment(self) -> dict:
        """Finaliza el pago de demostración y cierra la sesión.

        Returns:
            Estado final y número de pedido para retirar en caja.

        Raises:
            ValueError: Si todavía no se seleccionó un método de pago.
        """
        if self.session.state != SessionState.PAYMENT_PENDING:
            raise ValueError("The order is not waiting for payment")
        if self.session.payment_method is None:
            raise ValueError("Select a payment method first")
        self.session.state = SessionState.CONFIRMED
        snapshot = self._get_cart_snapshot()
        log_event(
            "INFO",
            "payment.completed",
            session_id=self.session.session_id,
            order_number=self.session.order_number,
            payment_method=self.session.payment_method,
            total=self.session.cart.total,
        )
        self._emit_event(
            "order.confirmed",
            {
                "cart": snapshot,
                "order_number": self.session.order_number,
                "payment_method": self.session.payment_method,
            },
        )
        return {
            "status": "confirmed",
            "order_number": self.session.order_number,
            "payment_method": self.session.payment_method,
            "total": self.session.cart.total,
        }
