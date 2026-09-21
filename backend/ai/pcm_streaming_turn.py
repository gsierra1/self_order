"""Ciclo común de un turno PCM enviado por fragmentos al backend."""

import asyncio

from backend.ai.contracts import SpeechToText


class PcmStreamingSpeechToText(SpeechToText):
    """Administra cola, límites y cancelación para adaptadores PCM de backend."""

    max_chunk_bytes = 32768
    max_audio_bytes = 16000 * 2 * 60

    def __init__(
        self,
        session_id: str | None,
        *,
        queue_full_message: str,
    ) -> None:
        """Inicializa el estado compartido de un turno de hasta 60 segundos.

        Args:
            session_id: Identificador usado para correlacionar eventos y logs.
            queue_full_message: Mensaje visible si el proveedor no consume la
                cola con suficiente velocidad.
        """
        self.session_id = session_id
        self.chunks: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=128)
        self.ended = False
        self.byte_count = 0
        self._processing_order = False
        self._queue_full_message = queue_full_message

    @property
    def processing_order(self) -> bool:
        """Indica si el texto final ya ingresó al intérprete del pedido.

        Returns:
            True cuando una cancelación podría interrumpir una operación.
        """
        return self._processing_order

    @processing_order.setter
    def processing_order(self, value: bool) -> None:
        """Actualiza si la transcripción final ya se está interpretando.

        Args:
            value: Estado de procesamiento que debe conservar el turno.
        """
        self._processing_order = value

    def feed(self, chunk: bytes) -> None:
        """Encola un fragmento PCM16 mono de 16 kHz sin bloquear el socket.

        Args:
            chunk: Fragmento binario con muestras de dos bytes.

        Raises:
            ValueError: Si el turno terminó, el fragmento no es válido, supera
                los límites o la cola está completa.

        Effects:
            Incrementa los bytes recibidos y agrega el fragmento al turno.
        """
        if (
            self.ended
            or not chunk
            or len(chunk) % 2
            or len(chunk) > self.max_chunk_bytes
        ):
            raise ValueError("Fragmento de audio inválido o turno finalizado.")
        self.byte_count += len(chunk)
        if self.byte_count > self.max_audio_bytes:
            raise ValueError("El turno de voz supera los 60 segundos.")
        try:
            self.chunks.put_nowait(chunk)
        except asyncio.QueueFull as exc:
            raise ValueError(self._queue_full_message) from exc

    def finish(self) -> None:
        """Encola una única marca de final después del audio recibido.

        Raises:
            ValueError: Si la cola está completa y no puede finalizarse sin
                perder audio.

        Effects:
            Impide nuevos fragmentos y señala el final al consumidor.
        """
        if self.ended:
            return
        self.ended = True
        try:
            self.chunks.put_nowait(None)
        except asyncio.QueueFull as exc:
            raise ValueError(
                "No se pudo finalizar el audio; volvé a intentar.",
            ) from exc

    def cancel(self) -> None:
        """Descarta el turno mientras no se esté procesando como pedido.

        Effects:
            Impide recibir más audio sin interrumpir una mutación ya iniciada.
        """
        if not self.processing_order:
            self.ended = True

    async def close(self) -> None:
        """Cierra el turno compartido y evita nuevos fragmentos de audio.

        Effects:
            Aplica la misma cancelación segura usada por el WebSocket.
        """
        self.cancel()
