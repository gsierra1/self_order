import asyncio

from backend.ai.gemini_client import create_gemini_client


MODEL = "gemini-3.1-flash-live-preview"


async def test_live_connection() -> None:
    """
    Verifica una conexión básica con Gemini Live.

    Abre una sesión Live, envía un mensaje textual y muestra en terminal
    la transcripción de la respuesta de audio generada por Gemini.

    Returns:
        None.
    """
    client = create_gemini_client()

    config = {
        "response_modalities": ["AUDIO"],
        "output_audio_transcription": {},
    }

    print("Conectando con Gemini Live...")

    async with client.aio.live.connect(
        model=MODEL,
        config=config,
    ) as session:
        print("Sesión Live conectada.")

        await session.send_client_content(
            turns={
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Respondeme brevemente en español: "
                            "¿podés escucharme mediante Gemini Live?"
                        )
                    }
                ],
            },
            turn_complete=True,
        )

        async for response in session.receive():
            server_content = response.server_content

            if server_content is None:
                continue

            if server_content.output_transcription:
                text = server_content.output_transcription.text

                if text:
                    print(
                        "Gemini:",
                        text,
                    )

            if server_content.generation_complete:
                print("Generación finalizada.")
                break


if __name__ == "__main__":
    asyncio.run(
        test_live_connection()
    )