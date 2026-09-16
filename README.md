# Self Order Voice

Prueba de un autoservicio conversacional: Gemini interpreta pedidos ya sean mediante voz o texto y
un backend Python valida productos, modificadores y precios. El dashboard muestra
la conversación y el carrito actualizado por WebSocket.

Tocá **Hablar**, luego de que el indicador de **Estado** esté en "Listo" esperá la
escucha y tocá **Enviar audio** al terminar; el texto definitivo usa el mismo
orquestador del chat. La respuesta puede leerse con la voz del navegador si el mismo está habilitado.
La confirmación y el pago son demostraciones locales, sin integración POS ni
procesamiento real de tarjetas. El QR es escaneable, pero contiene solo texto de demostracion sin URL ni pago real.

Ver [la guía de voz](docs/voz.md) para funcionamiento, límites y pruebas. Todavía
no se detectan silencios ni se agregan productos durante una frase en curso.

## Documentación

Empezar por [la guía del proyecto](docs/README.md). Incluye alcance,
[arquitectura](docs/arquitectura.md), [decisiones y alternativas](docs/decisiones.md)
y [pendientes](docs/pendientes.md).
Las reglas de docstrings Google y actualización documental están en
[AGENTS.md](AGENTS.md).

## Ejecutar en Windows / PowerShell

Desde la raíz del repositorio, con Python instalado (entorno revisado: 3.12.1) crea un entorno virtual de Python dentro de la carpeta .venv. Si ya existe `.venv`, reutilizarlo.

```powershell
python -m venv .venv
```
En la carpeta .venv instalá ahi las dependencias del proyecto sin mezclarlas con el Python global de tu computadora.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

 Crear `.env` a partir de `.env.example`
solo si todavía no existe y configurar una API key de Gemini:

```dotenv
STT_PROVIDER=gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=tu_api_key
GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe-live
GEMINI_CHAT_MODEL=gemini-3.7-flash
```

Las credenciales locales no deben versionarse. El SDK carga la clave desde el
entorno o `.env`; no se envía al frontend.

Iniciar el servidor:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.api.app:app --reload
```

Activar el entorno en cada terminal PowerShell nueva desde la raíz del proyecto.
Debería aparecer `(.venv)` en el prompt. Para salir del entorno, usar `deactivate`.
Si PowerShell bloquea el script, permitirlo solo para la terminal actual y
volver a activar el entorno:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Abrir `http://127.0.0.1:8000/`. FastAPI sirve también el frontend, sin un servidor
adicional. `http://127.0.0.1:8000/docs` muestra los endpoints HTTP.
`/api/health` verifica la API, no el acceso a Gemini.

La configuración recomendada para la cuenta revisada el 15/09/2026 usa
`gemini-3.7-flash` para chat y `gemini-3.5-transcribe-live` para transcripción.
Los nombres se configuran mediante `GEMINI_CHAT_MODEL` y
`GEMINI_TRANSCRIPTION_MODEL` en `.env` cuando ambos proveedores son Gemini.

## Proveedores de IA y adaptadores

`STT_PROVIDER` decide el proveedor que transforma audio en texto y
`LLM_PROVIDER` el que interpreta el pedido. La configuración predeterminada es
`gemini` para ambos y conserva el recorrido actual. Gemini usa una sola
`GEMINI_API_KEY` para las dos capas; sus modelos se configuran con
`GEMINI_TRANSCRIPTION_MODEL` y `GEMINI_CHAT_MODEL`.

Gemini esta implementado para STT y LLM. OpenAI y Groq estan implementados solo
para LLM; su STT sigue pendiente. Para probar cualquiera de los dos, conserva
`STT_PROVIDER=gemini` y configura solo la credencial y modelo del LLM elegido:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=tu_clave_local
OPENAI_CHAT_MODEL=gpt-4.1-mini
```

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=tu_clave_local
GROQ_CHAT_MODEL=openai/gpt-oss-20b
```

Groq ejecuta ese modelo en la nube: no se instala un modelo en la computadora.
Su plan gratuito aplica límites de solicitudes y tokens; por eso es apto para
desarrollo y demostraciones acotadas, no una garantía de capacidad productiva.
La integración usa su API compatible con Chat Completions y mantiene el mismo
camino tools → `OrderService` que Gemini y OpenAI.
El adaptador limita cada respuesta a 800 tokens, para respetar el límite gratuito
de salida conocido de esos modelos y mantener respuestas breves para el kiosco.

`whisper`, `vosk`, `anthropic`, `google-cloud`, `azure` u otro valor no
implementado se informa claramente y no intenta usar una clave ajena.
`.env.example` registra `OPENAI_API_KEY` y `OPENAI_CHAT_MODEL` para el
interprete OpenAI. `OPENAI_TRANSCRIPTION_MODEL` sigue siendo una referencia
hasta crear el adaptador de voz OpenAI.

Para consultar modelos visibles para la cuenta OpenAI, sin imprimir la clave:

```powershell
.\.venv\Scripts\Activate.ps1
python -m backend.ai.list_openai_models
```

El listado indica disponibilidad de cuenta, no garantiza compatibilidad con tools ni saldo.
El diseño está separado en `SpeechToText` para audio por streaming y
`OrderInterpreter` para texto y tools. Gemini los implementa con
`GeminiLiveTranscriber` y `GeminiOrderInterpreter`. Ningún adaptador puede
validar precios, disponibilidad, modificadores, carrito o pagos: las tools
siguen delegando esas decisiones en `OrderService`. Ver
[arquitectura](docs/arquitectura.md) y [decisión 09](docs/decisiones.md).

Si se configura un nombre inexistente o incompatible, el chat o la voz muestran
el nombre concreto del modelo y la etapa que falló, sin modificar el carrito.

Un modelo de chat necesita la acción `generateContent`. Para voz,
`bidiGenerateContent` es necesario, pero no suficiente: el modelo también debe
estar documentado para **Live Transcription**, aceptar
`response_modalities=["TEXT"]` e `input_audio_transcription`, y emitir
`server_content.input_transcription` final después de `activity_end`. El listado
de modelos solo confirma la primera condición; las demás se validan con la
documentación oficial y una prueba de audio real. La disponibilidad futura depende
del proveedor y de la cuenta.

Para consultar todos los modelos visibles para la API key configurada, tanto los
de chat como los de transcripción, ejecutar:

```powershell
python -m backend.ai.list_models
```

El comando requiere red y credenciales, y solo muestra nombres y acciones del
proveedor. Las acciones permiten elegir: `generateContent` corresponde al chat y
`bidiGenerateContent` a transcripción/conversación en vivo. La lista puede
cambiar según la cuenta y la fecha; no es fija dentro del proyecto.

## Diagnóstico manual disponible

Requieren credenciales, red y acceso al modelo; pueden consumir cuota de Gemini.
Ejecutar desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m backend.ai.test_chat
```

El script permite conversar por terminal usando el mismo orquestador y las
validaciones del dashboard. Requiere credenciales, red y acceso al modelo, por
lo que puede consumir cuota de Gemini. Las pruebas de voz se mantienen como
regresiones en `tests/`; no se conservan experimentos aislados con modelos Live
anteriores ni archivos de audio de muestra.

## Diagnóstico

`logs/runtime.log` contiene eventos legibles; `logs/events.jsonl`, el detalle
estructurado. No confundir estos registros locales con persistencia de pedidos.
Consultar [pendientes](docs/pendientes.md) para los límites conocidos
y distinguir evidencia histórica, pruebas simuladas y verificaciones pendientes.
