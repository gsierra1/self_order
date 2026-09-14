from google.genai import errors


class AIProviderError(RuntimeError):
    """
    Representa un error identificado en el proveedor de inteligencia artificial.

    Conserva información técnica suficiente para debugging y, al mismo tiempo,
    proporciona un mensaje limpio que puede mostrarse al usuario final.

    Attributes:
        provider: Proveedor de IA que produjo el error.
        model: Modelo utilizado cuando ocurrió el error.
        error_type: Clasificación interna del error.
        status_code: Código HTTP informado por el proveedor, si existe.
        api_status: Estado textual informado por la API, si existe.
        stage: Etapa del flujo conversacional en la que ocurrió el error.
        retryable: Indica si tiene sentido volver a intentar más adelante.
        transaction_applied: Indica si una modificación del pedido ya había
            sido aplicada antes de producirse el error.
        last_tool: Última tool ejecutada antes del error, si corresponde.
        technical_message: Mensaje técnico original del proveedor.
        user_message: Mensaje limpio destinado al usuario.
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        error_type: str,
        stage: str,
        retryable: bool,
        transaction_applied: bool,
        technical_message: str,
        user_message: str,
        status_code: int | None = None,
        api_status: str | None = None,
        last_tool: str | None = None,
    ):
        """
        Inicializa un error estructurado del proveedor de IA.

        Args:
            provider: Nombre del proveedor de IA.
            model: Modelo utilizado.
            error_type: Clasificación interna del error.
            stage: Etapa del procesamiento donde ocurrió.
            retryable: Indica si el error puede ser transitorio.
            transaction_applied: Indica si el carrito ya fue modificado.
            technical_message: Detalle técnico original.
            user_message: Mensaje destinado al usuario.
            status_code: Código HTTP, si está disponible.
            api_status: Estado textual de la API, si está disponible.
            last_tool: Última tool ejecutada, si corresponde.
        """
        super().__init__(user_message)

        self.provider = provider
        self.model = model
        self.error_type = error_type
        self.status_code = status_code
        self.api_status = api_status
        self.stage = stage
        self.retryable = retryable
        self.transaction_applied = transaction_applied
        self.last_tool = last_tool
        self.technical_message = technical_message
        self.user_message = user_message

    def to_dict(self) -> dict:
        """
        Convierte el error en una representación estructurada.

        Returns:
            Diccionario apto para logging, FastAPI o envío al frontend.
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "error_type": self.error_type,
            "status_code": self.status_code,
            "api_status": self.api_status,
            "stage": self.stage,
            "retryable": self.retryable,
            "transaction_applied": self.transaction_applied,
            "last_tool": self.last_tool,
            "technical_message": self.technical_message,
            "user_message": self.user_message,
        }


def classify_gemini_api_error(
    exc: errors.APIError,
    *,
    model: str,
    stage: str,
    transaction_applied: bool,
    last_tool: str | None = None,
) -> AIProviderError:
    """
    Clasifica un error HTTP devuelto por la API de Gemini.

    Args:
        exc: Excepción producida por el SDK de Google GenAI.
        model: Modelo de Gemini utilizado.
        stage: Etapa del procesamiento donde ocurrió el error.
        transaction_applied: Indica si una mutación del carrito ya fue
            completada antes del error.
        last_tool: Última tool ejecutada, si corresponde.

    Returns:
        Error estructurado con clasificación técnica y mensaje para el usuario.
    """
    code = exc.code
    api_status = exc.status
    technical_message = exc.message or str(exc)

    message_lower = technical_message.lower()

    if code == 429:
        if (
            "per minute" in message_lower
            or "rate limit" in message_lower
            or "retry in" in message_lower
        ):
            error_type = "RATE_LIMIT"
            user_message = (
                "Gemini alcanzó temporalmente el límite de solicitudes "
                "permitidas para este modelo (429)."
            )
        elif "quota" in message_lower:
            error_type = "QUOTA_EXCEEDED"
            user_message = (
                "La cuota disponible de Gemini para este modelo fue "
                "alcanzada (429)."
            )
        else:
            error_type = "RESOURCE_EXHAUSTED"
            user_message = (
                "Gemini rechazó la solicitud porque uno de sus límites "
                "de capacidad o cuota fue alcanzado (429)."
            )

        retryable = True

    elif code == 503:
        if (
            "high demand" in message_lower
            or "overload" in message_lower
            or "capacity" in message_lower
        ):
            error_type = "MODEL_OVERLOADED"
            user_message = (
                "El modelo de Gemini está temporalmente saturado "
                "y no pudo completar la solicitud (503)."
            )
        else:
            error_type = "SERVICE_UNAVAILABLE"
            user_message = (
                "El servicio de Gemini está temporalmente no disponible "
                "(503)."
            )

        retryable = True

    elif code == 404:
        error_type = "MODEL_NOT_FOUND"
        retryable = False
        user_message = (
            "Gemini no encontró el modelo configurado o ese modelo no "
            "admite esta operación (404)."
        )

    elif code == 401:
        error_type = "AUTHENTICATION_ERROR"
        retryable = False
        user_message = (
            "Gemini rechazó la autenticación de la aplicación (401)."
        )

    elif code == 403:
        error_type = "PERMISSION_ERROR"
        retryable = False
        user_message = (
            "Gemini rechazó la solicitud por permisos insuficientes (403)."
        )

    elif code == 400:
        error_type = "INVALID_REQUEST"
        retryable = False
        user_message = (
            "Gemini rechazó la solicitud porque contiene parámetros "
            "inválidos o incompatibles (400)."
        )

    elif code == 408:
        error_type = "REQUEST_TIMEOUT"
        retryable = True
        user_message = (
            "Gemini no respondió dentro del tiempo disponible (408)."
        )

    elif code in {500, 502, 504}:
        error_type = "PROVIDER_SERVER_ERROR"
        retryable = True
        user_message = (
            f"Gemini presentó un error temporal de servidor ({code})."
        )

    else:
        error_type = "GEMINI_API_ERROR"
        retryable = False
        user_message = (
            f"Gemini devolvió un error de API ({code})."
        )

    if transaction_applied:
        user_message += (
            " La operación del pedido ya había sido aplicada correctamente; "
            "no es necesario repetirla."
        )
    else:
        user_message += (
            " El pedido no fue modificado por esta operación."
        )

    return AIProviderError(
        provider="Gemini",
        model=model,
        error_type=error_type,
        status_code=code,
        api_status=api_status,
        stage=stage,
        retryable=retryable,
        transaction_applied=transaction_applied,
        last_tool=last_tool,
        technical_message=technical_message,
        user_message=user_message,
    )


def classify_gemini_transport_error(
    exc: Exception,
    *,
    model: str,
    stage: str,
    transaction_applied: bool,
    last_tool: str | None = None,
) -> AIProviderError | None:
    """
    Identifica errores de transporte producidos al comunicarse con Gemini.

    Solo clasifica como error de red excepciones provenientes de librerías de
    transporte conocidas. Los errores Python no relacionados se dejan sin
    clasificar para evitar atribuir incorrectamente fallas internas a Gemini.

    Args:
        exc: Excepción original.
        model: Modelo de Gemini utilizado.
        stage: Etapa del procesamiento donde ocurrió el error.
        transaction_applied: Indica si una mutación ya había sido aplicada.
        last_tool: Última tool ejecutada, si corresponde.

    Returns:
        AIProviderError si se reconoce un error de transporte; de lo contrario,
        None.
    """
    module_name = type(exc).__module__
    exception_name = type(exc).__name__

    transport_modules = (
        "httpx",
        "requests",
        "aiohttp",
    )

    if not module_name.startswith(transport_modules):
        return None

    user_message = (
        "No se pudo establecer o mantener la comunicación con Gemini."
    )

    if transaction_applied:
        user_message += (
            " La operación del pedido ya había sido aplicada correctamente; "
            "no es necesario repetirla."
        )
    else:
        user_message += (
            " El pedido no fue modificado por esta operación."
        )

    return AIProviderError(
        provider="Gemini",
        model=model,
        error_type="NETWORK_ERROR",
        status_code=None,
        api_status=None,
        stage=stage,
        retryable=True,
        transaction_applied=transaction_applied,
        last_tool=last_tool,
        technical_message=f"{exception_name}: {exc}",
        user_message=user_message,
    )