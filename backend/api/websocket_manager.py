import asyncio

from fastapi import WebSocket


class WebSocketManager:
    """
    Administra las conexiones WebSocket activas de las sesiones.

    Cada sesión puede mantener una conexión con el navegador para recibir
    eventos generados por el backend en tiempo real.
    """

    def __init__(self) -> None:
        """
        Inicializa el administrador de conexiones WebSocket.
        """
        self.connections: dict[str, WebSocket] = {}
        self.send_locks: dict[str, asyncio.Lock] = {}
        self.event_loop: asyncio.AbstractEventLoop | None = None

    async def connect(
        self,
        session_id: str,
        websocket: WebSocket,
    ) -> bool:
        """
        Acepta y registra una conexión WebSocket.

        También conserva una referencia al event loop de FastAPI para permitir
        que código síncrono ejecutado en otros threads publique eventos.

        Args:
            session_id: Identificador técnico de la sesión.
            websocket: Conexión WebSocket iniciada por el navegador.

        Returns:
            True si se aceptó la conexión; False si la sesión ya tiene otra.
        """
        if session_id in self.connections:
            await websocket.close(code=4409)
            return False
        await websocket.accept()

        self.event_loop = asyncio.get_running_loop()

        self.connections[session_id] = websocket
        self.send_locks[session_id] = asyncio.Lock()
        return True

    def disconnect(
        self,
        session_id: str,
    ) -> None:
        """
        Elimina una conexión WebSocket registrada.

        Args:
            session_id: Identificador técnico de la sesión desconectada.
        """
        self.connections.pop(
            session_id,
            None,
        )

        self.send_locks.pop(session_id, None)

    async def send_event(
        self,
        session_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """
        Envía un evento estructurado a una sesión conectada.

        Args:
            session_id: Identificador técnico de la sesión destinataria.
            event_type: Tipo semántico del evento enviado.
            data: Información asociada al evento.
        """
        websocket = self.connections.get(
            session_id
        )

        lock = self.send_locks.get(session_id)
        if websocket is None or lock is None:
            return
        async with lock:
            if self.connections.get(session_id) is websocket:
                await websocket.send_json({"type": event_type, "data": data})

    def send_event_threadsafe(
        self,
        session_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """
        Programa el envío de un evento desde código síncrono.

        FastAPI puede ejecutar operaciones síncronas de negocio en un thread
        diferente del event loop utilizado por WebSocket. Este método permite
        publicar el evento de forma segura sobre el loop correspondiente.

        Args:
            session_id: Identificador técnico de la sesión destinataria.
            event_type: Tipo semántico del evento enviado.
            data: Información asociada al evento.
        """
        if (
            self.event_loop is None
            or self.event_loop.is_closed()
        ):
            return

        asyncio.run_coroutine_threadsafe(
            self.send_event(
                session_id=session_id,
                event_type=event_type,
                data=data,
            ),
            self.event_loop,
        )
