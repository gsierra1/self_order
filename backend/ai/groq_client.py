"""Cliente y configuracion exclusivos del proveedor Groq."""

import os

from dotenv import load_dotenv
from openai import OpenAI


def get_groq_api_key() -> str:
    """Obtiene la clave de Groq del entorno local.

    Returns:
        Clave usada unicamente por los adaptadores Groq.

    Raises:
        RuntimeError: Si GROQ_API_KEY no esta configurada.
    """
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY no esta configurada. Crea .env desde .env.example."
        )
    return api_key


def create_groq_client() -> OpenAI:
    """Crea un cliente para la API compatible con OpenAI de Groq.

    Returns:
        Cliente sincronico configurado con la URL publica de Groq.

    Raises:
        RuntimeError: Si no existe GROQ_API_KEY.
    """
    return OpenAI(
        api_key=get_groq_api_key(),
        base_url="https://api.groq.com/openai/v1",
    )
