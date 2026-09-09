from dataclasses import dataclass, field
from uuid import uuid4

from backend.domain.cart import Cart


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    cart: Cart = field(default_factory=Cart)