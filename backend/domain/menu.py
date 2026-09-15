import json
from dataclasses import dataclass
from pathlib import Path

from backend.domain.product import Product, ModifierGroup, ModifierOption


@dataclass
class Menu:
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
        """Traduce los modificadores internos a textos aptos para la interfaz.

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
        KeyError: Si falta un atributo obligatorio del catálogo.
    """
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    products = {}

    for product_data in data["products"]:
        modifier_groups = []

        for group_data in product_data.get("modifier_groups", []):
            options = [
                ModifierOption(
                    id=option_data["id"],
                    name=option_data["name"],
                    price_delta=option_data["price_delta"],
                )
                for option_data in group_data.get("options", [])
            ]

            modifier_groups.append(
                ModifierGroup(
                    id=group_data["id"],
                    name=group_data["name"],
                    required=group_data["required"],
                    options=options,
                )
            )

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
