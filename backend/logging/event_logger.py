import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"

EVENTS_LOG_PATH = LOG_DIR / "events.jsonl"
RUNTIME_LOG_PATH = LOG_DIR / "runtime.log"


_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


_LEVEL_COLORS = {
    logging.DEBUG: "\033[90m",
    logging.INFO: "\033[37m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[91m",
}


_RESET_COLOR = "\033[0m"


# Campos que se conservan completos en events.jsonl, pero que se ocultan
# en la salida compacta para no saturar la terminal ni runtime.log.
_RUNTIME_HIDDEN_FIELDS = {
    "cart",
    "arguments",
    "text",
    "response_text",
    "technical_message",
}


class JsonEventFormatter(logging.Formatter):
    """
    Convierte cada evento de logging en una línea JSON estructurada.

    El formato JSONL permite almacenar un objeto JSON independiente por línea,
    facilitando tanto la lectura manual como el procesamiento posterior con
    Python, bases de datos o herramientas de observabilidad.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Convierte un LogRecord en una representación JSON.

        Args:
            record: Registro generado por el sistema de logging de Python.

        Returns:
            Cadena JSON correspondiente al evento.
        """
        event_data = getattr(
            record,
            "event_data",
            {},
        )

        payload = {
            "level": _LEVEL_NAMES.get(
                record.levelno,
                record.levelname,
            ),
            "timestamp": datetime.now().astimezone().isoformat(
                timespec="milliseconds"
            ),
            "event": getattr(
                record,
                "event_name",
                record.getMessage(),
            ),
        }

        payload.update(event_data)

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )


class RuntimeFormatter(logging.Formatter):
    """
    Genera una representación compacta y legible para desarrolladores.

    Los campos voluminosos permanecen disponibles en events.jsonl, pero no se
    muestran en esta salida para facilitar la identificación rápida de eventos.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Convierte un LogRecord en una línea de texto compacta.

        Args:
            record: Registro generado por el sistema de logging de Python.

        Returns:
            Línea de texto preparada para runtime.log.
        """
        level = _LEVEL_NAMES.get(
            record.levelno,
            record.levelname,
        )

        timestamp = datetime.now().astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        event_name = getattr(
            record,
            "event_name",
            record.getMessage(),
        )

        event_data = getattr(
            record,
            "event_data",
            {},
        )

        visible_data = {
            key: value
            for key, value in event_data.items()
            if key not in _RUNTIME_HIDDEN_FIELDS
        }

        details = " | ".join(
            f"{key}={value}"
            for key, value in visible_data.items()
        )

        message = (
            f"[{level}] {timestamp} | {event_name}"
        )

        if details:
            message += f" | {details}"

        if record.exc_info:
            message += (
                "\n"
                + self.formatException(record.exc_info)
            )

        return message


class ColoredConsoleFormatter(RuntimeFormatter):
    """
    Genera una salida compacta y coloreada para la terminal.

    Los tracebacks completos se guardan en los archivos de log, pero no se
    imprimen automáticamente en consola para mantener una supervisión visual
    limpia.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Formatea y colorea un evento según su nivel.

        Args:
            record: Registro generado por el sistema de logging de Python.

        Returns:
            Línea compacta y coloreada para la terminal.
        """
        original_exc_info = record.exc_info

        try:
            record.exc_info = None
            message = super().format(record)
        finally:
            record.exc_info = original_exc_info

        color = _LEVEL_COLORS.get(
            record.levelno,
            "",
        )

        if not color:
            return message

        return f"{color}{message}{_RESET_COLOR}"


def configure_event_logger() -> logging.Logger:
    """
    Configura el logger central del proyecto.

    Se crean tres destinos de logging:

    - events.jsonl: registro estructurado completo desde nivel DEBUG.
    - runtime.log: registro legible para desarrolladores desde nivel INFO.
    - terminal: salida compacta y coloreada desde nivel INFO.

    Los archivos utilizan rotación para evitar un crecimiento indefinido.

    Returns:
        Logger central configurado para el proyecto.
    """
    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = logging.getLogger("self_order")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # ---------------------------------------------------------
    # events.jsonl
    # Registro estructurado completo.
    # ---------------------------------------------------------

    json_handler = RotatingFileHandler(
        EVENTS_LOG_PATH,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )

    json_handler.setLevel(logging.DEBUG)
    json_handler.setFormatter(
        JsonEventFormatter()
    )

    logger.addHandler(json_handler)

    # ---------------------------------------------------------
    # runtime.log
    # Registro compacto para lectura humana.
    # ---------------------------------------------------------

    runtime_handler = RotatingFileHandler(
        RUNTIME_LOG_PATH,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )

    runtime_handler.setLevel(logging.INFO)
    runtime_handler.setFormatter(
        RuntimeFormatter()
    )

    logger.addHandler(runtime_handler)

    # ---------------------------------------------------------
    # Consola
    # Monitoreo visual durante desarrollo.
    # ---------------------------------------------------------

    console_handler = logging.StreamHandler()

    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        ColoredConsoleFormatter()
    )

    logger.addHandler(console_handler)

    return logger


LOGGER = configure_event_logger()


def log_event(
    level: str,
    event: str,
    *,
    exception: BaseException | None = None,
    **data: Any,
) -> None:
    """
    Registra un evento estructurado en los destinos configurados.

    Si se proporciona una excepción, el traceback completo queda almacenado
    en los archivos de logging para facilitar el debugging.

    Args:
        level: Nivel del evento. Valores admitidos: DEBUG, INFO, WARN,
            WARNING, ERROR y CRITICAL.
        event: Nombre semántico del evento, por ejemplo "session.started",
            "cart.updated" o "gemini.error".
        exception: Excepción asociada al evento, si existe.
        **data: Información estructurada adicional asociada al evento.

    Raises:
        ValueError: Si se indica un nivel de logging no soportado.
    """
    normalized_level = level.upper()

    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level_number = levels.get(
        normalized_level
    )

    if level_number is None:
        raise ValueError(
            f"Unsupported log level: {level}"
        )

    exc_info = None

    if exception is not None:
        exc_info = (
            type(exception),
            exception,
            exception.__traceback__,
        )

    LOGGER.log(
        level_number,
        event,
        extra={
            "event_name": event,
            "event_data": data,
        },
        exc_info=exc_info,
    )