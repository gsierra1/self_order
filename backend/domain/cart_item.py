from dataclasses import dataclass, field


@dataclass
class CartItem:
    """Representa una linea validada dentro de un carrito.

    Attributes:
        line_id: Identificador de la linea dentro de su sesion.
        product_id: Identificador tecnico del producto del catalogo.
        product_name: Nombre visible del producto al momento de agregarlo.
        quantity: Cantidad de unidades con la misma configuracion.
        selected_modifiers: Opciones elegidas, indexadas por grupo.
        unit_price: Importe de una unidad, incluidos sus adicionales.
    """

    line_id: int
    product_id: str
    product_name: str
    quantity: int
    selected_modifiers: dict[str, str] = field(default_factory=dict)
    unit_price: int = 0
