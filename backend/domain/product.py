from dataclasses import dataclass, field


@dataclass
class ModifierOption:
    id: str
    name: str
    price_delta: int


@dataclass
class ModifierGroup:
    id: str
    name: str
    required: bool
    options: list[ModifierOption] = field(default_factory=list)


@dataclass
class Product:
    id: str
    name: str
    category: str
    base_price: int
    available: bool
    modifier_groups: list[ModifierGroup] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
