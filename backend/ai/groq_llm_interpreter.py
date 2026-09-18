"""Interprete Groq que reutiliza el protocolo compatible de tools."""

from backend.ai.groq_client import create_groq_client
from backend.ai.openai_llm_interpreter import OpenAIOrderInterpreter


class GroqOrderInterpreter(OpenAIOrderInterpreter):
    """Implementa OrderInterpreter mediante Groq y function calling compatible."""

    provider_name = "groq"
    provider_label = "Groq"
    max_completion_tokens = 800

    def _create_client(self):
        """Crea el cliente Groq para esta conversacion.

        Returns:
            Cliente sincronico compatible con Chat Completions.

        Raises:
            RuntimeError: Si GROQ_API_KEY no esta configurada.
        """
        return create_groq_client()
