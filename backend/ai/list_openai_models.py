"""Lista identificadores OpenAI visibles sin mostrar credenciales."""

import json

from backend.ai.openai_client import create_openai_client


def list_openai_models() -> list[str]:
    """Consulta los modelos disponibles para la cuenta OpenAI configurada.

    Returns:
        Identificadores de modelos ordenados alfabeticamente.

    Raises:
        RuntimeError: Si OPENAI_API_KEY no esta configurada.
        Exception: Si OpenAI no puede completar la consulta.
    """
    client = create_openai_client()
    try:
        return sorted(model.id for model in client.models.list().data)
    finally:
        client.close()


def main() -> None:
    """Imprime los modelos de la cuenta en formato JSON sin incluir claves."""
    print(json.dumps(list_openai_models(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
