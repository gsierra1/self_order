# Self Order Voice

Prueba de concepto de autoservicio conversacional: Gemini interpreta pedidos y
un backend Python valida productos, modificadores y precios. El dashboard muestra
la conversación y el carrito actualizado por WebSocket.

**Estado:** flujo escrito implementado, captura/transporte de micrófono parcial
y experimentos aislados de Gemini Live. Todavía no se pueden completar pedidos
por voz desde el dashboard ni escuchar sus respuestas. La confirmación es local,
sin integración POS ni pagos.

## Documentación

Empezar por [la guía del proyecto](docs/README.md). Incluye alcance,
[arquitectura](docs/arquitectura.md), [decisiones y alternativas](docs/decisiones.md)
y [estado, pruebas y pendientes](docs/estado-y-pruebas.md).
Las reglas de docstrings Google y actualización documental están en
[AGENTS.md](AGENTS.md).

## Ejecutar en Windows / PowerShell

Desde la raíz del repositorio, con Python instalado (entorno revisado: 3.12.1):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si ya existe `.venv`, reutilizarlo. Crear `.env` a partir de `.env.example`
solo si todavía no existe y configurar una API key de Gemini:

```dotenv
GEMINI_API_KEY=tu_api_key
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
Si PowerShell bloquea el script, consultar la solución limitada a la terminal
actual en [la guía de seguimiento](docs/seguimiento.md).

Abrir `http://127.0.0.1:8000/`. FastAPI sirve también el frontend, sin un servidor
adicional. `http://127.0.0.1:8000/docs` muestra los endpoints HTTP.
`/api/health` verifica la API, no el acceso a Gemini.

Ejemplo escrito: «Quiero un Big Mac grande con Coca». El total esperado para
una unidad es $12.500. Una solicitud incompleta debe generar preguntas antes de
agregar. Para una nueva sesión, recargar la página; reiniciar el backend pierde
todas las sesiones. Usar un solo worker mientras el estado permanezca en memoria.

El modelo de chat configurado en código es `gemini-3.5-flash-lite`; los
experimentos Live usan `gemini-3.1-flash-live-preview`. Su disponibilidad depende
del proveedor y de la cuenta y no fue verificada de nuevo en la revisión inicial.

## Scripts manuales existentes

Requieren credenciales, red y acceso al modelo; pueden consumir cuota de Gemini.
Ejecutar desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m backend.ai.test_chat
.\.venv\Scripts\python.exe -m backend.ai.test_live
.\.venv\Scripts\python.exe -m backend.ai.test_live_audio
```

El primero permite conversar por terminal. Los otros prueban Live de forma
aislada y muestran transcripciones. El último espera `sample.pcm` en PCM mono
de 16 bits a 16 kHz; el formato esperado está en el script, no en una cabecera
del archivo. Ninguno de los scripts Live modifica el carrito.

## Diagnóstico

`logs/runtime.log` contiene eventos legibles; `logs/events.jsonl`, el detalle
estructurado. No confundir estos registros locales con persistencia de pedidos.
Consultar [estado y pruebas](docs/estado-y-pruebas.md) para los límites conocidos
y distinguir evidencia histórica, pruebas simuladas y verificaciones pendientes.
