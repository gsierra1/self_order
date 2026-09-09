import os

from dotenv import load_dotenv


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