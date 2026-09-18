from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from backend.domain.cart import Cart


class SessionState(str, Enum):
    """
    Representa el estado transaccional de una sesión de pedido.

    Attributes:
        ACTIVE: La sesion admite consultas y modificaciones del carrito.
        PAYMENT_PENDING: El carrito queda reservado para elegir o completar el
            pago. Conserva su contenido, no admite mutaciones y puede volver a
            ``ACTIVE`` mediante ``return_to_order``.
        CONFIRMED: El pago de demostracion fue completado y el pedido ya no
            admite modificaciones.
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
        session_id: Identificador tecnico unico de la sesion.
        cart: Carrito asociado a la sesion.
        state: Estado transaccional actual: ``ACTIVE``, ``PAYMENT_PENDING`` o
            ``CONFIRMED``.
        order_number: Numero generado al preparar el pago; se conserva hasta
            que el pedido se confirma o se vuelve a editar.
        payment_method: Metodo elegido durante ``PAYMENT_PENDING``.
        next_line_id: Próximo identificador de línea reservado para esta sesión.
    """

    session_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    cart: Cart = field(default_factory=Cart)
    state: SessionState = SessionState.ACTIVE
    order_number: str | None = None
    payment_method: str | None = None
    next_line_id: int = 1
