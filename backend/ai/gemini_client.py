from google import genai

from config.settings import get_gemini_api_key


def create_gemini_client() -> genai.Client:
    """
    Crea un cliente autenticado para interactuar con la API de Gemini.

    Returns:
        Cliente de Google GenAI configurado con la API key del entorno.

    Raises:
        RuntimeError: Si GEMINI_API_KEY no está configurada.
    """
    api_key = get_gemini_api_key()

    return genai.Client(api_key=api_key)