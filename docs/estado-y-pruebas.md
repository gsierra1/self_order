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

- Conexión real a `gemini-3.5-transcribe-live` y transcripción de un audio de
  prueba, sin copiar su contenido a documentación ni logs. El archivo temporal
  usado para ese experimento no se conserva en el repositorio.
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
| Experimentos Gemini Live | La evidencia histórica se conserva documentada; los scripts aislados y el audio de muestra se retiraron porque usaban un modelo anterior y no representan el flujo integrado. |
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
conversacion continua y las validaciones del punto 4.

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
6. **Pedidos con varias acciones (verificado por código).** Varias function calls
   distintas en una respuesta se ejecutan en orden y sus resultados vuelven juntos
   a Gemini; una llamada idéntica repetida se rechaza. El límite de cinco ciclos
   todavía afecta pedidos largos.
7. **Micrófono y cierre (por código).** Confirmar/desconectar no llama a
   `disableMicrophone()`. Revisar liberación, permisos, errores y estados. La
   captura actual usa `createScriptProcessor` y un remuestreo por selección de
   muestras; evaluar calidad y mecanismo de captura al implementar voz.

### Antes de presentar garantías más amplias

- Los grupos de modificadores ahora se leen desde el catálogo y el frontend
  recibe sus nombres visibles. Falta una evaluación manual con Gemini para
  comprobar que la interpretación conversacional use correctamente varios
  extras opcionales en una misma frase.
- El prompt no informa precios ni `available`, y no hay tool de consulta de menú.
  Hace falta cubrir «¿cuánto cuesta?» y productos indisponibles sin agregarlos.
- `change_quantity` y `clear_cart` necesitan exposición conversacional si se
  incorporan a las capacidades prometidas.
- `line_id` puede reutilizarse tras una eliminación (reproducido).
- Deduplicar una tool dentro del turno no evita duplicados al repetir mensajes.
- La deuda previa de documentación de `Cart.total` se resolvió junto con la
  descripción Google de los modelos de dominio `Cart`, `CartItem`, `Menu`,
  `Product`, `ModifierGroup` y `ModifierOption`. El frontend documenta sus
  funciones modificadas con JSDoc.
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
| 5. Menú y presentación visual | Implementado: grupos generales, bebida obligatoria, extras opcionales y renderizado basado en catálogo. Falta prueba manual con Gemini. |
| 6. Defensa | Demo repetible, diagramas actualizados y explicación de decisiones, evidencia y límites. |

La prioridad funcional es voz. Las correcciones de transporte y pruebas de la
base acompañan esa etapa para que sus fallas no se confundan con errores de audio.

La selección de modelos queda en `.env` mediante `GEMINI_TRANSCRIPTION_MODEL` y
`GEMINI_CHAT_MODEL`; `.env.example` contiene los valores recomendados. El comando
`python -m backend.ai.list_models` consulta la cuenta configurada y muestra los
modelos disponibles sin exponer la API key. La salida incluye acciones para
distinguir modelos de chat (`generateContent`) y transcripción en vivo
(`bidiGenerateContent`). Aún falta comparar de forma medida latencia, costo y
calidad entre alternativas.

### Robustez de pago y configuración de modelos (15/09/2026)

La corrida anterior mostró que, al elegir QR, Gemini intentó una segunda vez
`confirm_order` con el pedido ya en `PAYMENT_PENDING`. Se reforzó la tool para
que esa llamada sea idempotente: devuelve el pago pendiente y el mismo número de
pedido, sin una segunda confirmación ni una mutación. Gemini puede continuar con
la selección de método o con la vuelta a edición.

También se consultaron los modelos visibles para la API key local mediante
`python -m backend.ai.list_models`. La cuenta mostró `gemini-3.6-flash` con
`generateContent` para chat y `gemini-3.5-transcribe-live` con
`bidiGenerateContent` para voz. No mostró `gemini-3.6-flash-lite` ni
`gemini-3.6-transcribe-live`; por eso esas configuraciones produjeron error. La
configuración local se corrigió sin versionar `.env`. Los errores 404 de voz
ahora indican modelo y etapa al usuario y conservan el detalle técnico en logs.
Falta una prueba manual nueva con Gemini para medir si el cambio de chat reduce
la latencia o la saturación: que un nombre exista no garantiza capacidad ni
mejor rendimiento.

La consulta posterior del mismo día también mostró como alternativas de chat
`gemini-3.7-flash`, `gemini-3.8-flash` y `gemini-3.5-flash`; para Live mostró
`gemini-3.8-live`, `gemini-3.1-flash-live-preview` y
`gemini-3.5-live-translate-preview`. La acción `generateContent` o
`bidiGenerateContent` confirma la capacidad que declara el proveedor, pero no
sustituye una evaluación real del flujo de pedido.

La corrida posterior comprobó que `gemini-3.6-flash` devolvió `503
MODEL_OVERLOADED` en dos solicitudes de chat. Una consulta real de precio con
`gemini-3.7-flash` respondió correctamente y mantuvo el carrito vacío. Para voz,
`gemini-3.5-live-translate-preview` abrió Live pero, después de audios de 14,4 y
17,8 segundos, no entregó transcripción final dentro de los 20 segundos de
espera. Se volvió a configurar `gemini-3.5-transcribe-live`, que sí tiene
transcripciones reales registradas. Por ahora es el único modelo recomendado
para STT; los demás modelos Live quedan como candidatos para evaluación, no como
alternativas intercambiables.

El criterio de selección de STT se precisó en `.env.example`: `bidiGenerateContent`
es necesario para la conexión Live, pero el candidato también debe estar
documentado para Live Transcription, aceptar la configuración de texto y
transcripción de entrada, y emitir una transcripción final después de terminar
el turno. El listado de modelos no informa por sí solo esas últimas condiciones.

### Disponibilidad del proveedor y preparación para producción (15/09/2026)

Los `503 MODEL_OVERLOADED` observados pertenecen a la capacidad temporal del
proveedor; no prueban que todos los modelos fallen ni que la frase de usuario sea
demasiado larga. `gemini-3.7-flash` respondió una consulta real posterior. Un
`429` sería distinto: señalaría que se excedió una cuota de solicitudes, tokens
o gasto. El plan pago aumenta las cuotas disponibles, pero no garantiza eliminar
un `503` de un servicio compartido.

Para un kiosco real queda pendiente medir pedidos por minuto, tokens, latencia,
porcentaje de errores y costo por local. Con esos datos se decide entre un plan
pago con cuotas adecuadas, capacidad reservada en Vertex AI para un modelo
compatible, o una combinación de proveedores. También se requiere una ruta de
continuidad por pantalla/escritura, reintentos idempotentes y adaptadores de STT
y LLM que permitan cambiar proveedor sin alterar `OrderService`. No se probó ni
se implementó todavía failover automático o capacidad reservada.

### Desglose y eliminación de extras en el carrito (15/09/2026)

El carrito separa ahora los modificadores obligatorios del precio base y los
opcionales bajo el título «Extras». Cada extra opcional tiene un tachito propio;
el control llama a un endpoint que delega la validación y el nuevo precio en
`OrderService`. El tachito junto al importe de la línea elimina el producto
completo. Las instrucciones escritas y de voz conservan las tools de cambio y
eliminación ya existentes. La prueba automática cubre que quitar queso conserva
la hamburguesa, la bebida y actualiza el total de ARS 9.500 a ARS 8.500.
La prueba de navegador con Edge y proveedores simulados verificó el orden visual
de configuración y extras, el tachito de queso, el nuevo total y el tachito de
la línea completa. No utiliza Gemini ni un micrófono real.

El flujo de pago demo quedó implementado: `PAYMENT_PENDING` genera un número de
pedido en backend, permite elegir QR, tarjeta o caja por texto, voz o botones y
finaliza en `CONFIRMED`. El QR es inválido a propósito, la tarjeta no se envía
ni se almacena, el botón atrás conserva la edición y cada línea activa tiene un
control de eliminación. La pantalla final cuenta cinco segundos e inicia otra
sesión. Falta realizar la prueba manual de los tres recorridos desde el navegador.
Las consultas de precios deben responderse desde el catálogo sin crear líneas
temporales. El botón del carrito inicia el pago directamente; el botón atrás
permite volver a editar, y los métodos QR, tarjeta y caja terminan con la misma
cuenta regresiva antes de abrir otra sesión.

## Matriz mínima de demostración pendiente

Para texto y luego para voz: producto completo; producto sin bebida;
producto fuera de menú; producto indisponible; cambio de bebida; reemplazo
válido e inválido; alta con varios extras y retiro de un extra; dos configuraciones del mismo producto; referencia ambigua;
varios productos en una frase; eliminar; confirmar vacío; confirmar con productos;
intentar modificar confirmado; proveedor caído antes/después de mutar.

Para voz además: activar/desactivar, silencio, ruido, autocorrección («Coca, no,
Sprite»), interrupción del asistente, pasar a escritura, pérdida de conexión y
apagado del micrófono al finalizar. Registrar entrada, carrito esperado,
resultado observado, fecha/modelo y latencias; no evaluar solo si el bot habló.

### Menú genérico de hamburguesas (15/09/2026)

Se reemplazó el menú de ejemplo por Burger Clásica y Burger Doble. La bebida es
obligatoria; tomate, lechuga, jamón y queso son extras independientes y opcionales
de ARS 1.000 cada uno. `OrderService`, las tools y el frontend leen los grupos
desde el catálogo, validan grupos desconocidos y muestran nombres visibles en el
carrito. La suite local comprobó bebida faltante, acumulación y retiro de extras,
rechazo de grupos desconocidos, reemplazo atómico, pagos y voz simulada. Falta la
prueba manual con Gemini y micrófono real de los recorridos nuevos.

La corrida manual del 15/09/2026 confirmó alta de Burger Clásica con agua y
tomate, retiro de tomate, altas consecutivas de queso y tomate, cambio de bebida
a Coca-Cola, consulta de precio, rechazo de empanada y pago QR. La primera frase
«hamburguesa simple» fue interpretada como ambigua; se incorporó el alias
explícito al catálogo. No hubo una mutación incorrecta. Se observaron demoras de
Gemini de hasta aproximadamente 53 segundos en una operación con dos extras y
de 22 segundos para rechazar un producto inexistente; son evidencia de latencia
del proveedor que se debe seguir midiendo. El carrito ahora muestra precio base,
bebida incluida y precio de cada extra.

### Actualización visual del frontend (14/09/2026)

La interfaz adoptó la identidad visual de SIA Interactive: tipografía Inter, violeta de marca y una composición con gradientes suaves, tarjetas redondeadas y jerarquía visual orientada a la acción. El encabezado ahora invita a iniciar el pedido con “Hace tu pedido” y conserva los mismos controles y estados funcionales. La mejora es exclusivamente visual y debe verificarse en escritorio y en la vista responsive antes de incorporarla a una demo formal.

La identidad visual incorpora también el amarillo distintivo en estados y detalles de interacción, junto con el logotipo oficial de SIA servido como recurso local para no depender de la disponibilidad del sitio externo.

La guía externa de arquitectura se incorporó como referencia de evolución. El estado actual debe presentarse como una prueba de concepto de software con voz cloud y pagos simulados; hardware industrial, Edge STT, POS, KDS y pasarela real pertenecen al piloto de producción.

## Pendientes para escalar hacia un kiosco real

Estos puntos son una hoja de evolución; no forman parte de la demo actual.

- **Evaluar STT local/Edge:** comparar Gemini Transcribe Live con motores locales como Whisper o Vosk usando el mismo conjunto de audios. Medir latencia total, calidad con ruido, costo por pedido, hardware necesario y comportamiento sin internet.
- **Definir un adaptador de transcripción:** encapsular el proveedor detrás de una interfaz común para cambiar de Gemini a un motor local sin modificar el flujo de pedido.
- **Captura para ambiente ruidoso:** probar un micrófono de matriz con beamforming y cancelación de eco acústico en el gabinete real. La configuración del navegador actual sirve para pruebas, pero no reemplaza esta validación física.
- **Experiencia de kiosco:** ejecutar el frontend en pantalla táctil y modo kiosco; agregar indicador de volumen, detección de silencio e interrupción del asistente cuando existan mediciones que justifiquen esas mejoras.
- **Persistencia e idempotencia:** guardar sesiones y pedidos en una base durable y asignar un identificador de operación para evitar duplicados ante reconexiones o reintentos.
- **Disponibilidad y stock:** reemplazar el menú estático por una fuente administrada o un adaptador al sistema que tenga el stock real.
- **Pasarela de pago:** después de confirmar el carrito, delegar QR, tarjeta o caja a un proveedor habilitado para el local. El proyecto conservaría la selección de método y recibiría un resultado de pago mediante un adaptador, sin almacenar datos sensibles.
- **POS y KDS:** publicar el pedido confirmado mediante clientes separados para el POS y la pantalla de cocina. Si un sistema externo falla, registrar el estado y permitir reintento idempotente sin volver a cobrar ni duplicar el pedido.
- **Ticketera:** agregar un adaptador de impresión que reciba el pedido aceptado por el POS, en lugar de imprimir directamente desde el navegador.
- **Operación y seguridad:** configurar autenticación del dispositivo, métricas de latencia, monitoreo, políticas de logs y recuperación ante caída de red.

El criterio de escalabilidad es agregar adaptadores detrás de contratos pequeños. La conversación y `OrderService` deben mantenerse estables mientras cambian el motor de voz, el proveedor de pago o el sistema externo.

### Disponibilidad de productos, bebidas y extras (15/09/2026)

El catalogo local ahora declara `available` para productos base y para cada
opcion de modificador. El estado permite informar "agotado" sin convertir el
producto en inexistente. `OrderService` rechaza una opcion no disponible antes
de cambiar el carrito, tambien durante un reemplazo o un cambio de modificador.
Las tools no piden una eleccion cuando un grupo obligatorio no conserva ninguna
alternativa disponible.

La suite automatica ejecuto 32 pruebas con `unittest`. Se verifico que
un extra agotado no agrega la linea, que una bebida obligatoria sin opciones
disponibles devuelve `unavailable_required_modifier` sin mutar y que un reemplazo
hacia un producto agotado conserva la linea original. La comprobacion usa un
catalogo cargado localmente; no prueba todavia una conversacion real de Gemini ni
la sincronizacion con un sistema externo de stock.

Para una prueba manual, cambiar temporalmente `available` a `false` en
`config/menu.json`, reiniciar la API y pedir ese producto por texto o voz. Se
espera que el asistente informe la falta de disponibilidad y que el carrito no
incorpore esa seleccion. Volver el valor a `true` al terminar la demostracion.

Se detecto y corrigio una inconsistencia: el catalogo repetia bebidas y extras
dentro de cada hamburguesa, por lo que Coca-Cola podia agotarse solo para una de
ellas. Los grupos ahora son compartidos y la prueba automatica confirma que una
Coca-Cola agotada se rechaza tambien al pedir Burger Doble.

### Estados de sesion y representacion de modificadores (16/09/2026)

El flujo de pago se unifico en `ACTIVE` -> `PAYMENT_PENDING` -> `CONFIRMED`.
Se elimino `OrderService.confirm_order()`, que confirmaba de forma directa y ya
no representaba la experiencia del dashboard. Las pruebas que lo usaban ahora
preparan el pago, eligen un metodo y lo completan mediante los metodos reales del
servicio. Mientras el pago esta pendiente, la persona puede elegir metodo o usar
atras para volver a `ACTIVE` y editar el mismo carrito.

Tambien se documento `Menu.get_modifier_details()`: no infiere ni valida
modificadores. Traduce IDs ya validados del carrito a nombres, obligatoriedad y
precios visibles para que el frontend renderice "Bebida", "Extras" y sus importes
sin repetir reglas de catalogo.

### Reconexion automatica del navegador (15/09/2026)

El frontend reintenta el WebSocket de la misma sesion despues de un cierre
inesperado. La espera aumenta de uno a quince segundos y los controles quedan
bloqueados hasta recibir el snapshot `connection.ready`. No reenvia texto ni
audio; si una captura estaba en curso, la descarta y conserva el carrito validado.
Un 4404 abre una sesion nueva porque la anterior ya no existe en memoria.

Se ejecuto la suite automatica completa: 32 pruebas de backend y una prueba de
navegador con Edge. Esta ultima fuerza el cierre del socket desde el servidor y
comprueba que la pagina muestra `Conexion restablecida` antes de continuar el
recorrido de voz, carrito y confirmacion. No prueba una perdida real de internet
ni recuperacion despues de reiniciar el proceso.

### Guia visual del recorrido de un pedido (15/09/2026)

Se agrego `docs/recorrido-pedido.html` como material de apoyo para la defensa.
Explica el arranque local, la sesion, el WebSocket, la captura, STT, Gemini,
tools, `OrderService` y el carrito. El diagrama ahora presenta los pasos en una
sola columna para que cada flecha una el paso consecutivo, y agrega una tabla de
conexiones concretas entre funciones y archivos. El ejemplo se amplio a una
sesion completa: alta de dos productos, consulta sin mutacion, cambio de
modificadores, eliminacion, confirmacion y pago QR simulado. El archivo es
estatico: no ejecuta Gemini ni el pedido; sus enlaces locales y estructura HTML
se verificaron automaticamente.
