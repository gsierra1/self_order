"""Protocolo WebSocket para turnos de texto y audio de un mismo pedido."""

import asyncio
import json
import time
import unicodedata
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect

from backend.ai.errors import AIProviderError
from backend.ai.contracts import (
    SpeechToText,
    SpeechToTextConnectionTimeout,
    SpeechToTextConfigurationError,
    SpeechToTextFinalizationTimeout,
)
from backend.ai.factories import create_speech_to_text
from backend.ai.order_tools_runtime import OrderToolsRuntime
from backend.api.conversation_guards import (
    get_ambiguous_removal_message,
    is_cart_query,
)
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


def _is_payment_methods_question(text: str) -> bool:
    """Distingue una consulta sobre medios de pago de una elección concreta.

    Args:
        text: Texto transcripto o escrito por la persona.

    Returns:
        ``True`` si la persona pregunta qué opciones de pago existen; ``False``
        si la frase debe continuar por el flujo normal de interpretación.
    """
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    normalized = " ".join(normalized.split())
    question_patterns = (
        "CON QUE PUEDO PAGAR",
        "COMO PUEDO PAGAR",
        "QUE MEDIOS DE PAGO",
        "CUALES SON LOS MEDIOS DE PAGO",
        "QUE METODOS DE PAGO",
        "CUALES SON LOS METODOS DE PAGO",
        "QUE FORMAS DE PAGO",
        "CUALES SON LAS FORMAS DE PAGO",
        "QUE OPCIONES DE PAGO",
        "CUALES SON LAS OPCIONES DE PAGO",
    )
    return any(pattern in normalized for pattern in question_patterns)


def _get_stt_label(audio: SpeechToText) -> str:
    """Convierte el identificador técnico del STT en un nombre visible.

    Args:
        audio: Adaptador de transcripción que produjo el evento o error.

    Returns:
        Nombre breve y legible del proveedor de voz seleccionado.
    """
    labels = {"gemini": "Gemini", "vosk": "Vosk"}
    return labels.get(audio.provider_name, audio.provider_name.capitalize())


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
        if runtime.service.session.state is SessionState.ACTIVE:
            ambiguous_removal = get_ambiguous_removal_message(runtime.service, text)
            if ambiguous_removal is not None:
                await publish("assistant.text", {
                    "text": ambiguous_removal,
                    "cart": snapshot(runtime.service),
                    "session_closed": False,
                })
                log_event(
                    "INFO",
                    "conversation.ambiguous_removal",
                    session_id=session_id,
                    input_length=len(text),
                )
                return
            if is_cart_query(text):
                await publish("assistant.text", {
                    "text": OrderToolsRuntime(runtime.service).get_cart_summary(),
                    "cart": snapshot(runtime.service),
                    "session_closed": False,
                })
                log_event(
                    "INFO",
                    "conversation.cart_query",
                    session_id=session_id,
                    input_length=len(text),
                )
                return
        if runtime.service.session.state in {SessionState.ACTIVE, SessionState.PAYMENT_PENDING}:
            if _is_payment_methods_question(text):
                await publish("assistant.text", {
                    "text": "Podés pagar con QR, tarjeta o en caja.",
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

    async def process_turn(text: str | None, audio: SpeechToText | None) -> bool:
        """Procesa una sola entrada y libera la reserva incluso ante errores.

        Args:
            text: Mensaje escrito, o None para un turno hablado.
            audio: Transcriptor del turno, o None para entrada escrita.

        Returns:
            True si el frontend debe esperar la liberación explícita del turno
            antes de permitir un nuevo audio; False en los demás casos.

        Raises:
            asyncio.CancelledError: Si el navegador cancela un turno que todavía
                no llegó a interpretar el pedido.

        Effects:
            Cierra el transcriptor aun si el proveedor falla, sin alterar el
            carrito antes de disponer de texto final.
        """
        try:
            if audio is not None:
                try:
                    text = await audio.transcribe(publish)
                except SpeechToTextConfigurationError as exc:
                    provider_label = _get_stt_label(audio)
                    log_event(
                        "WARN",
                        "voice.configuration_error",
                        session_id=session_id,
                        provider=audio.provider_name,
                    )
                    await publish("voice.error", {
                        "message": str(exc),
                        "stage": "VOICE_CONFIGURATION",
                        "source": provider_label,
                        "retryable": False,
                    })
                    return False
                except SpeechToTextConnectionTimeout as exc:
                    provider_label = _get_stt_label(audio)
                    log_event(
                        "WARN",
                        "voice.connection_timeout",
                        session_id=session_id,
                        provider=audio.provider_name,
                    )
                    await publish("voice.error", {
                        "message": (
                            f"No se pudo iniciar la transcripción con {provider_label}. "
                            "El pedido no cambió; podés volver a hablar o escribir."
                        ),
                        "stage": "VOICE_CONNECTION",
                        "source": provider_label,
                        "retryable": True,
                    })
                    return True
                except SpeechToTextFinalizationTimeout as exc:
                    provider_label = _get_stt_label(audio)
                    log_event(
                        "WARN",
                        "voice.finalization_timeout",
                        session_id=session_id,
                        provider=audio.provider_name,
                    )
                    await publish("voice.error", {
                        "message": (
                            f"{provider_label} recibió el audio, pero no devolvió una "
                            "transcripción final a tiempo. El pedido no cambió; "
                            "podés volver a hablar o escribir."
                        ),
                        "stage": "VOICE_FINALIZATION",
                        "source": provider_label,
                        "retryable": True,
                    })
                    return True
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
                    return False
                except Exception as exc:
                    log_event("WARN", "voice.error", session_id=session_id,
                              exception_type=type(exc).__name__)
                    await publish("voice.error", {
                        "message": "No se pudo transcribir el audio. El pedido no cambió; podés escribir o volver a hablar.",
                    })
                    return False
                await publish("voice.transcript", {"text": text, "final": True})
                log_event("INFO", "voice.turn_transcribed", session_id=session_id, transcript_length=len(text))
                audio.processing_order = True
            await execute(text)
            return False
        finally:
            if audio is not None:
                await audio.close()

    def release_turn(task: asyncio.Task, audio: SpeechToText | None) -> None:
        """Libera la reserva incluso si se cancela antes de iniciar la coroutine.

        Args:
            task: Tarea del turno que ya terminó.
            audio: Adaptador asociado a la tarea terminada, si era un turno de voz.

        Returns:
            None.

        Effects:
            Libera la exclusión de turnos y descarta la referencia al adaptador
            finalizado sin afectar un turno posterior.
        """
        nonlocal transcriber
        runtime.turn_lock.release()
        if transcriber is audio:
            transcriber = None
        retry_ready = (
            not task.cancelled()
            and task.exception() is None
            and task.result()
        )
        if retry_ready:
            asyncio.create_task(publish("voice.retry_ready", {}))
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
                        audio_to_cancel = transcriber
                        if audio_to_cancel.processing_order:
                            raise ValueError("El pedido ya se está procesando; esperá la respuesta.")
                        audio_to_cancel.cancel()
                        turn_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await turn_task
                        await audio_to_cancel.close()
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
                turn_task.add_done_callback(lambda task, audio=transcriber: release_turn(task, audio))
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
