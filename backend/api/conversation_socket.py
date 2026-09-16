"""Protocolo WebSocket para turnos de texto y audio de un mismo pedido."""

import asyncio
import json
import time
import unicodedata
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect

from backend.ai.errors import AIProviderError
from backend.ai.contracts import SpeechToText
from backend.ai.factories import create_speech_to_text
from backend.domain.session import SessionState
from backend.logging.event_logger import log_event


def _detect_payment_method(text: str) -> str | None:
    """Detecta una opción de pago explícita durante la etapa de pago.

    Args:
        text: Texto transcripto o escrito por la persona.

    Returns:
        Código interno ``QR``, ``CARD`` o ``CASH`` cuando la frase contiene una
        opción inequívoca; ``None`` si debe interpretarla el LLM.
    """
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    if "TARJETA" in normalized:
        return "CARD"
    if "CAJA" in normalized or "EFECTIVO" in normalized:
        return "CASH"
    if "QR" in normalized:
        return "QR"
    return None


async def handle_conversation(websocket: WebSocket, runtime, manager, snapshot) -> None:
    """Recibe turnos, publica resultados y limpia audio/conexión al desconectar.

    Args:
        websocket: Conexión de navegador ya aceptada por el manager.
        runtime: Servicio, orquestador y exclusión mutua de la sesión.
        manager: Publicador de eventos WebSocket.
        snapshot: Función que serializa el carrito real.
    """
    session_id = runtime.service.session.session_id
    transcriber = None
    turn_task = None

    async def publish(event_type: str, data: dict) -> None:
        """Publica un evento en la conexión asociada a esta sesión.

        Args:
            event_type: Tipo del protocolo de conversación.
            data: Cuerpo serializable del evento.
        """
        await manager.send_event(session_id, event_type, data)

    async def execute(text: str) -> None:
        """Ejecuta el orquestador con la reserva de sesión ya adquirida.

        Args:
            text: Mensaje escrito o transcripción definitiva del usuario.
        """
        started_at = time.perf_counter()
        if runtime.service.session.state == SessionState.PAYMENT_PENDING:
            payment_method = _detect_payment_method(text)
            if payment_method is not None:
                try:
                    runtime.service.select_payment_method(payment_method)
                    labels = {"QR": "QR", "CARD": "tarjeta", "CASH": "caja"}
                    await publish("assistant.text", {
                        "text": f"Seleccioné el pago en {labels[payment_method]}.",
                        "cart": snapshot(runtime.service),
                        "session_closed": False,
                    })
                    log_event(
                        "INFO",
                        "conversation.completed",
                        session_id=session_id,
                        input_length=len(text),
                        duration_ms=round((time.perf_counter() - started_at) * 1000),
                    )
                    return
                except ValueError:
                    # Si la sesión cambió mientras llegaba el turno, conserva
                    # el flujo general y deja que el orquestador informe el estado.
                    pass
        worker = asyncio.create_task(asyncio.to_thread(runtime.assistant.send_message, text))
        try:
            response = await asyncio.shield(worker)
            await publish("assistant.text", {
                "text": response,
                "cart": snapshot(runtime.service),
                "session_closed": runtime.service.session.state == SessionState.CONFIRMED,
            })
            log_event(
                "INFO",
                "conversation.completed",
                session_id=session_id,
                input_length=len(text),
                duration_ms=round((time.perf_counter() - started_at) * 1000),
            )
        except asyncio.CancelledError:
            # Cancelar una coroutine no detiene el thread ni deshace una tool.
            with suppress(Exception):
                await worker
            raise
        except AIProviderError as exc:
            await publish("ai.error", {
                "message": exc.user_message,
                "type": exc.error_type,
                "transaction_applied": exc.transaction_applied,
                "stage": exc.stage,
                "source": runtime.assistant.provider_name,
                "status_code": exc.status_code,
                "retryable": exc.retryable,
                "last_tool": exc.last_tool,
                "cart": snapshot(runtime.service),
            })
        except Exception as exc:
            log_event("ERROR", "conversation.error", exception_type=type(exc).__name__,
                      session_id=session_id)
            await publish("backend.error", {
                "message": "No se pudo completar la respuesta. Revisá el carrito antes de repetir.",
                "cart": snapshot(runtime.service),
            })

    async def process_turn(text: str | None, audio: SpeechToText | None) -> None:
        """Procesa una sola entrada y libera la reserva incluso ante errores.

        Args:
            text: Mensaje escrito, o None para un turno hablado.
            audio: Transcriptor del turno, o None para entrada escrita.
        """
        if audio is not None:
            try:
                text = await audio.transcribe(publish)
            except asyncio.CancelledError:
                raise
            except AIProviderError as exc:
                log_event(
                    "WARN",
                    "voice.provider_error",
                    session_id=session_id,
                    **exc.to_dict(),
                )
                await publish("voice.error", {
                    "message": exc.user_message,
                    "type": exc.error_type,
                    "source": audio.provider_name,
                    "status_code": exc.status_code,
                    "retryable": exc.retryable,
                    "stage": exc.stage,
                })
                return
            except Exception as exc:
                log_event("WARN", "voice.error", session_id=session_id,
                          exception_type=type(exc).__name__)
                message = (
                    "La transcripción tardó demasiado en responder. El pedido "
                    "no cambió; podés intentar nuevamente o escribir."
                    if isinstance(exc, TimeoutError)
                    else "No se pudo transcribir el audio. El pedido no cambió; "
                    "podés escribir o volver a hablar."
                )
                await publish("voice.error", {
                    "message": message,
                })
                return
            await publish("voice.transcript", {"text": text, "final": True})
            log_event("INFO", "voice.turn_transcribed", session_id=session_id, transcript_length=len(text))
            audio.processing_order = True
        await execute(text)

    def release_turn(task: asyncio.Task) -> None:
        """Libera la reserva incluso si se cancela antes de iniciar la coroutine.

        Args:
            task: Tarea del turno que ya terminó.
        """
        runtime.turn_lock.release()
        if not task.cancelled() and task.exception() is not None:
            log_event("WARN", "conversation.delivery_failed", session_id=session_id,
                      exception_type=type(task.exception()).__name__)

    try:
        await publish("connection.ready", {
            "session_id": session_id,
            "cart": snapshot(runtime.service),
            "state": runtime.service.session.state.value,
        })
        while True:
            incoming = await websocket.receive()
            if incoming["type"] == "websocket.disconnect":
                break
            audio_bytes = incoming.get("bytes")
            if audio_bytes is not None:
                if transcriber is None or turn_task is None or turn_task.done():
                    await publish("client.error", {"message": "Primero iniciá un turno de voz."})
                    continue
                if transcriber.processing_order:
                    await publish("client.error", {"message": "El turno de audio ya fue enviado."})
                    continue
                try:
                    transcriber.feed(audio_bytes)
                except ValueError as exc:
                    turn_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await turn_task
                    transcriber = None
                    await publish("voice.error", {"message": str(exc)})
                continue
            try:
                message = json.loads(incoming.get("text") or "")
                if not isinstance(message, dict) or not isinstance(message.get("data", {}), dict):
                    raise ValueError("El evento y sus datos deben ser objetos JSON.")
                event_type = message.get("type")
                data = message.get("data", {})
                if event_type == "audio.cancel":
                    if transcriber is not None and turn_task is not None and not turn_task.done():
                        if transcriber.processing_order:
                            raise ValueError("El pedido ya se está procesando; esperá la respuesta.")
                        transcriber.cancel()
                        turn_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await turn_task
                        await transcriber.close()
                    transcriber = None
                    await publish("voice.cancelled", {})
                    continue
                if event_type == "audio.stop":
                    if transcriber is not None and turn_task is not None and not turn_task.done():
                        try:
                            transcriber.finish()
                        except ValueError as exc:
                            turn_task.cancel()
                            with suppress(asyncio.CancelledError):
                                await turn_task
                            transcriber = None
                            await publish("voice.error", {"message": str(exc)})
                    continue
                if event_type not in {"audio.start", "user.text"}:
                    raise ValueError("Tipo de evento no soportado.")
                if runtime.service.session.state == SessionState.CONFIRMED:
                    raise ValueError("El pedido ya fue confirmado.")
                text = data.get("message") if event_type == "user.text" else None
                if event_type == "user.text" and (not isinstance(text, str) or not text.strip()):
                    raise ValueError("El mensaje debe contener texto.")
                if not runtime.turn_lock.acquire(blocking=False):
                    raise ValueError("Hay un turno en curso. Esperá su respuesta.")
                try:
                    transcriber = (
                        create_speech_to_text(session_id=session_id)
                        if event_type == "audio.start" else None
                    )
                except RuntimeError as exc:
                    runtime.turn_lock.release()
                    raise ValueError(str(exc)) from exc
                turn_task = asyncio.create_task(process_turn(
                    text.strip() if text is not None else None, transcriber,
                ))
                turn_task.add_done_callback(release_turn)
            except (ValueError, json.JSONDecodeError) as exc:
                await publish("client.error", {"message": str(exc)})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(session_id)
        if turn_task is not None:
            # Una transcripción se puede cancelar; una mutación en un thread no.
            # Si ya comenzó la interpretación, esperamos para conservar la reserva.
            if transcriber is not None and not transcriber.processing_order:
                transcriber.cancel()
                turn_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await turn_task
        if transcriber is not None:
            with suppress(Exception):
                await transcriber.close()
        log_event("INFO", "websocket.disconnected", session_id=session_id)
