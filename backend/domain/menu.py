import json
from dataclasses import dataclass
from pathlib import Path

from backend.domain.product import Product, ModifierGroup, ModifierOption


@dataclass
class Menu:
    products: dict[str, Product]

    def get_product(self, product_id: str) -> Product | None:
        return self.products.get(product_id)


def load_menu(path: str | Path) -> Menu:
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
        )

        products[product.id] = product

    return Menu(products=products)