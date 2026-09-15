from dataclasses import dataclass, field

from backend.domain.cart_item import CartItem


@dataclass
class Cart:
    """Representa el carrito validado asociado a una sesion de pedido.

    Attributes:
        items: Lineas validadas que componen el pedido actual.
    """

    items: list[CartItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Calcula el importe total de las lineas presentes en el carrito.

        Returns:
            Suma de cada precio unitario multiplicado por su cantidad. El
            resultado se expresa en pesos argentinos completos.
        """
        return sum(
            item.unit_price * item.quantity
            for item in self.items
        )
