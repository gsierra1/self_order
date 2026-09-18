"""Validaciones deterministas previas al intérprete conversacional."""

import re
import unicodedata

from backend.domain.cart_item import CartItem
from backend.services.order_service import OrderService

_MUTATION_VERBS = (
    "elimina", "eliminar", "saca", "sacar", "quita", "quitar", "borra",
    "borrar", "cambia", "cambiar", "reemplaza", "reemplazar",
)
_CLEAR_CART_PHRASES = (
    "todo el carrito", "carrito completo", "vaciar el carrito", "borra todo",
)
_REMOVAL_VERBS = (
    "elimina", "eliminar", "saca", "sacar", "quita", "quitar", "borra",
    "borrar",
)


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
        "que tiene mi carrito", "que hay en mi carrito", "decime mi carrito",
        "mostrame mi carrito", "mostrar mi carrito", "ver mi carrito",
        "a ver mi carrito",
    )
    return any(pattern in normalized for pattern in patterns)


def get_ambiguous_mutation_message(service: OrderService, text: str) -> str | None:
    """Detiene una mutación que no identifica una línea única del carrito.

    La guarda cubre eliminar o cambiar un producto, una bebida o un extra. Usa
    exclusivamente las líneas y opciones que ya validó ``OrderService``; no
    aplica operaciones ni interpreta precios.

    Args:
        service: Servicio que conserva el carrito validado de la sesión.
        text: Mensaje final escrito o transcripto de la persona usuaria.

    Returns:
        Pregunta con alternativas visibles si la mutación es ambigua, o ``None``
        si no se detecta ambigüedad.
    """
    normalized = _normalize(text)
    if not any(verb in normalized for verb in _MUTATION_VERBS):
        return None
    if any(phrase in normalized for phrase in _CLEAR_CART_PHRASES):
        return None

    cart = service.get_cart()
    requested_action = "eliminar" if any(
        verb in normalized for verb in _REMOVAL_VERBS
    ) else "modificar"
    modifier_match = _find_target_modifier(service, cart.items, normalized)
    if modifier_match is not None:
        option_name, candidates = modifier_match
        candidates = _filter_by_product_and_details(service, candidates, normalized)
        if len(candidates) > 1:
            return _build_question(
                service,
                candidates,
                f"Tenés {option_name} en más de una hamburguesa. "
                f"¿De cuál querés modificarlo o quitarlo?",
            )

    group_match = _find_target_group(service, cart.items, normalized)
    if group_match is not None:
        group_name, candidates = group_match
        candidates = _filter_by_product_and_details(service, candidates, normalized)
        if len(candidates) > 1:
            return _build_question(
                service,
                candidates,
                f"Tenés más de una hamburguesa con {group_name.lower()} elegida. "
                "¿Cuál querés modificar?",
            )

    for product in service.menu.products.values():
        if not _mentions_any(normalized, (product.name, *product.aliases)):
            continue
        candidates = [item for item in cart.items if item.product_id == product.id]
        candidates = _filter_by_product_and_details(service, candidates, normalized)
        if len(candidates) > 1:
            return _build_question(
                service,
                candidates,
                f"Tenés más de una línea de {product.name}. "
                f"¿Cuál querés {requested_action}?",
            )

    if len(cart.items) > 1 and not _mentions_known_target(service, normalized):
        return _build_question(
            service,
            cart.items,
            f"Hay más de un producto en el carrito. ¿Cuál querés {requested_action}?",
        )
    return None


def _find_target_modifier(
    service: OrderService,
    items: list[CartItem],
    normalized_text: str,
) -> tuple[str, list[CartItem]] | None:
    """Busca un extra u opción nombrada como objetivo de una mutación.

    Args:
        service: Servicio usado para traducir opciones seleccionadas.
        items: Líneas activas del carrito.
        normalized_text: Mensaje normalizado de la persona usuaria.

    Returns:
        Nombre visible y líneas que poseen esa opción, o ``None`` si no hay una
        opción elegida que parezca el objetivo del pedido.
    """
    for item in items:
        for detail in service.menu.get_modifier_details(
            item.product_id,
            item.selected_modifiers,
        ):
            option = _normalize(str(detail["option_name"]))
            if option and _is_target_after_mutation_verb(normalized_text, option):
                candidates = [
                    candidate for candidate in items
                    if any(
                        _normalize(str(candidate_detail["option_name"])) == option
                        for candidate_detail in service.menu.get_modifier_details(
                            candidate.product_id,
                            candidate.selected_modifiers,
                        )
                    )
                ]
                return str(detail["option_name"]), candidates
    return None


def _find_target_group(
    service: OrderService,
    items: list[CartItem],
    normalized_text: str,
) -> tuple[str, list[CartItem]] | None:
    """Busca un grupo de modificadores citado como destino de un cambio.

    Args:
        service: Servicio usado para leer los grupos ya seleccionados.
        items: Líneas activas del carrito.
        normalized_text: Mensaje normalizado de la persona usuaria.

    Returns:
        Nombre del grupo y sus líneas candidatas, o ``None`` si no se identifica
        un grupo seleccionado como objetivo.
    """
    for item in items:
        for detail in service.menu.get_modifier_details(
            item.product_id,
            item.selected_modifiers,
        ):
            group = _normalize(str(detail["group_name"]))
            if group and _is_target_after_mutation_verb(normalized_text, group):
                candidates = [
                    candidate for candidate in items
                    if any(
                        _normalize(str(candidate_detail["group_name"])) == group
                        for candidate_detail in service.menu.get_modifier_details(
                            candidate.product_id,
                            candidate.selected_modifiers,
                        )
                    )
                ]
                return str(detail["group_name"]), candidates
    return None


def _is_target_after_mutation_verb(normalized_text: str, target: str) -> bool:
    """Comprueba si una palabra parece ser objeto de eliminar o cambiar.

    Args:
        normalized_text: Mensaje normalizado de la persona usuaria.
        target: Nombre normalizado de una opción o grupo del menú.

    Returns:
        ``True`` si un verbo de mutación antecede al objetivo a corta distancia.
    """
    verbs = "|".join(_MUTATION_VERBS)
    return bool(
        re.search(
            rf"\b(?:{verbs})\b(?:\s+\w+){{0,5}}\s+{re.escape(target)}\b",
            normalized_text,
        )
    )


def _filter_by_product_and_details(
    service: OrderService,
    candidates: list[CartItem],
    normalized_text: str,
) -> list[CartItem]:
    """Reduce candidatos según producto o modificadores explícitos en la frase.

    Args:
        service: Servicio usado para traducir cada línea del carrito.
        candidates: Líneas que comparten el objetivo que se quiere modificar.
        normalized_text: Mensaje normalizado de la persona usuaria.

    Returns:
        Líneas compatibles con los detalles mencionados; si no hay detalles que
        distingan, conserva todos los candidatos originales.
    """
    products_named = {
        product.id
        for product in service.menu.products.values()
        if _mentions_any(normalized_text, (product.name, *product.aliases))
    }
    filtered = [
        item for item in candidates
        if not products_named or item.product_id in products_named
    ]
    matching_details = [
        item for item in filtered
        if any(
            _normalize(str(detail["option_name"])) in normalized_text
            for detail in service.menu.get_modifier_details(
                item.product_id,
                item.selected_modifiers,
            )
        )
    ]
    return matching_details or filtered


def _mentions_known_target(service: OrderService, normalized_text: str) -> bool:
    """Indica si la frase menciona un producto, opción o grupo del carrito.

    Args:
        service: Servicio que permite leer el catálogo y el carrito actual.
        normalized_text: Mensaje normalizado de la persona usuaria.

    Returns:
        ``True`` si existe alguna referencia al catálogo o a una selección actual.
    """
    for product in service.menu.products.values():
        if _mentions_any(normalized_text, (product.name, *product.aliases)):
            return True
    for item in service.get_cart().items:
        for detail in service.menu.get_modifier_details(
            item.product_id,
            item.selected_modifiers,
        ):
            if _mentions_any(
                normalized_text,
                (str(detail["group_name"]), str(detail["option_name"])),
            ):
                return True
    return False


def _mentions_any(normalized_text: str, terms: tuple[str, ...]) -> bool:
    """Determina si una frase contiene cualquiera de varios términos del menú.

    Args:
        normalized_text: Mensaje normalizado de la persona usuaria.
        terms: Nombres o aliases visibles que se desean buscar.

    Returns:
        ``True`` si al menos un término normalizado aparece como frase completa.
    """
    return any(
        term_normalized and re.search(
            rf"\b{re.escape(term_normalized)}\b",
            normalized_text,
        )
        for term in terms
        if (term_normalized := _normalize(term))
    )


def _build_question(
    service: OrderService,
    candidates: list[CartItem],
    introduction: str,
) -> str:
    """Construye una pregunta de aclaración con alternativas del carrito real.

    Args:
        service: Servicio usado para describir líneas validadas.
        candidates: Líneas entre las cuales la persona debe elegir.
        introduction: Texto que explica por qué se necesita la aclaración.

    Returns:
        Pregunta visible con una alternativa por línea y sin IDs internos.
    """
    choices = "\n".join(f"- {_describe_item(service, item)}" for item in candidates)
    return f"{introduction}\n{choices}"


def _describe_item(service: OrderService, item: CartItem) -> str:
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
