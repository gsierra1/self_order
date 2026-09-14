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
serialización de envíos; sigue pendiente la reconexión automática del navegador.

## 06. Catálogo y precios locales estructurados

**Estado:** implementado.

**Interpretación:** un JSON pequeño permite comprobar reglas sin depender de un
sistema de ventas. Los modificadores modelados como grupos evitan que el precio
se deduzca de frases del usuario.

**Consecuencia:** el catálogo es configurable, pero las tools y el frontend
todavía asumen tamaño/bebida y dos opciones por grupo. Ampliar el menú requiere
revisar esas capas. El prompt incluye nombres e IDs, pero no precios ni el flag
de disponibilidad; no existe una tool específica de consulta de catálogo/precios.

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
