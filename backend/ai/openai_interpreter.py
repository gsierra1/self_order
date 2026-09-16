"""Interprete OpenAI que conserva OrderService como autoridad transaccional."""

import json
from types import SimpleNamespace

from openai import APIConnectionError, APIStatusError, APITimeoutError

from backend.ai.contracts import OrderInterpreter
from backend.ai.errors import AIProviderError
from backend.ai.openai_client import create_openai_client
from backend.ai.order_tools_runtime import OrderToolsRuntime
from backend.logging.event_logger import log_event
from backend.services.order_service import OrderService


class OpenAIOrderInterpreter(OrderInterpreter):
    """Implementa OrderInterpreter con Chat Completions y function calling."""

    provider_name = "openai"
    provider_label = "OpenAI"
    max_completion_tokens: int | None = None

    def __init__(
        self,
        service: OrderService,
        model: str,
        max_tool_rounds: int = 5,
    ) -> None:
        """Inicializa historial, herramientas y cliente del proveedor.

        Args:
            service: Autoridad que valida cada operacion solicitada.
            model: Modelo de chat con function calling compatible.
            max_tool_rounds: Maximo de rondas de tools por mensaje.

        Raises:
            ValueError: Si max_tool_rounds no es positivo.
            RuntimeError: Si falta la credencial del proveedor concreto.
        """
        if max_tool_rounds <= 0:
            raise ValueError("max_tool_rounds debe ser mayor que cero.")
        self.service = service
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.runtime = OrderToolsRuntime(service)
        self.available_tools = self.runtime.available_tools
        self.client = self._create_client()
        self.messages = [{
            "role": "system",
            "content": self.runtime.build_system_instruction(),
        }]
        log_event(
            "INFO",
            f"{self.provider_name}_interpreter.started",
            session_id=service.session.session_id,
            model=model,
        )

    def close(self) -> None:
        """Cierra el cliente del proveedor sin modificar el pedido de la sesion."""
        self.client.close()

    def _create_client(self):
        """Crea el cliente compatible con Chat Completions del proveedor.

        Returns:
            Cliente sincronico que implementa Chat Completions.

        Raises:
            RuntimeError: Si faltan las credenciales del proveedor concreto.
        """
        return create_openai_client()

    def _tool_definitions(self) -> list[dict]:
        """Describe las tools autorizadas con el esquema de OpenAI.

        Returns:
            Lista de definiciones JSON para Chat Completions.
        """
        string_map = {
            "type": "object",
            "additionalProperties": {"type": "string"},
        }
        return [
            self._function("add_item", "Agrega un producto completo al carrito.", {
                "product_id": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
                "selected_modifiers": string_map,
            }, ["product_id"]),
            self._function("get_cart", "Consulta el carrito validado.", {}, []),
            self._function("change_modifier", "Cambia o quita un modificador de una linea.", {
                "line_id": {"type": "integer"},
                "modifier_group_id": {"type": "string"},
                "option_id": {"type": ["string", "null"]},
            }, ["line_id", "modifier_group_id"]),
            self._function("replace_item", "Reemplaza una linea por otro producto.", {
                "line_id": {"type": "integer"},
                "new_product_id": {"type": "string"},
                "selected_modifiers": string_map,
            }, ["line_id", "new_product_id"]),
            self._function("remove_item", "Elimina una linea del carrito.", {
                "line_id": {"type": "integer"},
            }, ["line_id"]),
            self._function("confirm_order", "Prepara el pedido para seleccionar pago.", {}, []),
            self._function("select_payment_method", "Selecciona QR, tarjeta o pago en caja.", {
                "method": {"type": "string", "enum": ["QR", "CARD", "CASH"]},
            }, ["method"]),
            self._function("return_to_order", "Vuelve a editar el carrito desde pago.", {}, []),
        ]

    def _function(
        self,
        name: str,
        description: str,
        properties: dict,
        required: list[str],
    ) -> dict:
        """Construye una definicion de function calling de OpenAI.

        Args:
            name: Nombre autorizado de la tool.
            description: Descripcion enviada al modelo.
            properties: Parametros JSON Schema de la tool.
            required: Parametros obligatorios del esquema.

        Returns:
            Definicion compatible con Chat Completions.
        """
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }

    def _request(
        self,
        *,
        stage: str,
        transaction_applied: bool,
        last_tool: str | None = None,
    ):
        """Solicita una respuesta del proveedor y traduce fallas al error comun.

        Args:
            stage: Etapa logica de la interpretacion.
            transaction_applied: Indica si ya cambio el carrito en este turno.
            last_tool: Ultima tool ejecutada, si existe.

        Returns:
            Respuesta de Chat Completions.

        Raises:
            AIProviderError: Si el proveedor rechaza o no puede atender la solicitud.
        """
        try:
            request = {
                "model": self.model,
                "messages": self.messages,
                "tools": self._tool_definitions(),
            }
            if self.max_completion_tokens is not None:
                request["max_tokens"] = self.max_completion_tokens
            return self.client.chat.completions.create(**request)
        except (APIStatusError, APIConnectionError, APITimeoutError) as exc:
            raise self._classify_error(
                exc, stage, transaction_applied, last_tool,
            ) from exc

    def _classify_error(
        self,
        exc: Exception,
        stage: str,
        transaction_applied: bool,
        last_tool: str | None,
    ) -> AIProviderError:
        """Convierte un error del proveedor en un mensaje seguro para el frontend.

        Args:
            exc: Excepcion emitida por el SDK compatible con OpenAI.
            stage: Etapa en la que ocurrio la falla.
            transaction_applied: Indica si el pedido ya fue mutado.
            last_tool: Ultima tool aplicada antes del error.

        Returns:
            Error estructurado y apto para publicar al navegador.
        """
        status_code = getattr(exc, "status_code", None)
        if status_code == 401:
            error_type, retryable = "AUTHENTICATION_ERROR", False
            message = f"{self.provider_label} rechazo la autenticacion de la aplicacion (401)."
        elif status_code == 404:
            error_type, retryable = "MODEL_NOT_FOUND", False
            message = f"El modelo {self.provider_label} configurado {self.model!r} no esta disponible (404)."
        elif status_code == 429:
            technical_message = str(exc).lower()
            if "credit_balance_exhausted" in technical_message or "no credits" in technical_message:
                error_type, retryable = "CREDIT_BALANCE_EXHAUSTED", False
                message = (
                    f"La cuenta de {self.provider_label} no tiene creditos disponibles para la API "
                    "(429). Configura facturacion o agrega creditos antes de reintentar."
                )
            else:
                error_type, retryable = "RATE_LIMIT", True
                message = f"{self.provider_label} alcanzo temporalmente un limite de uso (429)."
        elif status_code in {500, 502, 503, 504}:
            error_type, retryable = "SERVICE_UNAVAILABLE", True
            message = f"{self.provider_label} no esta disponible temporalmente ({status_code})."
        elif status_code is None:
            error_type, retryable = "NETWORK_ERROR", True
            message = f"No se pudo comunicar el backend con {self.provider_label}."
        else:
            error_type, retryable = "OPENAI_API_ERROR", False
            message = f"{self.provider_label} devolvio un error de API ({status_code})."
        suffix = (
            " La operacion del pedido ya se aplico; no la repitas."
            if transaction_applied
            else " El pedido no fue modificado por esta operacion."
        )
        return AIProviderError(
            provider=self.provider_label, model=self.model, error_type=error_type,
            status_code=status_code, api_status=None, stage=stage,
            retryable=retryable, transaction_applied=transaction_applied,
            last_tool=last_tool, technical_message=str(exc),
            user_message=message + suffix,
        )

    def send_message(self, message: str) -> str:
        """Interpreta un mensaje y ejecuta solo tools autorizadas por el servicio.

        Args:
            message: Texto final escrito o transcripto del usuario.

        Returns:
            Respuesta final segura para mostrar al usuario.

        Raises:
            ValueError: Si el mensaje esta vacio o una tool repite una mutacion.
            AIProviderError: Si el proveedor no completa una solicitud.
            RuntimeError: Si la respuesta no contiene texto final util.
        """
        if not message.strip():
            raise ValueError("El mensaje no puede estar vacio.")
        self.messages.append({"role": "user", "content": message})
        transaction_applied = False
        last_tool = None
        executed_calls: set = set()
        for tool_round in range(self.max_tool_rounds + 1):
            response = self._request(
                stage=(
                    f"{self.provider_name.upper()}_INTERPRETATION"
                    if not last_tool
                    else f"{self.provider_name.upper()}_AFTER_TOOL"
                ),
                transaction_applied=transaction_applied,
                last_tool=last_tool,
            )
            assistant_message = response.choices[0].message
            tool_calls = list(assistant_message.tool_calls or [])
            self.messages.append(assistant_message)
            if not tool_calls:
                return self.runtime.sanitize_user_text(
                    assistant_message.content or "",
                )
            if tool_round >= self.max_tool_rounds:
                raise RuntimeError("Se alcanzo el maximo de ciclos de tools permitidos.")
            calls = []
            for call in tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"{self.provider_label} devolvio argumentos JSON invalidos."
                    ) from exc
                calls.append(SimpleNamespace(name=call.function.name, args=arguments, call_id=call.id))
            self.runtime.validate_calls(calls, executed_calls)
            for call in calls:
                signature = (call.name, json.dumps(call.args, sort_keys=True, ensure_ascii=False))
                executed_calls.add(signature)
                result = self.runtime.execute(call)
                last_tool = call.name
                transaction_applied = transaction_applied or self.runtime.did_mutate(call.name, result)
                self.messages.append({
                    "role": "tool", "tool_call_id": call.call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        raise RuntimeError("Se alcanzo el maximo de ciclos de tools permitidos.")
