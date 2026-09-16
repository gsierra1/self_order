"""Cliente y configuracion exclusivos del proveedor OpenAI."""

import os

from dotenv import load_dotenv
from openai import OpenAI


def get_openai_api_key() -> str:
    """Obtiene la clave de OpenAI del entorno local.

    Returns:
        Clave usada unicamente por los adaptadores OpenAI.

    Raises:
        RuntimeError: Si OPENAI_API_KEY no esta configurada.
    """
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY no esta configurada. Crea .env desde .env.example."
        )
    return api_key


def create_openai_client() -> OpenAI:
    """Crea un cliente OpenAI autenticado para el backend.

    Returns:
        Cliente sincronico del SDK oficial de OpenAI.

    Raises:
        RuntimeError: Si no existe OPENAI_API_KEY.
    """
    return OpenAI(api_key=get_openai_api_key())
