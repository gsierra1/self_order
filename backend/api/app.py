from dataclasses import dataclass, field
from threading import Lock
from pathlib import Path
from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.errors import AIProviderError
from backend.ai.orchestrator import OrderConversationOrchestrator
from backend.api.websocket_manager import WebSocketManager
from backend.api.conversation_socket import handle_conversation
from backend.domain.menu import load_menu
from backend.domain.session import Session, SessionState
from backend.logging.event_logger import log_event
from backend.services.order_service import OrderService
from config.settings import get_chat_model


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MENU_PATH = (
    PROJECT_ROOT
    / "config"
    / "menu.json"
)

FRONTEND_DIR = (
    PROJECT_ROOT
    / "frontend"
)


app = FastAPI(
    title="SIA Self Order API",
    description=(
        "Backend de la prueba de concepto del sistema "
        "conversacional de autoservicio."
    ),
    version="0.1.0",
)


app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR
    ),
    name="static",
)


menu = load_menu(MENU_PATH)


@dataclass
class SessionRuntime:
    """
    Agrupa los componentes asociados a una sesión activa.

    Attributes:
        service: Servicio que administra el estado real del pedido.
        assistant: Orquestador conversacional conectado a Gemini.
        turn_lock: Reserva compartida entre HTTP, texto WebSocket y voz.
    """

    service: OrderService
    assistant: OrderConversationOrchestrator
    turn_lock: Lock = field(default_factory=Lock)


sessions: dict[str, SessionRuntime] = {}

websocket_manager = WebSocketManager()


def serialize_cart(
    service: OrderService,
) -> dict:
    """
    Convierte el carrito actual en una representación serializable.

    La información corresponde siempre al estado real mantenido por
    OrderService y no al contenido textual generado por Gemini.

    Args:
        service: Servicio de pedidos cuya sesión se desea consultar.

    Returns:
        Diccionario con los productos, total y estado de la sesión.
    """
    cart = service.get_cart()

    return {
        "items": [
            {
                "line_id": item.line_id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "selected_modifiers": (
                    item.selected_modifiers
                ),
                "unit_price": item.unit_price,
            }
            for item in cart.items
        ],
        "total": cart.total,
        "state": service.session.state.value,
        "order_number": service.session.order_number,
        "payment_method": service.session.payment_method,
    }


def get_runtime(
    session_id: str,
) -> SessionRuntime:
    """
    Obtiene los componentes asociados a una sesión existente.

    Args:
        session_id: Identificador técnico de la sesión.

    Returns:
        Contexto de ejecución correspondiente a la sesión.

    Raises:
        HTTPException: Si la sesión indicada no existe.
    """
    runtime = sessions.get(
        session_id
    )

    if runtime is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    return runtime


@app.get("/")
def frontend() -> FileResponse:
    """
    Devuelve la interfaz principal del sistema de autoservicio.

    Returns:
        Archivo HTML correspondiente al frontend.
    """
    return FileResponse(
        FRONTEND_DIR / "index.html"
    )


@app.get("/api/health")
def health_check() -> dict:
    """
    Verifica que la API se encuentre disponible.

    Returns:
        Diccionario con el estado actual del servicio.
    """
    return {
        "status": "ok",
        "service": "self_order",
    }


@app.post("/api/sessions")
def create_session() -> dict:
    """
    Crea una nueva sesión conversacional de pedido.

    Se crea una sesión independiente junto con su OrderService y su
    orquestador conversacional. El OrderService recibe además un callback
    que permite publicar cambios del pedido hacia el navegador mediante
    WebSocket.

    Returns:
        Información inicial de la nueva sesión, incluyendo identificador,
        estado y carrito vacío.
    """
    session = Session()

    def publish_session_event(
        event_type: str,
        data: dict,
    ) -> None:
        """
        Publica un evento de la sesión hacia su conexión WebSocket.

        Args:
            event_type: Tipo semántico del evento generado.
            data: Información estructurada asociada al evento.
        """
        websocket_manager.send_event_threadsafe(
            session_id=session.session_id,
            event_type=event_type,
            data=data,
        )

    service = OrderService(
        menu=menu,
        session=session,
        event_callback=publish_session_event,
    )

    assistant = OrderConversationOrchestrator(
        service=service,
        model=get_chat_model(),
    )

    runtime = SessionRuntime(
        service=service,
        assistant=assistant,
    )

    sessions[
        session.session_id
    ] = runtime

    log_event(
        "INFO",
        "session.started",
        session_id=session.session_id,
    )

    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "cart": serialize_cart(service),
    }


@app.get(
    "/api/sessions/{session_id}/cart"
)
def get_cart(
    session_id: str,
) -> dict:
    """
    Obtiene el estado real del carrito asociado a una sesión.

    Args:
        session_id: Identificador técnico de la sesión.

    Returns:
        Estado estructurado del carrito.
    """
    runtime = get_runtime(
        session_id
    )

    return serialize_cart(
        runtime.service
    )


@app.post("/api/sessions/{session_id}/payment/start")
def start_payment(session_id: str) -> dict:
    """Prepara el pago desde el botón de confirmación del carrito.

    Args:
        session_id: Identificador técnico de la sesión.

    Returns:
        Carrito en espera de método de pago y número generado.

    Raises:
        HTTPException: Si el carrito está vacío o hay otro turno en curso.
    """
    runtime = get_runtime(session_id)
    if not runtime.turn_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Hay un turno en curso.")
    try:
        try:
            result = runtime.service.prepare_payment()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        runtime.turn_lock.release()
    return {"ok": True, **result, "cart": serialize_cart(runtime.service)}


@app.post("/api/sessions/{session_id}/payment/complete")
def complete_payment(session_id: str) -> dict:
    """Completa el pago de demostración y devuelve el número de pedido.

    Args:
        session_id: Identificador técnico de la sesión.

    Returns:
        Estado final, número de pedido y carrito confirmado.

    Raises:
        HTTPException: Si no se seleccionó un método o la sesión no espera
            pago.
    """
    runtime = get_runtime(session_id)
    if not runtime.turn_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Hay un turno en curso.")
    try:
        try:
            result = runtime.service.complete_payment()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        runtime.turn_lock.release()
    return {"ok": True, **result, "cart": serialize_cart(runtime.service)}


@app.post("/api/sessions/{session_id}/payment/back")
def return_to_order(session_id: str) -> dict:
    """Devuelve un pedido pendiente de pago a su carrito editable.

    Args:
        session_id: Identificador técnico de la sesión.

    Returns:
        Carrito activo conservado.

    Raises:
        HTTPException: Si la sesión no está pendiente de pago.
    """
    runtime = get_runtime(session_id)
    if not runtime.turn_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Hay un turno en curso.")
    try:
        try:
            runtime.service.return_to_order()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        runtime.turn_lock.release()
    return {"ok": True, "cart": serialize_cart(runtime.service)}


@app.delete("/api/sessions/{session_id}/cart/items/{line_id}")
def delete_cart_item(session_id: str, line_id: int) -> dict:
    """Elimina una línea del carrito desde un control explícito del frontend.

    Args:
        session_id: Identificador técnico de la sesión.
        line_id: Línea interna que se desea eliminar.

    Returns:
        Carrito actualizado por OrderService.

    Raises:
        HTTPException: Si la línea no existe o la sesión está cerrada.
    """
    runtime = get_runtime(session_id)
    if not runtime.turn_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Hay un turno en curso.")
    try:
        try:
            runtime.service.remove_item(line_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        runtime.turn_lock.release()
    return {"ok": True, "cart": serialize_cart(runtime.service)}


@app.post(
    "/api/sessions/{session_id}/messages"
)
def send_message(
    session_id: str,
    payload: dict,
):
    """
    Procesa un mensaje textual dentro de una sesión de pedido.

    Gemini interpreta la intención del usuario y puede solicitar tools,
    mientras que OrderService conserva la autoridad sobre las modificaciones
    reales del carrito.

    Reserva el turno para impedir que HTTP procese un mensaje mientras voz u
    otro mensaje de la misma sesión están en curso; en ese caso devuelve 409.

    Args:
        session_id: Identificador técnico de la sesión.
        payload: Cuerpo JSON que debe contener la clave "message".

    Returns:
        Respuesta del asistente junto con el carrito real y el estado actual.

    Raises:
        HTTPException: Si la sesión ya fue confirmada o el mensaje recibido
            no es válido.
    """
    runtime = get_runtime(
        session_id
    )

    service = runtime.service
    assistant = runtime.assistant

    if (
        service.session.state
        == SessionState.CONFIRMED
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "SESSION_CLOSED",
                "message": (
                    "El pedido ya fue confirmado y la sesión "
                    "no admite nuevos mensajes."
                ),
            },
        )

    message = payload.get(
        "message"
    )

    if (
        not isinstance(message, str)
        or not message.strip()
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "INVALID_MESSAGE",
                "message": (
                    "El campo 'message' debe contener texto."
                ),
            },
        )

    try:
        if not runtime.turn_lock.acquire(blocking=False):
            return JSONResponse(status_code=409, content={
                "ok": False, "error": {"message": "Hay un turno en curso."},
            })
        try:
            if service.session.state == SessionState.CONFIRMED:
                return JSONResponse(status_code=409, content={"ok": False})
            assistant_text = assistant.send_message(message.strip())
        finally:
            runtime.turn_lock.release()

        cart = serialize_cart(
            service
        )

        return {
            "ok": True,
            "session_id": session_id,
            "assistant_text": assistant_text,
            "cart": cart,
            "session_closed": (
                service.session.state
                == SessionState.CONFIRMED
            ),
        }

    except AIProviderError as exc:
        status_code = (
            exc.status_code
            if exc.status_code is not None
            else 502
        )

        return JSONResponse(
            status_code=status_code,
            content={
                "ok": False,
                "session_id": session_id,
                "error": {
                    "source": "gemini",
                    "type": exc.error_type,
                    "status_code": exc.status_code,
                    "stage": exc.stage,
                    "retryable": exc.retryable,
                    "transaction_applied": (
                        exc.transaction_applied
                    ),
                    "last_tool": exc.last_tool,
                    "message": exc.user_message,
                },
                "cart": serialize_cart(
                    service
                ),
                "session_closed": (
                    service.session.state
                    == SessionState.CONFIRMED
                ),
            },
        )

    except Exception as exc:
        log_event(
            "ERROR",
            "api.internal_error",
            exception=exc,
            session_id=session_id,
            endpoint="send_message",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "session_id": session_id,
                "error": {
                    "source": "backend",
                    "type": "INTERNAL_ERROR",
                    "message": (
                        "Ocurrió un error interno al procesar "
                        "la solicitud."
                    ),
                },
                "cart": serialize_cart(
                    service
                ),
                "session_closed": (
                    service.session.state
                    == SessionState.CONFIRMED
                ),
            },
        )


@app.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str) -> None:
    """Abre el canal de texto y voz de una sesión y delega su ciclo de vida.

    Args:
        websocket: Conexión iniciada por el navegador.
        session_id: Identificador técnico del pedido.
    """
    if session_id not in sessions:
        await websocket.close(code=4404)
        return
    if not await websocket_manager.connect(session_id, websocket):
        return
    await handle_conversation(
        websocket, sessions[session_id], websocket_manager, serialize_cart,
    )
