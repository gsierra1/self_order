import os

from dotenv import load_dotenv


def _get_provider(variable_name: str, default: str) -> str:
    """Lee y normaliza el identificador de un proveedor de IA.

    Args:
        variable_name: Nombre de la variable de entorno que se debe consultar.
        default: Proveedor usado si la variable no está definida o está vacía.

    Returns:
        Identificador normalizado en minúsculas.
    """
    load_dotenv()
    return os.getenv(variable_name, default).strip().lower() or default


def get_stt_provider() -> str:
    """Obtiene el proveedor configurado para transcripción de voz.

    Returns:
        Identificador del proveedor STT seleccionado; Gemini por omisión.
    """
    return _get_provider("STT_PROVIDER", "gemini")


def get_llm_provider() -> str:
    """Obtiene el proveedor configurado para interpretar pedidos.

    Returns:
        Identificador del proveedor LLM seleccionado; Gemini por omisión.
    """
    return _get_provider("LLM_PROVIDER", "gemini")


def get_transcription_model() -> str:
    """Obtiene el modelo Gemini de transcripción configurable en el entorno.

    Returns:
        Nombre del modelo Live usado únicamente cuando STT_PROVIDER es Gemini.
    """
    load_dotenv()
    return os.getenv("GEMINI_TRANSCRIPTION_MODEL", "gemini-3.5-transcribe-live")


def get_chat_model() -> str:
    """Obtiene el modelo Gemini que interpreta y redacta los pedidos.

    Returns:
        Nombre del modelo usado únicamente cuando LLM_PROVIDER es Gemini.
    """
    load_dotenv()
    return os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")


def get_openai_chat_model() -> str:
    """Obtiene el modelo OpenAI configurado para interpretar pedidos.

    Returns:
        Nombre del modelo usado unicamente cuando LLM_PROVIDER es openai.
    """
    load_dotenv()
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")


def get_groq_chat_model() -> str:
    """Obtiene el modelo Groq configurado para interpretar pedidos.

    Returns:
        Nombre del modelo usado unicamente cuando LLM_PROVIDER es groq.
    """
    load_dotenv()
    return os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")


def get_gemini_api_key() -> str:
    """Obtiene la API key de Gemini desde las variables de entorno.

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
