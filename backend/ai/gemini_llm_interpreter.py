import json
import re

from google.genai import errors, types

from backend.ai.contracts import OrderInterpreter
from backend.ai.errors import (
    AIProviderError,
    classify_gemini_api_error,
    classify_gemini_transport_error,
)
from backend.ai.gemini_client import create_gemini_client
from backend.ai.order_tools_runtime import OrderToolsRuntime
from backend.ai.tools import (
    create_add_item_tool,
    create_adjust_quantity_tool,
    create_change_modifier_tool,
    create_clear_cart_tool,
    create_confirm_order_tool,
    create_get_cart_tool,
    create_remove_item_tool,
    create_replace_item_tool,
    create_return_to_order_tool,
    create_return_to_payment_methods_tool,
    create_select_payment_method_tool,
)
from backend.logging.event_logger import log_event
from backend.services.order_service import OrderService


class GeminiOrderInterpreter(OrderInterpreter):
    """
    Orquesta la conversación entre el usuario, Gemini y OrderService.

    Gemini interpreta las solicitudes en lenguaje natural y propone llamadas
    a un conjunto explícito de tools. El orquestador controla qué operaciones
    están autorizadas, ejecuta las tools y devuelve sus resultados al modelo.

    Los eventos relevantes de la conversación, ejecución de tools y errores
    se registran mediante logging estructurado para facilitar debugging y
    observabilidad.
    """

    MUTATING_TOOLS = {
        "add_item",
        "adjust_quantity",
        "change_modifier",
        "replace_item",
        "remove_item",
        "clear_cart",
        "confirm_order",
        "select_payment_method",
        "return_to_order",
        "return_to_payment_methods",
    }

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

        self.available_tools = self._create_tools()

        self.client = create_gemini_client()

        self.chat = self.client.chats.create(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=self._build_system_instruction(),
                tools=list(self.available_tools.values()),
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

    def _create_tools(self) -> dict:
        """
        Crea las tools autorizadas para la sesión actual.

        Returns:
            Diccionario que relaciona nombres de tools con funciones Python.
        """
        add_item_tool = create_add_item_tool(self.service)
        adjust_quantity_tool = create_adjust_quantity_tool(self.service)
        get_cart_tool = create_get_cart_tool(self.service)
        change_modifier_tool = create_change_modifier_tool(self.service)
        replace_item_tool = create_replace_item_tool(self.service)
        remove_item_tool = create_remove_item_tool(self.service)
        clear_cart_tool = create_clear_cart_tool(self.service)
        confirm_order_tool = create_confirm_order_tool(self.service)
        select_payment_method_tool = create_select_payment_method_tool(self.service)
        return_to_order_tool = create_return_to_order_tool(self.service)
        return_to_payment_methods_tool = create_return_to_payment_methods_tool(self.service)

        return {
            "add_item": add_item_tool,
            "adjust_quantity": adjust_quantity_tool,
            "get_cart": get_cart_tool,
            "change_modifier": change_modifier_tool,
            "replace_item": replace_item_tool,
            "remove_item": remove_item_tool,
            "clear_cart": clear_cart_tool,
            "confirm_order": confirm_order_tool,
            "select_payment_method": select_payment_method_tool,
            "return_to_order": return_to_order_tool,
            "return_to_payment_methods": return_to_payment_methods_tool,
        }

    def _build_system_instruction(self) -> str:
        """
        Construye las instrucciones de comportamiento entregadas a Gemini.

        Incluye reglas transaccionales, tratamiento de información faltante
        y descripción del catálogo disponible.

        Returns:
            Instrucción de sistema utilizada durante la conversación.
        """
        catalog_lines = []

        for product in self.service.menu.products.values():
            catalog_lines.append(
                f"- {product.name}: product_id={product.id}, "
                f"precio base ARS {product.base_price}, "
                f"{'disponible' if product.available else 'agotado'}"
            )

            if product.aliases:
                catalog_lines.append(
                    f"  - También se puede pedir como: "
                    f"{', '.join(product.aliases)}"
                )

            for group in product.modifier_groups:
                option_ids = ", ".join(
                    f"{option.name} [id={option.id}] "
                    f"(+ARS {option.price_delta}, "
                    f"{'disponible' if option.available else 'agotado'})"
                    for option in group.options
                )

                required_text = (
                    "obligatorio"
                    if group.required
                    else "opcional"
                )

                catalog_lines.append(
                    f"  - {group.name} [grupo={group.id}] "
                    f"({required_text}): {option_ids}"
                )

        catalog = "\n".join(catalog_lines)

        return f"""
Sos la interfaz conversacional de un sistema de autoservicio de pedidos.

Tu función es interpretar lo que quiere el usuario y utilizar las tools
disponibles cuando sea necesario.

REGLAS TRANSACCIONALES:

- No inventes precios, descuentos, promociones, disponibilidad, stock,
  productos, grupos, variantes ni opciones ausentes del catálogo.
- No uses add_item, replace_item ni change_modifier para productos u opciones
  marcados como agotados. Informá que existen pero no están disponibles.
- Si un grupo obligatorio no tiene ninguna opción disponible, explicá que el
  producto no puede completarse por el momento; no pidas una elección imposible.
- Para una opcion agotada, informa la falta y ofrece solo alternativas disponibles.
- No modifiques directamente ningún dato del pedido.
- Las tools y OrderService son la autoridad sobre el estado transaccional.
- Para agregar productos utilizá add_item.
- Interpretá los aliases del catálogo como el producto indicado. Por ejemplo,
  si la persona pide una "hamburguesa simple", corresponde a la Burger Clásica.
- Si el usuario pregunta precios, menú u opciones, respondé con el catálogo y
  nunca utilices add_item solo para calcular o mostrar un precio.
- Para consultar el carrito utilizá get_cart.
- Para cambiar o quitar una opción de cualquier grupo utilizá
  change_modifier. Para quitar una opción opcional usá option_id=null.
- Para sustituir un producto utilizá replace_item.
- Si la persona pide sumar o quitar una cantidad de unidades de una línea,
  utilizá adjust_quantity con una variación relativa. Por ejemplo, "eliminá
  una" sobre una línea con cuatro unidades requiere delta=-1 y deja tres.
- Utilizá remove_item solamente cuando pida eliminar toda la línea.
- Para vaciar todo el carrito utilizá clear_cart una sola vez.
- Para finalizar el pedido utilizá confirm_order.
- confirm_order solo prepara el pago y devuelve las opciones; no cierres la
  sesión ni anuncies el pago confirmado todavía.
- Si el pedido ya está en `PAYMENT_PENDING`, no vuelvas a llamar confirm_order;
  utilizá únicamente select_payment_method o return_to_order.
- Para CASH decí siempre "En caja", nunca "efectivo". Para CARD indicá que la
  persona debe ingresar el número de su tarjeta; no menciones terminales.
- No uses tablas Markdown ni numeres líneas o alternativas. Presentá el carrito
  como una lista directa con producto, cantidad, modificadores y precio.
- No describas productos como "la opción mejor" ni agregues valoraciones que la
  persona no pidió. Decí "etcétera" en lugar de "etc.".
- Cuando el pedido esté pendiente de pago, utilizá select_payment_method
  con QR, CARD o CASH según lo que el usuario elija.
- Si el usuario quiere cambiar el método o volver a modificar el pedido,
  utilizá return_to_payment_methods para mostrar otra vez QR, tarjeta y caja.
  Utilizá return_to_order solo si quiere modificar los productos del carrito.
- Si el usuario pide varias operaciones independientes en una misma frase,
  podés emitir varias llamadas distintas; se ejecutarán en el orden recibido.
- Nunca emitas dos veces la misma operación con los mismos argumentos.

REGLAS SOBRE INFORMACIÓN FALTANTE:

- Nunca elijas un modificador obligatorio por defecto.
- Nunca supongas una opción si el usuario no la indicó explícitamente.
- Preguntá solamente por grupos obligatorios que existan en el catálogo y que
  el usuario todavía no haya respondido. Ofrecé únicamente las opciones
  listadas para ese grupo.
- Si el usuario ya indicó un producto y todos sus grupos obligatorios mediante
  nombres o aliases del catálogo, utilizá add_item inmediatamente. No preguntes
  subtipos, presentaciones ni distinciones que el catálogo no contiene.
- Si falta un modificador obligatorio, preguntale al usuario antes de agregar
  el producto.
- Si faltan varios modificadores obligatorios, podés preguntarlos juntos.
- Si el usuario ya indicó alguno, preguntá solamente los que todavía faltan.
- Conservá durante la conversación la información ya indicada mientras
  completás una misma solicitud.
- Si una referencia a un producto o línea es ambigua, pedí aclaración.
- Cuando necesites conocer el estado actual del carrito, utilizá get_cart.

FORMATO DE RESPUESTA:

- Expresate en español.
- Para montos anteponé el símbolo $, utilizá punto como separador de miles y
  decí explícitamente "pesos argentinos". Ejemplo: $12.500 pesos argentinos.
  No uses "USD" ni "dólares".
- Usá solamente los nombres visibles del catálogo para la persona. Los IDs de
  productos, grupos y opciones son internos y nunca deben aparecer en la
  respuesta escrita o hablada.

CATÁLOGO ACTUAL:

{catalog}
        """.strip()

    def _sanitize_user_text(self, text: str) -> str:
        """Elimina identificadores internos y símbolos ambiguos de la respuesta.

        Args:
            text: Texto final producido por Gemini.

        Returns:
            Texto preparado para mostrar y leer a la persona.
        """
        replacements = []

        for product in self.service.menu.products.values():
            replacements.append((product.id, product.name))

            for group in product.modifier_groups:
                replacements.append((group.id, group.name))

                for option in group.options:
                    replacements.append((option.id, option.name))

        replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

        for pattern, replacement in replacements:
            text = re.sub(
                rf"\b{re.escape(pattern)}\b",
                replacement,
                text,
            )
        text = re.sub(r"(?<=\d),(?=\d{3}\b)", ".", text)
        text = re.sub(
            r"\$\s*([0-9][0-9.]*)",
            r"\1 pesos argentinos",
            text,
        )
        text = re.sub(r"\bUSD\b", "pesos argentinos", text, flags=re.IGNORECASE)
        text = re.sub(r"\bdólares?\b", "pesos argentinos", text, flags=re.IGNORECASE)
        text = re.sub(r"\ben efectivo\b", "en caja", text, flags=re.IGNORECASE)
        text = re.sub(r"\befectivo\b", "en caja", text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?<![\w$])(\d+(?:\.\d{3})*)\s+pesos argentinos",
            r"$\1 pesos argentinos",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(?i)acercate a la terminal(?: o lectora)? para completar el pago de",
            "ingresá el número de tu tarjeta para completar el pago de",
            text,
        )
        return text

    def _execute_function_call(self, function_call) -> dict:
        """
        Ejecuta una function call si pertenece al conjunto autorizado.

        Los errores esperados de validación se devuelven de forma estructurada.
        Las excepciones inesperadas se registran como errores internos con su
        traceback completo y luego se propagan.

        Args:
            function_call: Function call solicitada por Gemini.

        Returns:
            Resultado estructurado de la ejecución.

        Raises:
            RuntimeError: Si Gemini solicita una función no autorizada.
            Exception: Si ocurre una falla interna inesperada.
        """
        tool = self.available_tools.get(function_call.name)

        if tool is None:
            log_event(
                "ERROR",
                "gemini_llm_interpreter.unauthorized_tool",
                session_id=self.service.session.session_id,
                tool=function_call.name,
            )

            raise RuntimeError(
                f"Gemini solicitó una función no permitida: "
                f"{function_call.name}"
            )

        arguments = dict(function_call.args or {})

        try:
            result = tool(**arguments)

            return {
                "ok": True,
                "result": result,
            }

        except ValueError as exc:
            log_event(
                "WARN",
                "tool.validation_error",
                session_id=self.service.session.session_id,
                tool=function_call.name,
                arguments=arguments,
                error=str(exc),
            )

            return {
                "ok": False,
                "error": str(exc),
            }

        except Exception as exc:
            log_event(
                "ERROR",
                "internal.error",
                exception=exc,
                session_id=self.service.session.session_id,
                component="GeminiOrderInterpreter",
                stage="TOOL_EXECUTION",
                tool=function_call.name,
                arguments=arguments,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )

            raise

    def _validate_function_calls(
        self,
        function_calls: list,
        executed_calls: set,
    ) -> None:
        """Verifica que un lote de llamadas no repita operaciones.

        Args:
            function_calls: Llamadas propuestas por Gemini en una respuesta.
            executed_calls: Firmas ya ejecutadas durante el turno actual.

        Raises:
            RuntimeError: Si una operación se repite en el turno.
        """
        batch_signatures = set()
        for function_call in function_calls:
            arguments = dict(function_call.args or {})
            signature = (
                function_call.name,
                json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str),
            )
            if signature in executed_calls or signature in batch_signatures:
                log_event(
                    "ERROR",
                    "gemini_llm_interpreter.duplicate_tool_call",
                    session_id=self.service.session.session_id,
                    tool=function_call.name,
                    arguments=arguments,
                )
                raise RuntimeError(
                    "Gemini intentó repetir exactamente la misma operación "
                    "dentro del mismo turno. La ejecución fue detenida para "
                    "evitar una mutación duplicada."
                )
            batch_signatures.add(signature)

    def _execute_function_call_with_response(
        self,
        function_call,
        executed_calls: set,
    ) -> tuple:
        """Ejecuta una llamada y construye la respuesta para Gemini.

        Args:
            function_call: Llamada solicitada por Gemini.
            executed_calls: Firmas ejecutadas durante el turno actual.

        Returns:
            Tupla con la parte de respuesta, nombre de tool y mutación realizada.
        """
        arguments = dict(function_call.args or {})
        signature = (
            function_call.name,
            json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str),
        )
        executed_calls.add(signature)
        log_event(
            "DEBUG",
            "tool.requested",
            session_id=self.service.session.session_id,
            tool=function_call.name,
            arguments=arguments,
        )

        result = self._execute_function_call(function_call)
        did_mutate = self._did_mutate(function_call.name, result)
        result_payload = result.get("result", {})
        if (
            result.get("ok")
            and isinstance(result_payload, dict)
            and result_payload.get("status") == "needs_clarification"
        ):
            log_event(
                "INFO",
                "tool.needs_clarification",
                session_id=self.service.session.session_id,
                tool=function_call.name,
                missing_modifier_groups=result_payload.get(
                    "missing_modifier_groups",
                    [],
                ),
            )
        elif result.get("ok"):
            log_event(
                "INFO",
                "tool.completed",
                session_id=self.service.session.session_id,
                tool=function_call.name,
                transaction_applied=did_mutate,
            )

        return (
            types.Part.from_function_response(
                name=function_call.name,
                response=result,
            ),
            function_call.name,
            did_mutate,
        )

    def _did_mutate(
        self,
        tool_name: str,
        execution_result: dict,
    ) -> bool:
        """
        Determina si una tool modificó efectivamente el pedido.

        Args:
            tool_name: Nombre de la tool ejecutada.
            execution_result: Resultado estructurado de su ejecución.

        Returns:
            True si la operación modificó el estado transaccional.
        """
        if not execution_result.get("ok"):
            return False

        if tool_name not in self.MUTATING_TOOLS:
            return False

        result = execution_result.get("result", {})

        if tool_name == "add_item":
            return result.get("status") == "added"

        if tool_name == "confirm_order":
            return result.get("status") != "payment_pending"

        return True

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
            Respuesta textual final generada por Gemini.

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

            function_calls = list(response.function_calls)

            if len(function_calls) > 1:
                log_event(
                    "INFO",
                    "gemini_llm_interpreter.multiple_function_calls",
                    session_id=session_id,
                    function_call_count=len(function_calls),
                )
            self._validate_function_calls(function_calls, executed_calls)
            function_response_parts = []

            for function_call in function_calls:
                (
                    function_response,
                    last_tool,
                    did_mutate,
                ) = self._execute_function_call_with_response(
                    function_call,
                    executed_calls,
                )
                function_response_parts.append(function_response)
                if did_mutate:
                    transaction_applied = True

            tool_rounds += 1

            response = self._send_to_gemini(
                function_response_parts,
                stage="GEMINI_AFTER_TOOL",
                transaction_applied=transaction_applied,
                last_tool=last_tool,
            )

        final_text = self._sanitize_user_text(response.text or "")
        final_text = OrderToolsRuntime(self.service).ensure_next_step(
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
