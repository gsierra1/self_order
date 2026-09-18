"""Validaciones deterministas previas al intérprete conversacional."""

import re
import unicodedata

from backend.services.order_service import OrderService


def _normalize(text: str) -> str:
    """Normaliza una frase para comparar palabras sin depender de acentos.

    Args:
        text: Texto escrito o transcripto que se desea comparar.

    Returns:
        Texto en minúsculas, sin acentos y con espacios uniformes.
    """
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


def is_cart_query(text: str) -> bool:
    """Reconoce una consulta explícita sobre el contenido del carrito.

    Args:
        text: Mensaje final de la persona usuaria.

    Returns:
        ``True`` cuando pide ver o conocer el carrito; ``False`` en otro caso.
    """
    normalized = _normalize(text)
    patterns = (
        "que tiene mi carrito",
        "que hay en mi carrito",
        "decime mi carrito",
        "mostrame mi carrito",
        "mostrar mi carrito",
        "ver mi carrito",
        "a ver mi carrito",
    )
    return any(pattern in normalized for pattern in patterns)


def get_ambiguous_removal_message(service: OrderService, text: str) -> str | None:
    """Detiene una eliminación que no identifica una línea única del carrito.

    La barrera usa el producto y los modificadores ya validados por
    ``OrderService``. No elimina ni interpreta precios: solamente evita delegar
    al LLM una solicitud que podría borrar más de una línea distinta.

    Args:
        service: Servicio que conserva el carrito validado de la sesión.
        text: Mensaje final escrito o transcripto de la persona usuaria.

    Returns:
        Pregunta con alternativas visibles si la eliminación es ambigua, o
        ``None`` cuando la frase no es una eliminación ambigua.
    """
    normalized = _normalize(text)
    removal_verbs = ("elimina", "eliminar", "saca", "sacar", "quita", "quitar", "borra", "borrar")
    if not any(verb in normalized for verb in removal_verbs):
        return None
    if any(term in normalized for term in ("todo el carrito", "carrito completo", "vaciar el carrito")):
        return None

    cart = service.get_cart()
    for product in service.menu.products.values():
        product_terms = (product.name, *product.aliases)
        if not any(_normalize(term) in normalized for term in product_terms):
            continue
        candidates = [item for item in cart.items if item.product_id == product.id]
        if len(candidates) < 2:
            continue
        if _mentions_selected_modifier(service, candidates, normalized):
            continue
        choices = "\n".join(
            f"- {_describe_item(service, item)}" for item in candidates
        )
        return (
            f"Tenés más de una línea de {product.name}. "
            f"¿Cuál querés eliminar?\n{choices}"
        )
    return None


def _mentions_selected_modifier(
    service: OrderService,
    candidates: list,
    normalized_text: str,
) -> bool:
    """Indica si el mensaje nombra un modificador que distingue candidatos.

    Args:
        service: Servicio usado para traducir los IDs del carrito.
        candidates: Líneas del mismo producto que podrían eliminarse.
        normalized_text: Mensaje ya normalizado para comparaciones.

    Returns:
        ``True`` si la frase contiene una opción elegida por al menos una línea.
    """
    names = {
        _normalize(detail["option_name"])
        for item in candidates
        for detail in service.menu.get_modifier_details(
            item.product_id,
            item.selected_modifiers,
        )
    }
    return any(name and name in normalized_text for name in names)


def _describe_item(service: OrderService, item) -> str:
    """Construye una alternativa legible a partir de una línea validada.

    Args:
        service: Servicio usado para obtener los nombres de modificadores.
        item: Línea del carrito que se presenta como alternativa.

    Returns:
        Producto, bebida y extras de la línea sin exponer identificadores internos.
    """
    details = service.menu.get_modifier_details(item.product_id, item.selected_modifiers)
    required = [detail["option_name"] for detail in details if detail["required"]]
    extras = [detail["option_name"] for detail in details if not detail["required"]]
    parts = [item.product_name]
    if required:
        parts.append(", ".join(required))
    if extras:
        parts.append(f"extras: {', '.join(extras)}")
    return " con ".join(parts)
