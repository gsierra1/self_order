"""Herramienta de diagnóstico para consultar los modelos visibles en Gemini."""

from google import genai

from config.settings import get_gemini_api_key


def print_available_models() -> None:
    """Imprime los modelos visibles para la credencial configurada.

    La consulta usa la API key local y solo imprime nombres y acciones del
    proveedor, nunca la credencial.

    Raises:
        RuntimeError: Si ``GEMINI_API_KEY`` no está configurada.
        Exception: Si Gemini rechaza la consulta o la red no está disponible.
    """
    client = genai.Client(api_key=get_gemini_api_key())
    try:
        models = sorted(client.models.list(), key=lambda model: model.name or "")
        if not models:
            print("La API no devolvió modelos para esta credencial.")
            return
        for model in models:
            name = model.name or "(sin nombre)"
            actions = getattr(model, "supported_actions", None) or []
            action_text = ", ".join(str(action) for action in actions)
            print(f"{name}\t{action_text}".rstrip())
    finally:
        close = getattr(client, "close", None)
        if close:
            close()


if __name__ == "__main__":
    print_available_models()
