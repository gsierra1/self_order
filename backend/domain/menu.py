import json
from dataclasses import dataclass
from pathlib import Path

from backend.domain.product import Product, ModifierGroup, ModifierOption


def _ensure_unique_ids(records: list[dict], collection_name: str) -> None:
    """Rechaza identificadores repetidos en una sección del catálogo.

    Args:
        records: Objetos JSON que deben definir un identificador ``id`` único.
        collection_name: Nombre legible de la sección que se está validando.

    Raises:
        ValueError: Si un registro no tiene un ID textual válido o repite un ID
            ya usado dentro de la misma sección.
    """
    identifiers: set[str] = set()
    for record in records:
        identifier = record.get("id") if isinstance(record, dict) else None
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(
                f"Cada elemento de «{collection_name}» debe tener un id textual."
            )
        if identifier in identifiers:
            raise ValueError(
                f"El id «{identifier}» está repetido en «{collection_name}»."
            )
        identifiers.add(identifier)


def _validate_product_group_ids(
    product_data: dict,
    shared_groups: dict[str, ModifierGroup],
) -> list[str] | None:
    """Valida referencias compartidas de modificadores de un producto.

    Args:
        product_data: Configuración JSON del producto que las declara.
        shared_groups: Grupos compartidos ya construidos e indexados por ID.

    Returns:
        Lista de IDs compartidos o ``None`` cuando el producto define grupos
        locales.

    Raises:
        ValueError: Si la referencia no es una lista, contiene IDs inválidos,
            repetidos o ausentes de los grupos compartidos.
    """
    group_ids = product_data.get("modifier_group_ids")
    if group_ids is None:
        return None
    if not isinstance(group_ids, list) or not all(
        isinstance(group_id, str) and group_id for group_id in group_ids
    ):
        raise ValueError("modifier_group_ids debe ser una lista de IDs textuales.")
    if len(group_ids) != len(set(group_ids)):
        raise ValueError(
            f"El producto «{product_data.get('id', 'sin id')}» repite un grupo de modificadores."
        )
    unknown_group_ids = [group_id for group_id in group_ids if group_id not in shared_groups]
    if unknown_group_ids:
        raise ValueError(
            f"El producto «{product_data.get('id', 'sin id')}» referencia el grupo inexistente «{unknown_group_ids[0]}»."
        )
    return group_ids


def _build_modifier_group(group_data: dict) -> ModifierGroup:
    """Construye un grupo de modificadores a partir de su configuracion.

    Args:
        group_data: Datos del grupo y de sus opciones dentro del catalogo JSON.

    Returns:
        Grupo de dominio con opciones y disponibilidad configuradas.

    Raises:
        ValueError: Si el grupo no es un objeto, sus opciones no son una lista o
            existen IDs de opciones duplicados.
        KeyError: Si faltan atributos obligatorios del grupo o de sus opciones.
    """
    if not isinstance(group_data, dict):
        raise ValueError("Cada grupo de modificadores debe ser un objeto JSON.")
    options = group_data.get("options", [])
    if not isinstance(options, list):
        raise ValueError("Las opciones de un grupo deben ser una lista.")
    _ensure_unique_ids(options, f"opciones de «{group_data.get('id', 'sin id')}»")
    return ModifierGroup(
        id=group_data["id"],
        name=group_data["name"],
        required=group_data["required"],
        options=[
            ModifierOption(
                id=option_data["id"],
                name=option_data["name"],
                price_delta=option_data["price_delta"],
                available=option_data.get("available", True),
            )
            for option_data in options
        ],
    )


@dataclass
class Menu:
    """Mantiene los productos del catalogo indexados por identificador tecnico.

    Attributes:
        products: Productos disponibles en el catalogo, indexados por su ID.
    """

    products: dict[str, Product]

    def get_product(self, product_id: str) -> Product | None:
        """Busca un producto por su identificador interno.

        Args:
            product_id: Identificador técnico definido en el catálogo.

        Returns:
            Producto encontrado o ``None`` si no pertenece al menú.
        """
        return self.products.get(product_id)

    def get_modifier_details(
        self,
        product_id: str,
        selected_modifiers: dict[str, str],
    ) -> list[dict[str, str | int | bool]]:
        """Traduce los IDs internos de los modificadores a textos aptos para mostrar en 
        el frontend. Por ejemplo:
         {
            "drink": "COCA",
            "extra_tomato": "ADD_TOMATO"
        }
        pasa a algo como:

        Bebida: Coca-Cola
        Tomate · + ARS 1.000

        Así el frontend no necesita saber qué significa COCA ni repetir precios o nombres del menú.

        Args:
            product_id: Identificador del producto asociado al carrito.
            selected_modifiers: Relación entre grupos y opciones validadas.

        Returns:
            Lista ordenada con los nombres visibles, el grupo técnico y si la
            selección es obligatoria. Devuelve una lista vacía si el producto
            ya no existe en el catálogo.
        """
        product = self.get_product(product_id)

        if product is None:
            return []

        details = []

        for group in product.modifier_groups:
            option_id = selected_modifiers.get(group.id)

            if option_id is None:
                continue

            option = next(
                (
                    candidate
                    for candidate in group.options
                    if candidate.id == option_id
                ),
                None,
            )

            if option is not None:
                details.append(
                    {
                        "group_id": group.id,
                        "group_name": group.name,
                        "option_name": option.name,
                        "price_delta": option.price_delta,
                        "required": group.required,
                        "available": option.available,
                    }
                )

        return details


def load_menu(path: str | Path) -> Menu:
    """Carga el catálogo JSON y lo transforma en objetos de dominio.

    Args:
        path: Ruta del archivo JSON que define productos y modificadores.

    Returns:
        Menú disponible para validar y cotizar pedidos.

    Raises:
        FileNotFoundError: Si no existe el archivo indicado.
        json.JSONDecodeError: Si el archivo no contiene JSON válido.
        ValueError: Si se repiten IDs o una referencia de grupo no existe.
        KeyError: Si falta un atributo obligatorio del catálogo.
    """
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    shared_group_data = data.get("modifier_groups", [])
    products_data = data["products"]
    if not isinstance(shared_group_data, list) or not isinstance(products_data, list):
        raise ValueError("products y modifier_groups deben ser listas JSON.")
    _ensure_unique_ids(shared_group_data, "modifier_groups")
    _ensure_unique_ids(products_data, "products")
    shared_groups = {
        group_data["id"]: _build_modifier_group(group_data)
        for group_data in shared_group_data
    }
    products = {}

    for product_data in products_data:
        if not isinstance(product_data, dict):
            raise ValueError("Cada producto debe ser un objeto JSON.")
        group_ids = _validate_product_group_ids(product_data, shared_groups)

        if group_ids is None:
            local_groups = product_data.get("modifier_groups", [])
            if not isinstance(local_groups, list):
                raise ValueError("Los grupos locales de un producto deben ser una lista.")
            _ensure_unique_ids(local_groups, f"grupos de «{product_data['id']}»")
            modifier_groups = [_build_modifier_group(group_data) for group_data in local_groups]
        else:
            modifier_groups = [shared_groups[group_id] for group_id in group_ids]

        product = Product(
            id=product_data["id"],
            name=product_data["name"],
            category=product_data["category"],
            base_price=product_data["base_price"],
            available=product_data["available"],
            modifier_groups=modifier_groups,
            aliases=product_data.get("aliases", []),
        )

        products[product.id] = product

    return Menu(products=products)
