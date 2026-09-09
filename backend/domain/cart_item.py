from dataclasses import dataclass, field


@dataclass
class CartItem:
    line_id: int
    product_id: str
    product_name: str
    quantity: int
    selected_modifiers: dict[str, str] = field(default_factory=dict)
    unit_price: int = 0