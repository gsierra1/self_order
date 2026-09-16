"""Crea adaptadores de IA según la configuración, fuera del dominio."""

from backend.ai.contracts import OrderInterpreter, SpeechToText
from backend.ai.groq_interpreter import GroqOrderInterpreter
from backend.ai.live_transcriber import GeminiLiveTranscriber
from backend.ai.orchestrator import GeminiOrderInterpreter
from backend.ai.openai_interpreter import OpenAIOrderInterpreter
from backend.services.order_service import OrderService
from config.settings import (
    get_chat_model,
    get_groq_chat_model,
    get_llm_provider,
    get_openai_chat_model,
    get_stt_provider,
)


def create_speech_to_text(session_id: str | None = None) -> SpeechToText:
    """Crea el adaptador de transcripción seleccionado para un turno de voz.

    Args:
        session_id: Identificador de la sesión que origina el audio.

    Returns:
        Adaptador que cumple SpeechToText para el proveedor configurado.

    Raises:
        RuntimeError: Si STT_PROVIDER no tiene un adaptador implementado.
    """
    provider = get_stt_provider()
    if provider == "gemini":
        return GeminiLiveTranscriber(session_id=session_id)
    raise RuntimeError(
        f"STT_PROVIDER={provider!r} todavía no tiene un adaptador implementado. "
        "Usá 'gemini' o agregá el adaptador y sus pruebas antes de seleccionarlo."
    )


def create_order_interpreter(service: OrderService) -> OrderInterpreter:
    """Crea el intérprete de pedidos seleccionado para una sesión.

    Args:
        service: Autoridad transaccional que las tools pueden solicitar usar.

    Returns:
        Intérprete que delega las operaciones permitidas en OrderService.

    Raises:
        RuntimeError: Si LLM_PROVIDER no tiene un adaptador implementado.
    """
    provider = get_llm_provider()
    if provider == "gemini":
        return GeminiOrderInterpreter(service=service, model=get_chat_model())
    if provider == "openai":
        return OpenAIOrderInterpreter(service=service, model=get_openai_chat_model())
    if provider == "groq":
        return GroqOrderInterpreter(service=service, model=get_groq_chat_model())
    raise RuntimeError(
        f"LLM_PROVIDER={provider!r} todavía no tiene un adaptador implementado. "
        "Usá 'gemini', 'openai', 'groq' o agregá el adaptador y sus pruebas "
        "antes de seleccionarlo."
    )
