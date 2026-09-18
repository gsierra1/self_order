"""Validaciones compartidas para entradas de conversación del navegador."""

MAX_USER_MESSAGE_CHARACTERS = 1000


def normalize_user_message(value: object) -> str:
    """Valida y normaliza un turno escrito antes de enviarlo al intérprete.

    Args:
        value: Valor recibido por HTTP o WebSocket para el mensaje de la persona.

    Returns:
        Texto sin espacios externos y dentro del límite aceptado.

    Raises:
        ValueError: Si el valor no es texto, queda vacío o supera el máximo de
            caracteres permitido para un turno.
    """
    if not isinstance(value, str):
        raise ValueError("El mensaje debe contener texto.")
    text = value.strip()
    if not text:
        raise ValueError("El mensaje debe contener texto.")
    if len(text) > MAX_USER_MESSAGE_CHARACTERS:
        raise ValueError(
            f"El mensaje supera el máximo de {MAX_USER_MESSAGE_CHARACTERS} caracteres."
        )
    return text
