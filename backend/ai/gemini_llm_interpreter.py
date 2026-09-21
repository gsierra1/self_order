from types import SimpleNamespace

from google.genai import errors, types

from backend.ai.contracts import OrderInterpreter
from backend.ai.errors import (
    AIProviderError,
    classify_gemini_api_error,
    classify_gemini_transport_error,
)
from backend.ai.gemini_client import create_gemini_client
from backend.ai.order_tools_runtime import OrderToolsRuntime
from backend.logging.event_logger import log_event
from backend.services.order_service import OrderService


class GeminiOrderInterpreter(OrderInterpreter):
    """
    Orquesta la conversación entre el usuario, Gemini y OrderService.

    Gemini interpreta las solicitudes en lenguaje natural y propone llamadas
    a un conjunto explícito de tools. El runtime común controla y ejecuta las
    operaciones; los resultados sin mutación pueden volver al modelo para que
    formule una aclaración.

    Los eventos relevantes de la conversación, ejecución de tools y errores
    se registran mediante logging estructurado para facilitar debugging y
    observabilidad.
    """

    def __init__(
        self,
        service: OrderService,
        model: str = "gemini-3.5-flash-lite",
        max_tool_rounds: int = 5,
    ):
        """
        Inicializa el orquestador para una sesión de pedido.

        Args:
            service: Servicio de pedidos asociado a la sesión actual.
            model: Modelo de Gemini utilizado para interpretar la conversación.
            max_tool_rounds: Máximo de ciclos de tools permitidos por mensaje.

        Raises:
            ValueError: Si max_tool_rounds no es mayor que cero.
        """
        if max_tool_rounds <= 0:
            raise ValueError(
                "max_tool_rounds must be greater than zero"
            )

        self.service = service
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.runtime = OrderToolsRuntime(service)
        self.system_instruction = self.runtime.build_system_instruction()

        self.available_tools = self.runtime.available_tools

        self.client = create_gemini_client()

        self.chat = self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                tools=[self._build_gemini_tool()],
                automatic_function_calling=(
                    types.AutomaticFunctionCallingConfig(
                        disable=True
                    )
                ),
            ),
        )

        log_event(
            "INFO",
            "gemini_llm_interpreter.started",
            session_id=self.service.session.session_id,
            model=self.model,
        )

    def _build_gemini_tool(self) -> types.Tool:
        """Traduce el catálogo neutral de tools al formato de Gemini.

        Returns:
            Tool Gemini con declaraciones equivalentes a las de otros LLM.
        """
        declarations = [
            types.FunctionDeclaration(
                name=spec.name,
                description=spec.description,
                parameters_json_schema=spec.json_schema(),
            )
            for spec in self.runtime.tool_specs
        ]
        return types.Tool(function_declarations=declarations)

    def _send_to_gemini(
        self,
        content,
        *,
        stage: str,
        transaction_applied: bool,
        last_tool: str | None = None,
    ):
        """
        Envía contenido a Gemini y clasifica errores propios del proveedor.

        Cada solicitud y respuesta se registra a nivel DEBUG. Los errores
        identificados del proveedor se registran a nivel ERROR antes de
        propagarse hacia la capa superior.

        Args:
            content: Contenido enviado al modelo.
            stage: Etapa conversacional correspondiente a la solicitud.
            transaction_applied: Indica si ya ocurrió una mutación del pedido.
            last_tool: Última tool ejecutada, si corresponde.

        Returns:
            Respuesta producida por Gemini.

        Raises:
            AIProviderError: Si Gemini o su transporte producen un error
                reconocido.
        """
        session_id = self.service.session.session_id

        log_event(
            "DEBUG",
            "gemini.request",
            session_id=session_id,
            model=self.model,
            stage=stage,
            transaction_applied=transaction_applied,
            last_tool=last_tool,
        )

        try:
            response = self.chat.send_message(content)

            function_calls = response.function_calls or []

            log_event(
                "DEBUG",
                "gemini.response",
                session_id=session_id,
                model=self.model,
                stage=stage,
                function_call_count=len(function_calls),
                response_text=(
                    response.text
                    if not function_calls
                    else None
                ),
            )

            return response

        except errors.APIError as exc:
            provider_error = classify_gemini_api_error(
                exc,
                model=self.model,
                stage=stage,
                transaction_applied=transaction_applied,
                last_tool=last_tool,
            )

            log_event(
                "ERROR",
                "gemini.error",
                exception=exc,
                session_id=session_id,
                provider=provider_error.provider,
                model=provider_error.model,
                error_type=provider_error.error_type,
                status_code=provider_error.status_code,
                api_status=provider_error.api_status,
                stage=provider_error.stage,
                retryable=provider_error.retryable,
                transaction_applied=(
                    provider_error.transaction_applied
                ),
                last_tool=provider_error.last_tool,
                technical_message=(
                    provider_error.technical_message
                ),
            )

            raise provider_error from exc

        except Exception as exc:
            provider_error = classify_gemini_transport_error(
                exc,
                model=self.model,
                stage=stage,
                transaction_applied=transaction_applied,
                last_tool=last_tool,
            )

            if provider_error is not None:
                log_event(
                    "ERROR",
                    "gemini.transport_error",
                    exception=exc,
                    session_id=session_id,
                    provider=provider_error.provider,
                    model=provider_error.model,
                    error_type=provider_error.error_type,
                    stage=provider_error.stage,
                    retryable=provider_error.retryable,
                    transaction_applied=(
                        provider_error.transaction_applied
                    ),
                    last_tool=provider_error.last_tool,
                    technical_message=(
                        provider_error.technical_message
                    ),
                )

                raise provider_error from exc

            log_event(
                "ERROR",
                "internal.error",
                exception=exc,
                session_id=session_id,
                component="GeminiOrderInterpreter",
                stage=stage,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )

            raise

    def _record_deterministic_tool_response(
        self,
        function_response_parts: list[types.Part],
        response_text: str,
    ) -> None:
        """Completa localmente el historial Gemini después de una mutación.

        Args:
            function_response_parts: Resultados de tools en el formato del SDK.
            response_text: Resumen determinístico construido por el runtime.

        Effects:
            Registra la respuesta de función y el cierre visible sin realizar
            una segunda solicitud al proveedor.
        """
        self.chat.record_history(
            user_input=types.Content(
                role="user",
                parts=function_response_parts,
            ),
            model_output=[
                types.Content(
                    role="model",
                    parts=[types.Part(text=response_text)],
                ),
            ],
            is_valid=True,
        )

    provider_name = "gemini"

    def close(self) -> None:
        """Cierra el cliente Gemini asociado a esta conversación si está disponible.

        El cierre es idempotente para permitir liberar una sesión desde distintos
        bordes de transporte sin cambiar el estado validado del pedido.
        """
        self.client.close()

    def send_message(self, message: str) -> str:
        """
        Procesa un mensaje del usuario dentro de la conversación actual.

        Gemini puede solicitar tools, que son verificadas y ejecutadas por la
        aplicación. Los eventos relevantes se registran para permitir
        reconstruir posteriormente cada etapa de la interacción.

        Args:
            message: Mensaje expresado en lenguaje natural por el usuario.

        Returns:
            Respuesta textual de Gemini cuando no hubo cambios o resumen
            determinístico del runtime después de una mutación.

        Raises:
            ValueError: Si el mensaje está vacío.
            AIProviderError: Si Gemini produce un error identificado.
            RuntimeError: Si Gemini solicita tools de manera no permitida.
        """
        if not message.strip():
            raise ValueError("El mensaje no puede estar vacío.")

        session_id = self.service.session.session_id

        log_event(
            "DEBUG",
            "user.message",
            session_id=session_id,
            text=message,
        )

        transaction_applied = False
        last_tool = None

        response = self._send_to_gemini(
            message,
            stage="GEMINI_INTERPRETATION",
            transaction_applied=False,
        )

        executed_calls = set()
        tool_rounds = 0

        while response.function_calls:
            if tool_rounds >= self.max_tool_rounds:
                log_event(
                    "ERROR",
                    "gemini_llm_interpreter.max_tool_rounds",
                    session_id=session_id,
                    max_tool_rounds=self.max_tool_rounds,
                )

                raise RuntimeError(
                    "Se alcanzó el máximo de ciclos de tools permitidos."
                )

            function_calls = [
                SimpleNamespace(
                    name=function_call.name,
                    args=dict(function_call.args or {}),
                )
                for function_call in response.function_calls
            ]

            if len(function_calls) > 1:
                log_event(
                    "INFO",
                    "gemini_llm_interpreter.multiple_function_calls",
                    session_id=session_id,
                    function_call_count=len(function_calls),
                )
            executions = self.runtime.execute_calls(
                function_calls,
                executed_calls,
            )
            function_response_parts = [
                types.Part.from_function_response(
                    name=execution.call.name,
                    response=execution.result,
                )
                for execution in executions
            ]
            if executions:
                last_tool = executions[-1].call.name
            transaction_applied = transaction_applied or any(
                execution.did_mutate for execution in executions
            )

            if transaction_applied:
                final_text = self.runtime.get_post_mutation_response(last_tool)
                self._record_deterministic_tool_response(
                    function_response_parts,
                    final_text,
                )
                log_event(
                    "INFO",
                    "llm.deterministic_post_mutation_response",
                    provider=self.provider_name,
                    session_id=session_id,
                    tool=last_tool,
                )
                log_event(
                    "DEBUG",
                    "assistant.response",
                    session_id=session_id,
                    text=final_text,
                )
                return final_text

            tool_rounds += 1

            response = self._send_to_gemini(
                function_response_parts,
                stage="GEMINI_AFTER_TOOL",
                transaction_applied=transaction_applied,
                last_tool=last_tool,
            )

        final_text = self.runtime.sanitize_user_text(response.text or "")
        final_text = self.runtime.ensure_next_step(
            final_text,
            transaction_applied,
        )

        log_event(
            "DEBUG",
            "assistant.response",
            session_id=session_id,
            text=final_text,
        )

        return final_text
