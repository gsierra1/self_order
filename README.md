# Self Order Voice

Prueba de un autoservicio conversacional: el STT configurado transcribe la voz; el LLM configurado interpreta el texto y la persona también puede escribir. Un backend Python valida productos, modificadores, disponibilidad, precios y estado del pedido. La interfaz muestra la conversación y el carrito actualizado por WebSocket.

Una vez que el indicador está en **Listo**, se puede tocar **Hablar** y esperar el estado **Escuchando**. Después de detectar voz, 1,4 segundos de silencio cierran el turno automáticamente. **Enviar audio** queda disponible como cierre manual. Solo la transcripción final llega al mismo intérprete LLM utilizado por el chat escrito.

La respuesta puede leerse mediante la síntesis de voz del navegador cuando está habilitada. La confirmación y el pago son demostraciones locales: no existe integración con POS ni procesamiento real de tarjetas. El QR es escaneable, pero contiene únicamente texto de demostración. QR y caja esperan 20 segundos antes de mostrar la confirmación y el número de pedido; la pantalla final permanece 10 segundos antes de iniciar otra sesión.

## Documentación

Empezar por [la guía del proyecto](docs/README.md). La documentación separa [producto y alcance](docs/producto.md), [arquitectura y contratos](docs/arquitectura.md), [voz por turnos](docs/voz.md) y [pendientes](docs/pendientes.md).

Las reglas para trabajar sobre el repositorio están en [AGENTS.md](AGENTS.md). Las decisiones arquitectónicas vigentes y sus justificaciones se documentan dentro de `docs/arquitectura.md`.

## Ejecutar en Windows / PowerShell

Desde la raíz del repositorio, crear un entorno virtual si todavía no existe:

```powershell
python -m venv .venv
```

Instalar las dependencias:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Crear `.env` a partir de `.env.example` solo si todavía no existe. Las credenciales locales no deben versionarse.

Iniciar el servidor:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.api.app:app --reload
```

Abrir `http://127.0.0.1:8000/`. FastAPI sirve también el frontend. `http://127.0.0.1:8000/docs` muestra los endpoints HTTP. `/api/health` verifica la API, pero no garantiza acceso a proveedores externos.

## Configuración de la demo

STT y LLM se seleccionan de forma independiente mediante `STT_PROVIDER` y `LLM_PROVIDER`.

La configuración utilizada actualmente para la demostración es Web Speech API para transcripción y Groq para interpretación:

```dotenv
STT_PROVIDER=web_speech_browser
SPEECH_API_LANGUAGE=es-AR
LLM_PROVIDER=groq
GROQ_API_KEY=tu_clave_de_groq
GROQ_CHAT_MODEL=openai/gpt-oss-20b
```

Web Speech API no necesita una API key propia. El navegador controla el motor de reconocimiento y puede utilizar un servicio remoto. Groq requiere una clave local de API, que permanece en backend.

## Proveedores implementados

Para STT están implementados `web_speech_browser`, `whisper_browser`, `vosk` y `gemini`. Para interpretación LLM están implementados `groq`, `gemini` y `openai`.

El backend publica `voice.transport`: `backend_pcm` para Gemini y Vosk, y `browser_text` para Whisper y Web Speech API. Así el frontend selecciona la captura adecuada a partir de la configuración recibida.

Los intérpretes reciben las reglas y el catálogo desde `OrderToolsRuntime.build_system_instruction()`. Las tools se definen en `order_tool_specs.py`. El LLM interpreta la intención, pero `OrderService` conserva la autoridad sobre productos, disponibilidad, modificadores, cantidades, precios, carrito y estados de pago.

La explicación completa está en [arquitectura y contratos](docs/arquitectura.md).

## Groq como intérprete LLM

Configuración:

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=tu_clave_de_groq
GROQ_CHAT_MODEL=openai/gpt-oss-20b
```

El prefijo `openai/` forma parte del nombre del modelo; las solicitudes siguen siendo procesadas por Groq. También se probó `qwen/qwen3.8-27b` como alternativa. El modelo elegido debe admitir tools.

Para listar los modelos visibles:

```powershell
python -m backend.ai.list_groq_models
```

## Web Speech API

Configuración:

```dotenv
STT_PROVIDER=web_speech_browser
SPEECH_API_LANGUAGE=es-AR
```

Publica resultados provisionales para feedback visual y envía al backend únicamente el texto final. `SPEECH_API_LANGUAGE` acepta una etiqueta BCP 47. No existe `SPEECH_API_MODEL` porque el navegador no permite seleccionar el modelo acústico.

## Vosk como STT local

Vosk procesa audio localmente y no requiere una API key de STT. `requirements.txt` instala la biblioteca, pero el modelo debe descargarse por separado y mantenerse fuera de Git.

```powershell
.\.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force .models
Invoke-WebRequest -Uri "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip" -OutFile ".models\vosk-model-small-es-0.42.zip"
Expand-Archive -LiteralPath ".models\vosk-model-small-es-0.42.zip" -DestinationPath ".models" -Force
Test-Path ".models\vosk-model-small-es-0.42\am"
```

Configuración:

```dotenv
STT_PROVIDER=vosk
VOSK_MODEL_PATH=.models/vosk-model-small-es-0.42
LLM_PROVIDER=groq
GROQ_API_KEY=tu_clave_de_groq
GROQ_CHAT_MODEL=openai/gpt-oss-20b
```

## Whisper local en el navegador

Configuración:

```dotenv
STT_PROVIDER=whisper_browser
WHISPER_BROWSER_MODEL=onnx-community/whisper-tiny
WHISPER_BROWSER_DEVICE=auto
LLM_PROVIDER=groq
GROQ_API_KEY=tu_clave_de_groq
GROQ_CHAT_MODEL=openai/gpt-oss-20b
```

Whisper se ejecuta en un Worker del navegador y al backend llega únicamente el texto final. `auto` intenta WebGPU y utiliza WebAssembly sobre CPU cuando WebGPU no está disponible. Su comparación real con los demás STT figura en [pendientes](docs/pendientes.md).

## Gemini para STT o LLM

Gemini puede utilizarse en cualquiera de las dos capas y usa `GEMINI_API_KEY`.

```dotenv
STT_PROVIDER=gemini
GEMINI_API_KEY=tu_clave_de_gemini
GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe-live
```

Para listar modelos visibles:

```powershell
python -m backend.ai.list_gemini_models
```

## OpenAI como intérprete LLM

OpenAI está implementado únicamente como intérprete LLM:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=tu_clave_local
OPENAI_CHAT_MODEL=gpt-4.1-mini
```

La API de OpenAI tiene facturación separada de ChatGPT. Para listar modelos visibles:

```powershell
python -m backend.ai.list_openai_models
```

## Incorporar otros proveedores

Elegir un nombre nuevo en `.env` no implementa automáticamente un proveedor. Un nuevo LLM debe implementar `OrderInterpreter`; un nuevo STT de backend debe implementar `SpeechToText`. Las integraciones nuevas deben conservar `OrderService` como autoridad del pedido.

Las tareas futuras concretas se mantienen en [pendientes](docs/pendientes.md).

## Diagnóstico manual

El chat de terminal utiliza el mismo intérprete y las mismas reglas del dashboard:

```powershell
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m backend.ai.test_chat
```

Puede consumir cuota del proveedor configurado.

## Pruebas automatizadas

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Las pruebas automáticas verifican reglas del pedido, transporte, adaptadores y comportamientos simulados. No sustituyen pruebas manuales con proveedores reales, micrófono físico o condiciones ambientales.

El recorrido específico de voz está documentado en [voz por turnos](docs/voz.md).

## Diagnóstico y logs

`logs/runtime.log` contiene eventos legibles y `logs/events.jsonl` conserva el detalle estructurado. Los logs sirven para diagnóstico y medición; no son persistencia de pedidos.

## Límites actuales

Todavía quedan fuera del alcance actual:

- persistencia durable de sesiones y pedidos;
- idempotencia entre procesos;
- pago real;
- integración con POS, cocina, stock y ticketera;
- evaluación productiva de hardware, ruido, latencia y disponibilidad de proveedores.

Los pendientes concretos se mantienen en [docs/pendientes.md](docs/pendientes.md). La arquitectura vigente y sus justificaciones técnicas se mantienen en [docs/arquitectura.md](docs/arquitectura.md).
