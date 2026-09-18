"""Lista identificadores Groq visibles sin mostrar credenciales."""

import json

from backend.ai.groq_client import create_groq_client


def list_groq_models() -> list[str]:
    """Consulta los modelos visibles para la cuenta Groq configurada.

    Returns:
        Identificadores de modelos ordenados alfabéticamente.

    Raises:
        RuntimeError: Si GROQ_API_KEY no está configurada.
        Exception: Si Groq no puede completar la consulta.
    """
    client = create_groq_client()
    try:
        return sorted(model.id for model in client.models.list().data)
    finally:
        client.close()


def main() -> None:
    """Imprime los modelos de la cuenta en formato JSON sin incluir claves."""
    print(json.dumps(list_groq_models(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
