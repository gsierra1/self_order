import os

from dotenv import load_dotenv


def get_transcription_model() -> str:
    """Obtiene el modelo dedicado de transcripción configurable en el entorno.

    Returns:
        Nombre del modelo Live que recibe audio y devuelve transcripciones.
    """
    load_dotenv()
    return os.getenv("GEMINI_TRANSCRIPTION_MODEL", "gemini-3.5-transcribe-live")


def get_chat_model() -> str:
    """Obtiene el modelo de Gemini que interpreta y redacta los pedidos.

    Returns:
        Nombre del modelo configurado para la conversación y las tools.
    """
    load_dotenv()
    return os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")


def get_gemini_api_key() -> str:
    """
    Obtiene la API key de Gemini desde las variables de entorno.

    Carga previamente las variables definidas en el archivo `.env` local.

    Returns:
        API key utilizada para autenticar las solicitudes a Gemini.

    Raises:
        RuntimeError: Si la variable GEMINI_API_KEY no está configurada.
    """
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY no está configurada. "
            "Creá un archivo .env a partir de .env.example."
        )

    return api_key
