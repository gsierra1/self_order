from dataclasses import dataclass, field


@dataclass
class ModifierOption:
    """Define una opcion seleccionable dentro de un grupo de modificadores.

    Attributes:
        id: Identificador tecnico estable de la opcion.
        name: Nombre visible para la persona que hace el pedido.
        price_delta: Importe que se suma al precio base del producto.
        available: Indica si la opcion se puede pedir actualmente.
    """

    id: str
    name: str
    price_delta: int
    available: bool = True


@dataclass
class ModifierGroup:
    """Agrupa opciones configurables de un producto, como bebida o extras.

    Attributes:
        id: Identificador tecnico estable del grupo.
        name: Nombre visible del grupo.
        required: Indica si una opcion debe elegirse antes de agregar el producto.
        options: Opciones validas y disponibles o agotadas del grupo.
    """

    id: str
    name: str
    required: bool
    options: list[ModifierOption] = field(default_factory=list)


@dataclass
class Product:
    """Describe un producto del catalogo y sus configuraciones permitidas.

    Attributes:
        id: Identificador tecnico estable del producto.
        name: Nombre visible para la persona que hace el pedido.
        category: Categoria utilizada para organizar el catalogo.
        base_price: Importe del producto antes de sus modificadores.
        available: Indica si el producto base se puede pedir actualmente.
        modifier_groups: Grupos de opciones aplicables al producto.
        aliases: Formas conversacionales que identifican al mismo producto.
    """

    id: str
    name: str
    category: str
    base_price: int
    available: bool
    modifier_groups: list[ModifierGroup] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
