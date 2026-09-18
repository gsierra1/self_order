# Self Order Voice

Prueba de un autoservicio conversacional: Gemini transcribe la voz; el LLM
configurado interpreta el texto y el usuario también puede escribir. Un backend
Python valida productos, modificadores y precios. El dashboard muestra la
conversación y el carrito actualizado por WebSocket.

Una vez que el indicador esté en "Listo", tocá **Hablar** y esperá la
escucha. Procede a indicar tu pedido por voz: después de que empieces a hablar,
1,4 segundos de silencio envían el turno automáticamente. **Enviar audio** queda
disponible como cierre manual. El texto definitivo usa el mismo intérprete LLM
configurado que el chat.
La respuesta puede leerse con la voz del navegador si el mismo está habilitado.
La confirmación y el pago son demostraciones locales, sin integración POS ni
procesamiento real de tarjetas. El QR es escaneable, pero contiene solo texto de demostracion sin URL ni pago real.

Si la persona deja de interactuar después de iniciar el pedido, la interfaz
pregunta si sigue allí a los 20 segundos, avisa que cerrará la sesión 20 segundos
después y crea una sesión nueva tras otros 20 segundos. Una sesión recién creada
no inicia este conteo hasta que alguien envíe un mensaje escrito o finalice una
transcripción de voz. Mover el mouse, enfocar un campo o tocar un control sin
enviar un mensaje no inicia la espera. El temporizador se detiene mientras se procesa una respuesta de voz o
texto y no consulta al proveedor de IA.

## Documentación

Empezar por [la guía del proyecto](docs/README.md). Incluye alcance,
[arquitectura](docs/arquitectura.md), [decisiones y alternativas](docs/decisiones.md)
y [pendientes](docs/pendientes.md).
Las reglas de docstrings Google y actualización documental están en
[AGENTS.md](AGENTS.md).

## Ejecutar en Windows / PowerShell

Desde la raíz del repositorio, con Python instalado crea un entorno virtual de Python dentro de la carpeta .venv. 
Si ya existe `.venv`, reutilizarlo.

```powershell
python -m venv .venv
```
En la carpeta .venv instalá ahi las dependencias del proyecto sin mezclarlas con el Python global de tu computadora.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Crear `.env` a partir de `.env.example` solo si todavía no existe. La
configuración recomendada para esta demo usa Gemini para transcribir la voz y
Groq para interpretar el pedido:

```dotenv
STT_PROVIDER=gemini
LLM_PROVIDER=groq
GEMINI_API_KEY=tu_clave_de_google_ai_studio
GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe-live
GROQ_API_KEY=tu_clave_de_groq
GROQ_CHAT_MODEL=openai/gpt-oss-20b
# Alternativa probada: qwen/qwen3.8-27b (menos consistente en algunas tools).
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
`/api/health` verifica la API, no el acceso a los proveedores de IA.


## Proveedores de IA y adaptadores

`STT_PROVIDER` decide el proveedor que transforma audio en texto y
`LLM_PROVIDER` el que interpreta el pedido. Si se omiten, el código usa Gemini
para ambas capas. La configuración recomendada del `.env.example` usa Groq para
el chat debido al saldo agotado de OpenAI y a la saturación observada en Gemini
Chat. Gemini usa una sola
`GEMINI_API_KEY` para las dos capas; sus modelos se configuran con
`GEMINI_TRANSCRIPTION_MODEL` y `GEMINI_CHAT_MODEL`.

Gemini está implementado para STT y LLM. Groq y OpenAI están implementados solo
para LLM; su STT sigue pendiente. Groq ofrece Whisper mediante un endpoint de
archivo, pero no el streaming de fragmentos que necesita esta interfaz; por eso
no se puede cambiar solo una variable sin crear otro adaptador. El `.env.example` selecciona Groq porque la
cuenta gratuita de Groq permitió probar las tools del carrito. No se instala un
modelo en la PC: Groq ejecuta `openai/gpt-oss-20b` en la nube mediante una API
compatible con OpenAI. El nombre `openai/` identifica al modelo, no al servicio
que procesa la solicitud: el proveedor configurado sigue siendo Groq.

Para generar una clave de Gemini para la transcripción recomendada:

1. Entrá a [Google AI Studio](https://aistudio.google.com/).
2. Iniciá sesión con tu cuenta de Google y abrí [la sección de claves API](https://aistudio.google.com/app/apikey).
3. Elegí **Create API key**, seleccioná un proyecto si la plataforma lo solicita,
   copiala y guardala en tu `.env` como `GEMINI_API_KEY`.
4. Conservá `STT_PROVIDER=gemini` y `GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe-live`.

Google puede pedir aceptar sus condiciones o asociar la clave a un proyecto. La
clave habilita las llamadas que permita tu cuenta; los límites y la disponibilidad
del modelo dependen del proyecto y del nivel de uso. No la pegues en el código,
README, logs ni Git.

Para generar o volver a generar una clave de Groq:

1. Entrá a [Groq Console](https://console.groq.com/).
2. Iniciá sesión y abrí [API Keys](https://console.groq.com/keys).
3. Creá una clave, copiala y guardala en tu `.env` como `GROQ_API_KEY`.
4. Configurá `LLM_PROVIDER=groq` y `GROQ_CHAT_MODEL=openai/gpt-oss-20b`.

También se probó `qwen/qwen3.8-27b` como alternativa. Para esta demo se
recomienda mantener `openai/gpt-oss-20b`, porque fue más consistente al ejecutar
las tools del carrito.

La clave se muestra como secreto: no la pegues en el código, README, logs ni Git.
El plan gratuito tiene límites de solicitudes y tokens que pueden cambiar; sirve
para desarrollo y una demo acotada, pero no garantiza disponibilidad productiva.
Groq publica los modelos y límites actuales en [su catálogo](https://console.groq.com/docs/models)
y [la tabla de límites](https://console.groq.com/docs/rate-limits).
Cuando Groq responde `429`, el backend muestra el tiempo de espera que la API
devuelve en sus cabeceras, si está disponible. Si no llega ese dato, consultá la
sección **Limits** de la [consola de Groq](https://console.groq.com/).

Gemini puede usarse también como LLM. En ese caso, conserva
`STT_PROVIDER=gemini`, configura `LLM_PROVIDER=gemini` y agrega
`GEMINI_CHAT_MODEL` con un modelo que admita `generateContent` y function calling.
Una sola `GEMINI_API_KEY` autentica ambas capas.

OpenAI también cuenta con un adaptador implementado para LLM. Su API se factura
por separado de ChatGPT y necesita una cuenta API con saldo o facturación
habilitada; una suscripción de ChatGPT no cubre llamadas a la API, según la
[documentación de facturación de OpenAI](https://help.openai.com/en/articles/9039756-managing-your-work-in-the-api-platform-with-projects).
Por eso la configuración recomendada utiliza Groq. Para probarlo,
conserva `STT_PROVIDER=gemini` y configura:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=tu_clave_local
OPENAI_CHAT_MODEL=gpt-4.1-mini
```

`OPENAI_CHAT_MODEL` debe admitir function calling. El comando para listar modelos
de la cuenta ayuda a revisar acceso, pero la compatibilidad con tools y el saldo
se confirman mediante una solicitud real.

`whisper`, `vosk`, `anthropic`, `google-cloud`, `azure` u otro valor no
implementado se informa claramente y no intenta usar una clave ajena.

Los proveedores se seleccionan mediante `STT_PROVIDER` y `LLM_PROVIDER`. Hoy
STT admite `gemini`; LLM admite `gemini`, `groq` y `openai`. Cada proveedor
requiere sus propias variables: Gemini usa `GEMINI_API_KEY`, Groq usa
`GROQ_API_KEY` y OpenAI usa `OPENAI_API_KEY`. Solo se exige la credencial del
proveedor elegido para esa capa. No compartas ni subas `.env` al repositorio.

Para consultar los modelos visibles para la cuenta OpenAI, sin imprimir la
clave (sólo aplica a `LLM_PROVIDER=openai`):

```powershell
.\.venv\Scripts\Activate.ps1
python -m backend.ai.list_openai_models
```

El listado indica disponibilidad de cuenta, pero no garantiza compatibilidad con
tools ni saldo de API.

Para consultar los modelos visibles para la cuenta Groq, sin imprimir la clave
(sólo aplica a `LLM_PROVIDER=groq`):

```powershell
.\.venv\Scripts\Activate.ps1
python -m backend.ai.list_groq_models
```

El comando consulta el catálogo expuesto para esa cuenta. Que un modelo aparezca
en la lista no garantiza que admita tools; la compatibilidad se valida con una
prueba controlada del adaptador.

El diseño está separado en `SpeechToText` para audio por streaming y
`OrderInterpreter` para texto y tools. Gemini los implementa con
`GeminiLiveTranscriber` y `GeminiOrderInterpreter`. Ningún adaptador puede
validar precios, disponibilidad, modificadores, carrito o pagos: las tools
siguen delegando esas decisiones en `OrderService`. Ver
[arquitectura](docs/arquitectura.md) y [decisión 09](docs/decisiones.md).

Si se configura un nombre inexistente o incompatible, el chat o la voz muestran
el nombre concreto del modelo y la etapa que falló, sin modificar el carrito.

Un modelo de chat Gemini necesita la acción `generateContent`. Para voz,
`bidiGenerateContent` es necesario, pero no suficiente: el modelo también debe
estar documentado para **Live Transcription**, aceptar
`response_modalities=["TEXT"]` e `input_audio_transcription`, y emitir
`server_content.input_transcription` final después de `activity_end`. El listado
de modelos solo confirma la primera condición; las demás se validan con la
documentación oficial y una prueba de audio real. La disponibilidad futura depende
del proveedor y de la cuenta.

Para consultar los modelos Gemini visibles para la API key, tanto de chat como
de Live, ejecutar desde la raíz:

```powershell
.\.venv\Scripts\Activate.ps1
python -m backend.ai.list_gemini_models
```

El comando requiere red y `GEMINI_API_KEY`; consulta únicamente los modelos de
Gemini y muestra sus nombres y acciones. `generateContent` corresponde al chat;
`bidiGenerateContent` es un requisito parcial para voz, que además necesita
compatibilidad real con Live Transcription. La lista cambia según cuenta y fecha.

## Incorporar otros proveedores

La arquitectura permite agregar proveedores en los bordes de IA sin cambiar
`OrderService`, que sigue siendo la autoridad para menú, disponibilidad,
modificadores, precios, carrito y pagos. Sin embargo, elegir un nombre nuevo en
`.env` no lo implementa automáticamente. Para sumar un LLM como Anthropic se
debe crear un cliente que lea `ANTHROPIC_API_KEY`, agregar la variable de modelo,
implementar `OrderInterpreter` traduciendo su protocolo de tool use a las tools
autorizadas, registrar el adaptador en `backend/ai/factories.py`, clasificar sus
errores y agregar pruebas simuladas y manuales. Para sumar STT se requiere
`SpeechToText` completo: conexión/preparación, audio por fragmentos, parciales,
texto final, cancelación y cierre; luego se configura proveedor, credencial o
modelo y se añade a la fábrica de STT. Los pasos por etapa y otros candidatos
están en [pendientes](docs/pendientes.md); los contratos y responsabilidades se
explican en [arquitectura](docs/arquitectura.md).

## Diagnóstico manual disponible

Requiere credenciales, red y acceso al proveedor seleccionado; puede consumir
cuota del proveedor cloud configurado. Ejecutar desde la raíz:

```powershell
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m backend.ai.test_chat
```

El script permite conversar por terminal usando el mismo intérprete de pedidos y
las validaciones del dashboard. Requiere credenciales, red y acceso al modelo.
Las pruebas de voz se mantienen como
regresiones en `tests/`; no se conservan experimentos aislados con modelos Live
anteriores ni archivos de audio de muestra.

## Diagnóstico

`logs/runtime.log` contiene eventos legibles; `logs/events.jsonl`, el detalle
estructurado. No confundir estos registros locales con persistencia de pedidos.
Consultar [pendientes](docs/pendientes.md) para los límites conocidos
y distinguir evidencia histórica, pruebas simuladas y verificaciones pendientes.
