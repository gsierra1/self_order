"""Contratos de los bordes de IA que no conocen las reglas del pedido."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


VoiceEventPublisher = Callable[[str, dict], Awaitable[None]]


class SpeechToTextConnectionTimeout(TimeoutError):
    """Indica que el proveedor STT no pudo abrir el turno de voz a tiempo."""


class SpeechToTextFinalizationTimeout(TimeoutError):
    """Indica que el proveedor STT recibió audio pero no confirmó texto final."""


class SpeechToTextConfigurationError(RuntimeError):
    """Indica que el STT elegido no puede prepararse con su configuración local."""


class SpeechToText(ABC):
    """Define un turno de voz por streaming sin conocer carrito ni tools."""

    provider_name: str

    @property
    @abstractmethod
    def processing_order(self) -> bool:
        """Indica si el texto final ya comenzó a interpretarse como pedido.

        Returns:
            True cuando cancelar el turno podría interrumpir una operación del
            pedido; False mientras solo hay audio o transcripción pendiente.
        """

    @processing_order.setter
    @abstractmethod
    def processing_order(self, value: bool) -> None:
        """Actualiza si el turno ya ingresó al intérprete de pedidos.

        Args:
            value: Estado de procesamiento del texto final.
        """

    @abstractmethod
    def feed(self, chunk: bytes) -> None:
        """Recibe un fragmento de audio del turno activo.

        Args:
            chunk: Audio codificado según el formato aceptado por el adaptador.

        Raises:
            ValueError: Si el turno no admite más audio o el fragmento es inválido.
        """

    @abstractmethod
    def finish(self) -> None:
        """Indica que no llegarán más fragmentos de audio en este turno.

        Raises:
            ValueError: Si no se puede terminar el turno sin perder audio.
        """

    @abstractmethod
    def cancel(self) -> None:
        """Descarta audio y texto pendientes antes de interpretar el pedido."""

    @abstractmethod
    async def transcribe(self, publish: VoiceEventPublisher) -> str:
        """Publica avances y devuelve el texto final de un turno de voz.

        Args:
            publish: Callback asíncrono para eventos de preparación y texto.

        Returns:
            Transcripción final que puede enviarse al intérprete de pedidos.

        Raises:
            TimeoutError: Si el proveedor no completa el turno a tiempo.
            ValueError: Si no se puede obtener un texto final válido.
            RuntimeError: Si el proveedor no permite completar la transcripción.
        """

    @abstractmethod
    async def close(self) -> None:
        """Libera recursos del proveedor asociados al turno de voz."""


class OrderInterpreter(ABC):
    """Interpreta lenguaje natural y solo propone operaciones autorizadas."""

    provider_name: str

    @abstractmethod
    def send_message(self, message: str) -> str:
        """Interpreta un mensaje mediante tools ligadas al OrderService.

        Args:
            message: Texto final escrito o transcrito por el usuario.

        Returns:
            Respuesta apta para mostrar al usuario.

        Raises:
            ValueError: Si el mensaje no se puede interpretar como entrada válida.
            RuntimeError: Si el proveedor o sus tools no completan el turno.
        """

    @abstractmethod
    def close(self) -> None:
        """Libera recursos de conversación del proveedor si los hubiera."""
