from dataclasses import dataclass, field

from backend.domain.cart_item import CartItem


@dataclass
class Cart:
    items: list[CartItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(
            item.unit_price * item.quantity
            for item in self.items
        )