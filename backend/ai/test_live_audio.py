import asyncio
from pathlib import Path

from google.genai import types

from backend.ai.gemini_client import create_gemini_client


MODEL = "gemini-3.1-flash-live-preview"

AUDIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "sample.pcm"
)

# PCM mono, 16 bits, 16 kHz:
# 16000 muestras/s × 2 bytes × 0.1 s = 3200 bytes.
CHUNK_SIZE = 3200


async def receive_response(
    session,
) -> None:
    """
    Recibe e imprime los eventos devueltos por Gemini Live.

    Muestra transcripciones de entrada y salida hasta que Gemini indique que
    terminó de generar la respuesta.

    Args:
        session: Sesión activa de Gemini Live.

    Returns:
        None.
    """
    async for response in session.receive():
        server_content = response.server_content

        if server_content is None:
            continue

        interim_transcription = (
            server_content.interim_input_transcription
        )

        if (
            interim_transcription
            and interim_transcription.text
        ):
            print(
                "Audio parcial:",
                interim_transcription.text,
            )

        input_transcription = (
            server_content.input_transcription
        )

        if (
            input_transcription
            and input_transcription.text
        ):
            print(
                "Audio entendido:",
                input_transcription.text,
            )

        output_transcription = (
            server_content.output_transcription
        )

        if (
            output_transcription
            and output_transcription.text
        ):
            print(
                "Gemini:",
                output_transcription.text,
            )

        if server_content.generation_complete:
            print(
                "Generación finalizada."
            )
            return


async def test_live_audio() -> None:
    """
    Verifica que Gemini Live pueda recibir y comprender audio PCM.

    El audio se transmite en fragmentos de aproximadamente 100 ms y los
    límites del turno se indican explícitamente para no depender del VAD
    automático.

    Returns:
        None.

    Raises:
        FileNotFoundError: Si no existe el archivo PCM de prueba.
        TimeoutError: Si Gemini no devuelve una respuesta en el tiempo límite.
    """
    if not AUDIO_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de audio: {AUDIO_PATH}"
        )

    audio_bytes = AUDIO_PATH.read_bytes()

    print(
        f"Audio cargado: {len(audio_bytes)} bytes"
    )

    client = create_gemini_client()

    config = types.LiveConnectConfig(
        response_modalities=[
            "AUDIO"
        ],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=(
                types.AutomaticActivityDetection(
                    disabled=True
                )
            )
        ),
        input_audio_transcription=(
            types.AudioTranscriptionConfig()
        ),
        output_audio_transcription=(
            types.AudioTranscriptionConfig()
        ),
    )

    print(
        "Conectando con Gemini Live..."
    )

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:
        print(
            "Sesión Live conectada."
        )

        print(
            "Indicando inicio de actividad..."
        )

        await session.send_realtime_input(
            activity_start=types.ActivityStart()
        )

        print(
            "Enviando audio..."
        )

        for start in range(
            0,
            len(audio_bytes),
            CHUNK_SIZE,
        ):
            chunk = audio_bytes[
                start:start + CHUNK_SIZE
            ]

            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type="audio/pcm;rate=16000",
                )
            )

            # Simula la llegada del audio en tiempo real.
            await asyncio.sleep(
                0.1
            )

        print(
            "Audio enviado."
        )

        print(
            "Indicando fin de actividad..."
        )

        await session.send_realtime_input(
            activity_end=types.ActivityEnd()
        )

        print(
            "Esperando respuesta de Gemini..."
        )

        try:
            async with asyncio.timeout(
                20
            ):
                await receive_response(
                    session
                )

        except TimeoutError:
            print(
                "TIMEOUT: Gemini no devolvió una respuesta "
                "completa en 20 segundos."
            )
            raise


if __name__ == "__main__":
    asyncio.run(
        test_live_audio()
    )