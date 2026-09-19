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


def get_stt_model_path() -> str:
    """Obtiene la ruta local configurada para un motor STT basado en archivos.

    Returns:
        Ruta al directorio del modelo local, o una cadena vacía si no se definió.

    Effects:
        Carga el archivo .env local antes de consultar la configuración.
    """
    load_dotenv()
    return os.getenv("STT_MODEL_PATH", "").strip()


def get_whisper_browser_model() -> str:
    """Obtiene el modelo Whisper que se descargará y ejecutará en el navegador.

    Returns:
        Identificador del modelo compatible con Transformers.js. Solo se usa
        cuando ``STT_PROVIDER`` es ``whisper_browser``.

    Effects:
        Carga el archivo .env local antes de consultar la configuración.
    """
    load_dotenv()
    return os.getenv("WHISPER_BROWSER_MODEL", "onnx-community/whisper-tiny").strip()


def get_whisper_browser_device() -> str:
    """Obtiene el modo de ejecución local preferido para Whisper en navegador.

    Returns:
        ``auto``, ``webgpu`` o ``wasm``. Los valores no reconocidos vuelven a
        ``auto`` para evitar publicar una configuración incompatible.

    Effects:
        Carga el archivo .env local antes de consultar la configuración.
    """
    load_dotenv()
    device = os.getenv("WHISPER_BROWSER_DEVICE", "auto").strip().lower()
    return device if device in {"auto", "webgpu", "wasm"} else "auto"


def get_public_stt_configuration() -> dict[str, str]:
    """Construye la configuración de voz segura que puede recibir el navegador.

    Returns:
        Proveedor de STT y, para Whisper local, modelo y modo de ejecución.
        No incorpora claves ni rutas privadas del servidor.
    """
    provider = get_stt_provider()
    configuration = {"provider": provider}
    if provider == "whisper_browser":
        configuration.update({
            "model": get_whisper_browser_model(),
            "device": get_whisper_browser_device(),
        })
    return configuration


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
