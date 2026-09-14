# Estado, evidencia y pendientes

Revisión inicial: 14/09/2026. Base Git revisada: `94aa4fc` (`bot hasta ahora`).
La primera entrega agregó documentación; las siguientes actualizaciones se
registran aquí con su evidencia. Los hallazgos iniciales se conservan como historial.

## Voz por turnos implementada — 14/09/2026

Se conectó micrófono → transcripción Live → orquestador existente → carrito y
respuesta, con lectura opcional del navegador. Se corrigió desconexión WebSocket,
validación de estructura JSON, exclusión de turnos HTTP/voz/texto, sincronización
al conectar y serialización de envíos. Ver [voz.md](voz.md) para límites y comandos.

Evidencia nueva:

- Conexión real a `gemini-3.5-transcribe-live` y transcripción del archivo existente
  `sample.pcm`, sin copiar su contenido a documentación ni logs.
- Prueba real por WebSocket con ese audio: transcripciones provisionales/final,
  procesamiento por el orquestador real y respuesta `assistant.text`. El carrito
  de esa prueba quedó vacío; no demuestra un alta completa de voz con micrófono físico.
- Suite local: 16 pruebas aprobadas de productos/opciones, cancelación, formato y límites PCM,
  exclusión de turnos, cierre del proveedor y recuperación de conexión. Proveedor
  simulado y logging deshabilitado para no mezclar evidencia.
- Edge headless: una prueba aprobada de micrófono sintético → AudioWorklet → WebSocket → transcripción
  simulada → alta mediante servicio real → total ARS 12.500 → confirmación escrita.
  Se comprobó solicitud de síntesis y apagado, sin reproducir audio real.
- Pendiente de evaluación humana: micrófono/parlantes físicos, comprensión con
  ruido, timbre, latencias, silencios automáticos e interrupciones.

Dependencias de pruebas en `requirements-dev.txt`; no se cambiaron dependencias
de ejecución del bot. `tests/` ahora contiene regresiones reproducibles.

## Actualización de seguimiento — 14/09/2026

Se incorporó la regla de un commit local por cambio coherente, con mensaje breve
en español, explicación por etapa y comandos reproducibles para la autora.
La guía `seguimiento.md` permite levantar el frontend, probar el flujo escrito
y consultar commits/logs desde VS Code. Validación: revisión del diff y de enlaces
locales de documentación; este cambio no modifica el comportamiento del bot.

## Limpieza de caché Python — 14/09/2026

Se agregaron `__pycache__/` y `*.py[cod]` a `.gitignore` y se retiraron del índice
los cinco `.pyc` del dominio previamente versionados, conservando los archivos
locales. Son artefactos regenerables, no código fuente. Validación: ausencia de
bytecode en `git ls-files`, reglas verificadas con `git check-ignore` y presencia
de los archivos locales después de retirarlos del índice. No cambia el bot.

## Capacidades actuales

La corrida de la autora del 14/09/2026 mostró demoras variables en Gemini: una
interpretación tardó aproximadamente 76 segundos y una respuesta posterior a una
tool aproximadamente 41 segundos; otras llamadas tardaron entre 1 y 33 segundos.
El log anterior no medía por separado captura, transcripción y orquestación, por
lo que se agregaron eventos `voice.live_ready`, `voice.audio_finished`,
`voice.transcription_finished` y `conversation.completed`. Esto permite separar
demora de red/proveedor, finalización del audio y segunda llamada del chat.

La guía de ejecución y las reglas de seguimiento ahora incluyen activar el
entorno con `.\.venv\Scripts\Activate.ps1` en cada terminal PowerShell nueva.
La primera prueba fue bloqueada por la política de scripts de PowerShell.
Tras usar `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`,
se verificó la activación y que `python` resuelve al ejecutable de `.venv`.
La guía incluye esa alternativa, limitada a la terminal actual.
Es una actualización documental, sin cambios de comportamiento del bot.

| Capacidad | Estado y evidencia |
| --- | --- |
| Crear sesión y servir dashboard | Implementado; HTTP y entrega de recursos comprobados localmente con `TestClient`. |
| Pedido por texto con Gemini | Implementado; se reutilizó el orquestador real en el ensayo nuevo de audio a conversación. |
| Agregar, quitar, reemplazar y confirmar | Implementado; evidencia histórica y verificaciones locales de servicio/eventos. |
| Validar productos y opciones obligatorias | Comprobado localmente: rechazo de producto desconocido, opciones inválidas y configuración incompleta sin modificar carrito. |
| Preguntar antes de agregar | Tool `needs_clarification` comprobada; tres eventos históricos de aclaración. Que el LLM no invente valores válidos requiere evaluación conversacional. |
| Cambiar cantidad / vaciar carrito | Existe en servicio; no expuesto como tools. |
| Carrito actualizado durante el procesamiento | Eventos WebSocket implementados y comprobados localmente. No equivale a interpretar audio parcial. |
| Captura de micrófono y envío PCM | AudioWorklet verificado en Edge con micrófono sintético; falta evaluación del hardware físico. |
| Experimentos Gemini Live | Hay scripts de conexión textual y envío de archivo PCM. No se ejecutaron ahora ni se verificó el contenido del audio. |
| Pedir por voz desde el dashboard | Implementado por turnos explícitos, con vista provisional y mismo orquestador del chat. |
| Escuchar al asistente | Implementado con speechSynthesis; solicitud y apagado probados, calidad audible pendiente de la autora. |
| Persistencia, POS, pagos | No implementados. |

## Evidencia histórica disponible

`logs/events.jsonl` contenía 631 eventos del 10/09/2026 al iniciar la revisión:
28 mensajes de usuario, 24 respuestas finales, 16 actualizaciones del carrito
(12 altas, tres eliminaciones y un reemplazo), tres confirmaciones y tres
solicitudes de aclaración. Hubo cuatro errores `MODEL_OVERLOADED`: tres durante
interpretación y uno después de una tool con `transaction_applied=true`.

Esto respalda uso previo, no una tasa de éxito ni una evaluación completa: no
hay un conjunto de casos esperado contra el cual comparar todos los mensajes.
No se copiaron conversaciones ni identificadores de sesiones a estos documentos.

`tests/` y `docs/` estaban vacíos. Los `test_*.py` de `backend/ai` son scripts
manuales/experimentos, no una suite de regresión con aserciones de negocio.

## Verificaciones ejecutadas durante la revisión

Entorno existente: Python 3.12.1, google-genai 2.22.0, python-dotenv 1.2.3,
FastAPI 0.141.1, Uvicorn 0.52.4 y httpx 0.28.1. Las cuatro dependencias declaradas
coincidían con las instaladas. Se analizaron sintácticamente todos los `.py` de
`backend/` y `config/` sin errores.

Se ejecutó un script temporal por entrada estándar con `python -B`, sin crear
bytecode ni agregar pruebas al repositorio. Se deshabilitó el logger durante las
operaciones para no mezclar evidencia nueva simulada con los logs anteriores.

Resultados:

- Producto inexistente, modificadores faltantes u opción inválida: `ValueError`
  y carrito vacío.
- Tool de alta incompleta: `needs_clarification`, sin alta.
- Dos Big Mac grandes: total ARS 25.000.
- Reemplazo inválido: conserva todos los campos originales.
- Reemplazo válido por Cuarto de Libra mediano: conserva ID/cantidad y total
  ARS 23.000; cambiar tamaño produce ARS 27.000 y cambiar cantidad a uno, ARS 13.500.
- Confirmar bloquea la eliminación posterior.
- `TestClient`: `/api/health`, `/`, JS estático, creación de sesión, mensaje HTTP,
  validación de texto vacío y rechazo HTTP 409 tras confirmación.
- WebSocket: `connection.ready`, texto y `assistant.text`, bytes y
  `audio.received`, alta y `cart.updated`, confirmación y `order.confirmed`.
  El cliente Gemini fue reemplazado por una respuesta fija: esto comprueba el
  cableado local, no comprensión lingüística ni disponibilidad del modelo.
- La salida de la conexión reprodujo el defecto de desconexión descrito abajo.

No se ejecutó una prueba visual en navegador, ni una llamada nueva al proveedor,
ni el audio de los experimentos. Los nombres de modelos se documentan como
configuración encontrada, no como disponibilidad verificada en la cuenta.

## Hallazgos para resolver

Esta lista conserva el diagnóstico inicial. La etapa de voz resolvió los puntos
1 (desconexión), 2 (integración básica), 3 (reserva por sesión/snapshot/envíos),
5 (estructura JSON) y 7 (captura/cierre) de la sección siguiente. Siguen pendientes
reconexión automática, conversación continua y las validaciones del punto 4.

### Antes o durante la integración de voz

1. **Desconexión WebSocket defectuosa (reproducida).** `websocket.receive()`
   devuelve un mensaje de desconexión que el bucle ignora. El siguiente `receive`
   lanza `RuntimeError: Cannot call "receive" once a disconnect message has been
   received.` Solo se captura `WebSocketDisconnect`; puede quedar una conexión
   registrada. Resolver detección y limpieza con `finally` y probar reconexión.
2. **Audio sin procesamiento de pedido (confirmado por código).** Faltan sesión
   Live por usuario, envío al proveedor, recepción concurrente, límites de turno,
   transcripciones, tools y reproducción en navegador.
3. **Recuperación y concurrencia (riesgo por código).** No hay lock/cola por sesión;
   HTTP y múltiples conexiones pueden acceder al mismo chat/carrito. Solo se
   guarda un WebSocket por ID y no hay recuperación de snapshot al reconectar.
4. **Validación de tipos incompleta (reproducida en servicio).** Se acepta cantidad
   `1.5` y se conservan claves de modificadores desconocidas. Las anotaciones
   Python no validan en runtime. Definir validación estricta en la frontera y
   mantener invariantes en el servicio.
5. **JSON WebSocket sin validar estructura (por código).** Se captura JSON
   malformado, pero un JSON válido que sea lista/null o tenga `data` no objeto
   puede fallar al invocar `.get()`.
6. **Pedidos con varias acciones (por código).** Más de una function call en una
   respuesta produce error interno; el límite de cinco ciclos también afecta
   pedidos largos. Incorporar casos de varios productos antes de darlo por cubierto.
7. **Micrófono y cierre (por código).** Confirmar/desconectar no llama a
   `disableMicrophone()`. Revisar liberación, permisos, errores y estados. La
   captura actual usa `createScriptProcessor` y un remuestreo por selección de
   muestras; evaluar calidad y mecanismo de captura al implementar voz.

### Antes de ampliar menú o presentar garantías más amplias

- Las tools y el renderizado asumen `size` y `drink`. La tool de alta pide esos
  campos incluso antes de comprobar si el producto existe: puede pedir detalles
  de un producto desconocido si el LLM intenta un alta incompleta.
- El prompt no informa precios ni `available`, y no hay tool de consulta de menú.
  Hace falta cubrir «¿cuánto cuesta?» y productos indisponibles sin agregarlos.
- `change_quantity` y `clear_cart` necesitan exposición conversacional si se
  incorporan a las capacidades prometidas.
- `line_id` puede reutilizarse tras una eliminación (reproducido).
- Deduplicar una tool dentro del turno no evita duplicados al repetir mensajes.
- Faltan docstrings en `Cart.total`, `Menu.get_product` y `load_menu`; el frontend
  también necesita documentación de funciones cuando se modifique.
- La deuda de bytecode versionado se resolvió en la limpieza del 14/09/2026:
  `.gitignore` excluye cachés y el índice ya no contiene los cinco `.pyc` originales.

### Para una integración operativa

Definir persistencia/expiración, aislamiento de sesiones, contrato POS, manejo de
confirmaciones externas, recuperación después de errores y métricas de latencia.
Los logs guardan texto completo: acordar qué se conserva y durante cuánto tiempo
antes de usar conversaciones reales fuera de las pruebas locales.

## Etapas propuestas y criterios de aceptación

| Etapa | Entregable verificable |
| --- | --- |
| 1. Base reproducible | Suite local para reglas críticas, desconexión corregida y matriz de conversaciones escritas con resultados esperados. |
| 2. Diseño de voz | Decisión documentada entre transcripción/orquestación/síntesis y Live con tools; contrato de eventos, turnos y estado compartido. |
| 3. Voz de extremo a extremo | Desde micrófono real, completar un pedido, preguntar modificadores, rechazar fuera de menú y actualizar carrito; texto sigue funcionando en la misma sesión. |
| 4. Interacción continua | Transcripción provisional, silencios, interrupciones/correcciones, desconexión y cierre sin repetir altas; latencias medidas. |
| 5. Menú y presentación visual | Grupos de modificadores generales y renderizado basado en catálogo, luego mejora estética. |
| 6. Defensa | Demo repetible, diagramas actualizados y explicación de decisiones, evidencia y límites. |

La prioridad funcional es voz. Las correcciones de transporte y pruebas de la
base acompañan esa etapa para que sus fallas no se confundan con errores de audio.

La selección de modelos queda en `.env` mediante `GEMINI_TRANSCRIPTION_MODEL` y
`GEMINI_CHAT_MODEL`; `.env.example` contiene los valores recomendados. El comando
`python -m backend.ai.list_models` consulta la cuenta configurada y muestra los
modelos disponibles sin exponer la API key. Aún falta comparar de forma medida
latencia, costo y calidad entre alternativas.

## Matriz mínima de demostración pendiente

Para texto y luego para voz: producto completo; producto sin tamaño/bebida;
producto fuera de menú; producto indisponible; cambio de bebida; reemplazo
válido e inválido; dos configuraciones del mismo producto; referencia ambigua;
varios productos en una frase; eliminar; confirmar vacío; confirmar con productos;
intentar modificar confirmado; proveedor caído antes/después de mutar.

Para voz además: activar/desactivar, silencio, ruido, autocorrección («Coca, no,
Sprite»), interrupción del asistente, pasar a escritura, pérdida de conexión y
apagado del micrófono al finalizar. Registrar entrada, carrito esperado,
resultado observado, fecha/modelo y latencias; no evaluar solo si el bot habló.
