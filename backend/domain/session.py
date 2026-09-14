from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from backend.domain.cart import Cart


class SessionState(str, Enum):
    """
    Representa el estado transaccional de una sesión de pedido.

    Attributes:
        ACTIVE: La sesión admite consultas y modificaciones del carrito.
        CONFIRMED: El pedido fue confirmado y ya no admite modificaciones.
    """

    ACTIVE = "ACTIVE"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONFIRMED = "CONFIRMED"


@dataclass
class Session:
    """
    Representa una sesión individual de pedido.

    Cada sesión posee un identificador único, un carrito y un estado
    transaccional que determina si el pedido todavía puede modificarse.

    Attributes:
        session_id: Identificador técnico único de la sesión.
        cart: Carrito asociado a la sesión.
        state: Estado transaccional actual de la sesión.
    """

    session_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    cart: Cart = field(default_factory=Cart)
    state: SessionState = SessionState.ACTIVE
    order_number: str | None = None
    payment_method: str | None = None
