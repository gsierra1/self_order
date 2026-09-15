# Decisiones de arquitectura

Las decisiones 01–08 describen mecanismos existentes. Sus justificaciones son
interpretaciones de la revisión del 14/09/2026, salvo donde el código explicita
el motivo. Sirven para discutir con la autora y preparar la defensa; no son un
registro histórico inventado.

## 01. Separar IA, servicio de pedidos y dominio

**Estado:** implementado.

**Problema:** el lenguaje natural puede ser ambiguo y las respuestas del modelo
no deben definir precios ni saltarse validaciones.

**Decisión observada:** Gemini propone operaciones; las tools las adaptan;
`OrderService` valida y cambia objetos de dominio. El docstring del servicio
explicita que este es la autoridad sobre el pedido.

**Alternativa:** dejar que el modelo redacte un carrito JSON y usarlo directamente.
Sería sencillo para una demo, pero permitiría productos o precios inventados y
haría más difícil comprobar reglas independientemente del proveedor.

**Consecuencia:** texto y voz pueden compartir reglas y pruebas. Cambiar de
proveedor sigue requiriendo adaptar el orquestador, las tools y sus esquemas;
no es un reemplazo automático. El servicio depende del logger concreto y los
objetos devueltos son mutables, de modo que aún hay límites de encapsulación.

**Para explicar:** «La IA entiende la intención; el backend decide si el pedido
es válido y cuánto cuesta».

El modelo de conversación ahora se configura con `GEMINI_CHAT_MODEL`. El valor
actual sigue siendo `gemini-3.5-flash-lite`, que Google clasifica como su modelo
3.5 más rápido y económico; no se cambia automáticamente porque los logs muestran
que la latencia también puede venir de la red, cuota o la segunda llamada después
de una tool. La configuración permite comparar modelos con el mismo flujo y
mediciones antes de tomar una decisión.

La lista de modelos se consulta con `python -m backend.ai.list_models` usando la
API key local. Se mantiene como diagnóstico explícito porque la disponibilidad
depende de la cuenta y puede cambiar; los comentarios de `.env.example` son una
guía, no una garantía futura.

## 02. UUID para sesión y número local para línea

**Estado:** implementado mediante `uuid4()` y `max(line_id) + 1` respectivamente.

**Interpretación:** una sesión necesita una identidad técnica que se pueda generar
sin coordinar un contador global. Un UUID facilita crear sesiones independientes
y reduce colisiones a una probabilidad extremadamente pequeña. Una secuencia
1, 2, 3 también podría funcionar con almacenamiento y coordinación adecuados.

**Consecuencia:** el UUID es largo y poco útil como número visible de retiro.
Identificar una sesión no equivale a autenticar al usuario. En producción un
número amigable de pedido puede coexistir con el UUID técnico.

Las líneas se identifican solo dentro de una sesión: `line_id=1` en dos sesiones
no representa la misma línea. El algoritmo actual reutiliza IDs borrados; si se
necesitan referencias estables durante reconexiones o auditoría, debe cambiarse.

## 03. Reemplazar como operación explícita

**Estado:** implementado; el docstring explicita validación antes de mutar.

**Problema:** «Cambiame el Big Mac por un Cuarto de Libra» es una sola intención.
Con `remove` seguido de `add`, el alta podría fallar después de borrar el original.

**Decisión:** `replace_item` valida el nuevo producto y configuración, conserva
cantidad e identidad de línea y recién entonces modifica. Emite un único evento
de actualización con la acción semántica correcta.

**Consecuencia:** facilita mostrar y auditar un reemplazo. La atomicidad aquí
significa que un error de validación no deja la línea a medio cambiar; no es una
transacción de base de datos, no incluye rollback ante cualquier excepción y
no provee aislamiento frente a accesos concurrentes.

## 04. Tools autorizadas y ejecución manual

**Estado:** implementado; el SDK tiene deshabilitado automatic function calling.

**Interpretación:** controlar el punto donde una sugerencia del modelo produce
un efecto permite validar, observar y limitar la ejecución.

**Alternativa:** delegar la ejecución automática al SDK. Reduce código propio,
pero dificulta ubicar ciertos controles específicos de esta prueba de concepto.

**Consecuencia:** hay lista explícita, límite de ciclos y detección de repetición
en un turno. Varias llamadas distintas de una misma respuesta se ejecutan en el
orden recibido y sus resultados se envían juntos al modelo; una llamada repetida
se detiene antes de ejecutarse. Las firmas tipadas ayudan
al SDK a describir las tools; Python no valida esos tipos en ejecución por sí solo.

## 09. Separar confirmación, pago y cierre de sesión

**Estado:** implementado como flujo de demostración local.

**Decisión:** confirmar el carrito lleva la sesión a `PAYMENT_PENDING` y genera
un número de pedido en backend. La selección de método puede llegar por botones,
texto o voz mediante la misma tool. QR, tarjeta y caja terminan en una pantalla
de retiro y el botón final cierra la sesión.

**Motivo:** no mezclar la validación del pedido con un pago real y permitir que
la interfaz empiece un nuevo pedido sin recargar la página.

**Límites:** el QR es deliberadamente inválido y el campo de tarjeta es solo de
demo; una integración real requiere un proveedor que tokenice los datos y
confirme el pago. La vuelta atrás cancela el pago pendiente y genera otro número
cuando el pedido vuelva a confirmarse.

**Refuerzo adoptado el 15/09/2026:** si Gemini solicita por error
`confirm_order` cuando la sesión ya está en `PAYMENT_PENDING`, la tool devuelve
el estado existente, el mismo número de pedido y las opciones disponibles. No
vuelve a confirmar, no genera otro número y no marca una mutación. El modelo
recibe la indicación de elegir un método o volver a editar.

**Motivo:** la instrucción de sistema reduce esta llamada repetida, pero un LLM
puede incumplirla. La protección se coloca junto a la operación transaccional
para que el flujo conserve consistencia aun si la interpretación falla.

**Consecuencia:** puede haber una ronda adicional de conversación antes de que
Gemini elija el método correcto, pero ya no se publica una advertencia de
validación ni se altera el pedido pendiente. Una mejora futura podría reconocer
de forma determinista una elección inequívoca de pago antes de consultar al LLM.

## 05. HTTP para inicio y consulta, WebSocket para interacción

**Estado:** implementado.

**Interpretación:** HTTP resuelve creación/consulta y WebSocket permite publicar
el carrito al cambiar y transportar mensajes y audio sobre una conexión abierta.

**Alternativa:** consultar periódicamente el carrito por HTTP. Es más simple,
pero introduce espera y peticiones repetidas para saber si hubo cambios.

**Consecuencia:** el callback desacopla el servicio del transporte; el puente entre
threads permite usar el SDK síncrono. Faltan reconexión, sincronización del snapshot,
control de envíos concurrentes y manejo completo de desconexión en la revisión
inicial. En la etapa de voz se resolvieron limpieza, snapshot al conectar y
serialización de envíos; la reconexion automatica del navegador se incorpora en la etapa posterior.

## 06. Catálogo y precios locales estructurados

**Estado:** implementado.

**Interpretación:** un JSON pequeño permite comprobar reglas sin depender de un
sistema de ventas. Los modificadores modelados como grupos evitan que el precio
se deduzca de frases del usuario.

**Consecuencia inicial:** el catálogo era configurable, pero las tools y el
frontend asumían tamaño/bebida y dos opciones por grupo.

**Ajuste adoptado el 15/09/2026:** las tools reciben un diccionario genérico de
modificadores y consultan los grupos obligatorios del producto antes de mutar.
`OrderService` rechaza grupos desconocidos, valida opciones y recalcula precios;
el frontend recibe nombres visibles desde el backend. Los extras se modelan como
grupos opcionales independientes, lo que permite acumular tomate, lechuga, jamón
y queso sin habilitar valores inventados.

**Motivo:** ampliar el menú solo desde JSON habría conservado reglas ocultas para
tamaño y bebida. Llevar la definición de grupos al catálogo evita duplicar esas
reglas entre Gemini, backend y frontend.

**Límite:** cada grupo actual admite una sola opción. Si en el futuro un grupo
necesita varias elecciones dentro del mismo grupo, habrá que extender el contrato
de modificadores y repetir sus pruebas.

**Ajuste posterior:** se agregaron aliases conversacionales al catálogo. El
orquestador los entrega a Gemini como equivalencias explícitas —por ejemplo,
«hamburguesa simple» para Burger Clásica— sin convertirlos en precios o reglas
duplicadas en código.

**Ajuste de interfaz posterior:** el snapshot del carrito incluye el identificador
del grupo y si una selección es obligatoria, junto con su nombre y precio
visible. El frontend muestra los obligatorios junto al precio base y agrupa los
opcionales como extras. El tachito de cada extra pide al backend quitar ese grupo
opcional; el tachito junto al total de la línea elimina el producto completo.

**Motivo:** el navegador necesita saber qué control corresponde a cada extra,
pero no debe deducir si una selección es removible ni recalcular importes. La
decisión mantiene voz, texto y botones sobre las mismas reglas de `OrderService`.

Los precios enteros evitan aritmética flotante en este catálogo de pesos argentinos completos.
Antes de integrar un POS habrá que fijar moneda, unidad monetaria y redondeo.

## 07. Sesiones en memoria y confirmación local

**Estado:** implementado como prueba de concepto.

**Interpretación:** permite demostrar conversación y carrito sin introducir una
base de datos o una integración aún desconocida.

**Consecuencia:** al reiniciar se pierden sesiones. Varios workers no comparten
el diccionario. No hay expiración ni liberación sistemática de clientes. Confirmar
no envía el pedido a cocina ni implica pago. El propio código exige que un futuro
DEX/POS acepte el pedido antes de marcarlo confirmado.

## 08. Distinguir falla del proveedor de operación aplicada

**Estado:** implementado y con evidencia en logs anteriores.

**Problema:** puede agregarse el producto correctamente y fallar Gemini al redactar
la respuesta posterior. Repetir toda la solicitud puede duplicar el pedido.

**Decisión observada:** conservar `stage`, `transaction_applied` y `last_tool`,
registrar el error y mostrar un mensaje que avisa si ya se aplicó una operación.

**Consecuencia:** mejora diagnóstico y experiencia, pero no reemplaza IDs de
operación o idempotencia. `retryable` describe el error del proveedor; no autoriza
a repetir una mutación. Si un turno tiene varias operaciones, el booleano solo
indica que hubo alguna mutación, no que se completó todo el turno.

## 09. Integración de voz sobre el mismo pedido

**Estado:** adoptada e implementada para turnos explícitos el 14/09/2026.

**Restricción:** conservar `OrderService` como autoridad y un único estado de
sesión para voz y texto. Mostrar transcripciones parciales separadas del carrito.

**Alternativas a evaluar con un prototipo:**

| Opción | Beneficio esperado | Costo o dificultad |
| --- | --- | --- |
| Transcripción → orquestador actual → síntesis de voz | Reutiliza el flujo escrito y facilita probar cada etapa. | Puede sumar latencia y exige coordinar varios pasos. |
| Sesión conversacional Live con tools de pedido | Puede acercar escucha y respuesta a una conversación continua. | Requiere adaptar tools, turnos, interrupciones, recuperación y convivencia con texto. |

**Decisión:** transcripción con `gemini-3.5-transcribe-live`, orquestador existente
y síntesis del navegador. Se verificaron documentación del proveedor, acceso al
modelo y transcripción real con el PCM de prueba. No se midieron todavía costos
ni latencias comparativas contra un agente Live con tools.

**Motivo:** conservar un solo historial y las mismas validaciones para texto y
voz, evitando dos agentes independientes intentando administrar el pedido.
El módulo de transcripción no recibe tools. La voz de salida depende del navegador
y no agrega otra integración de generación de audio en esta etapa.

**Consecuencias:** clic para empezar y clic para enviar; transcripción provisional
visible, sin mutar el carrito durante la frase. Se suman transcripción y generación
de texto, lo que puede aumentar la latencia. El timbre depende de las voces del
equipo. Detección de silencio, interrupciones y evaluación acústica quedan para
una etapa posterior. Contratos y pruebas en [voz](voz.md).

**Criterio para decidir:** la persona debe poder completar y corregir un pedido
sin duplicados, recibir aclaraciones, ver el estado real y continuar escribiendo
si falla o desactiva el audio. La primera demo puede delimitar turnos explícitos;
la conversación con interrupciones requiere una etapa adicional bien probada.

## 10. Identidad visual alineada con SIA Interactive

**Estado:** adoptada para la capa de presentación el 14/09/2026.

**Contexto:** la autora pidió que el autoservicio se reconozca como una experiencia de SIA y que la interfaz comunique intención de producto, sin alterar el flujo de pedidos.

**Decisión:** usar Inter, la paleta violeta de marca (`#7332fa`, `#4e19d5`) y fondos oscuros y claros con gradientes sutiles. El título visible pasa a ser “Hace tu pedido” y se suma una bajada que explica las alternativas de voz y escritura.

**Alternativas consideradas:** mantener el estilo neutro existente o introducir una biblioteca visual completa. Se mantiene CSS propio para no sumar dependencias ni acoplar la lógica a un framework de interfaz.

**Consecuencias:** mejora el reconocimiento de marca y la jerarquía visual, conserva los contratos y controles existentes, y requiere una validación responsive antes de una presentación pública.

**Ajuste posterior:** se incorporó el logotipo oficial como recurso local y amarillo de acento para reforzar la asociación visual sin introducir una dependencia de red en tiempo de ejecución.

## 11. Alcance de la guía de kiosco físico

**Estado:** referencia de evolución, no implementación requerida todavía.

**Decisión:** mantener el diseño actual para validar conversación, reglas de pedido y estados con texto, voz por turnos y frontend web. Incorporar interfaces de adaptador antes de conectar STT local, POS, KDS, pagos o ticketera reales.

**Motivo:** la guía mezcla decisiones de producto, hardware y operación con componentes que todavía no tienen un entorno de prueba. Implementarlos ahora agregaría complejidad sin evidencia de que resuelvan el flujo principal.

**Consecuencia:** la demo no puede presentarse como kiosco listo para producción. Sí puede presentarse como el núcleo conversacional y transaccional que luego se integra con el hardware y los sistemas externos.

## 12. Evaluación futura de Edge y proveedores

**Estado:** pendiente de investigación y pruebas comparativas.

**Definición:** Edge significa procesar el audio cerca del dispositivo que captura la voz, en vez de enviarlo siempre a un servidor remoto. Puede ejecutarse en una PC industrial, Intel NUC, Raspberry Pi 5 u otro equipo con acelerador NPU/GPU; el hardware permite ejecutar el motor, pero Edge no es un motor específico.

**Motores candidatos:** Whisper (por ejemplo, una variante optimizada para CPU/GPU) y Vosk son alternativas de reconocimiento local. Cambiar de Gemini a STT significa cambiar únicamente la etapa que convierte audio en texto; el texto resultante seguiría entrando al mismo orquestador y `OrderService`.

**Decisión provisional:** mantener Gemini para la demo y medir antes de cambiarlo. La comparación debe usar audios equivalentes y registrar latencia total, calidad con ruido, costo por pedido, hardware disponible y funcionamiento sin internet.

**Consecuencia:** si un motor local resulta más conveniente, se incorpora mediante un adaptador de transcripción. No debería ser necesario reescribir las reglas de menú, carrito, pagos o frontend.

## 13. Diferencia práctica entre STT cloud y Edge

**STT** describe la función: convertir audio en texto. **Edge** describe dónde se ejecuta esa función: cerca del micrófono, en el equipo del kiosco. Gemini Transcribe Live es un STT cloud; Whisper o Vosk ejecutándose en una PC local serían STT Edge.

| Alternativa | Ventaja principal | Costo o límite |
| --- | --- | --- |
| Gemini Transcribe Live actual | Permite validar rápido con el hardware existente y delega mantenimiento del modelo al proveedor. | Depende de internet, tiene latencia variable y costo por uso. |
| STT Edge | Puede responder sin internet, reducir la latencia de red y mantener el audio local. | Requiere hardware, instalación, actualizaciones y pruebas de calidad con ruido. |

Edge no mejora automáticamente la transcripción. Es una alternativa operativa que solo conviene adoptar si las mediciones de latencia, ruido, costo, privacidad y disponibilidad justifican el hardware adicional.

## 14. Disponibilidad de IA para una operación de kiosco

**Estado:** pendiente para un piloto; no forma parte de la garantía de la demo.

**Contexto comprobado:** los logs locales registraron dos respuestas `503
MODEL_OVERLOADED` de `gemini-3.6-flash`. Ese código indica que el proveedor no
tuvo capacidad disponible temporalmente. Es distinto de un `429`, que indica que
la aplicación excedió una cuota de solicitudes, tokens o gasto configurada.

**Decisión propuesta:** para un piloto, usar un plan pago adecuado al volumen,
medir errores y latencias por proveedor/modelo, y conservar una ruta de
continuidad cuando falle la IA: escritura y selección táctil deben permitir
completar el pedido. Los reintentos de fallas temporales deben estar asociados a
un identificador de operación y nunca repetir una mutación del carrito sin poder
demostrar que la anterior no se aplicó.

**Sobre pagar:** un plan pago de Gemini aumenta límites de uso y habilita más
capacidad que el nivel gratuito, pero no convierte un proveedor compartido en
infalible ni elimina por sí mismo los `503`. Para una necesidad de capacidad
previsible, evaluar Vertex AI y su Provisioned Throughput solo después de medir
el tráfico y confirmar que el modelo elegido lo admite.

**Alternativas:** Gemini no es el único proveedor. STT puede implementarse con
Gemini, Google Cloud Speech-to-Text, Deepgram, Azure Speech, OpenAI o un motor
local; el LLM de interpretación puede ser Gemini, OpenAI, Anthropic o un modelo
local. No son reemplazos de configuración: cada proveedor tiene protocolos,
herramientas y formatos propios.

**Consecuencia de arquitectura:** antes de un piloto se debe definir un contrato
`SpeechToText` para voz y otro de interpretación estructurada para el LLM. Cada
adaptador traduce su proveedor a esos contratos; `OrderService` permanece como
autoridad de menú, precios y estado. Esto permite usar un proveedor alternativo
o hacer failover sin reescribir las reglas del pedido.

**Fuentes de consulta:** [cuotas de Gemini](https://ai.google.dev/gemini-api/docs/rate-limits),
[facturación de Gemini](https://ai.google.dev/gemini-api/docs/billing) y
[capacidad aprovisionada en Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/resources/throughput-quota).

## 15. Disponibilidad declarada en catalogo

**Estado:** implementada para la demo local.

**Contexto:** un producto puede existir en el menu y estar agotado. La misma
situacion aplica a una bebida o un extra: quitarlo del JSON haria imposible
distinguir "no existe" de "existe, pero hoy no se puede pedir".

**Decision:** conservar `available` en `Product` y agregarlo en cada
`ModifierOption`. `OrderService` rechaza ambos casos antes de mutar el carrito.
Las tools detectan ademas si un grupo obligatorio quedo sin ninguna opcion
disponible y devuelven un estado explicito, para que la conversacion no pregunte
por una seleccion imposible. Gemini recibe disponibilidad y alternativas en su
catalogo, pero la validacion final no depende de que siga la instruccion.

**Alternativas consideradas:** eliminar temporalmente items del menu o dejar que
solo el prompt controle el stock. La primera pierde la explicacion y referencias
estables; la segunda permite que una respuesta incorrecta del modelo agregue una
opcion agotada.

**Consecuencias:** para agotar Coca-Cola se cambia solo su `available` a `false`
en `config/menu.json` y se recarga la aplicacion. El carrito no se altera si una
alta, cambio o reemplazo contiene una opcion agotada; un reemplazo conserva su
linea original. La fuente sigue siendo manual y local: la integracion con stock
real requiere un adaptador que actualice esa informacion.

**Ajuste posterior:** bebidas y extras no se repiten dentro de cada hamburguesa.
El JSON declara grupos compartidos y cada producto conserva solo sus referencias.
Asi, marcar Coca-Cola o tomate como agotado actualiza la disponibilidad de todas
las hamburguesas que lo ofrecen. Esta normalizacion evita configuraciones
contradictorias y mantiene una sola fuente local para stock de modificadores.

## 16. Reconexion automatica sin reenvio de operaciones

**Estado:** implementada para la demo con sesiones en memoria.

**Contexto:** el WebSocket puede cerrarse por una perdida momentanea de red.
Reenviar automaticamente el ultimo texto o audio seria inseguro porque el backend
pudo haber aplicado una mutacion antes de perder la respuesta.

**Decision:** reintentar la conexion con el mismo `session_id` y espera
progresiva. Al volver, usar exclusivamente el snapshot `connection.ready` como
fuente de verdad. Si habia audio local, se descarta. Un cierre intencional no
reconecta; un 4404 inicia una sesion nueva porque el backend ya no conserva la
anterior.

**Consecuencias:** el carrito se recupera ante una desconexion breve sin duplicar
items. El texto de respuesta que se perdio no se reconstruye y la persistencia
tras reiniciar el proceso sigue pendiente.
