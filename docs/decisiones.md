# Decisiones de arquitectura

## 01. Separar IA, servicio de pedidos y dominio

**Problema:** el lenguaje natural puede ser ambiguo y las respuestas del modelo
no deben definir precios ni saltarse validaciones.

**Decisión observada:** Gemini propone operaciones; las tools las adaptan;
`OrderService` valida y cambia objetos de dominio, es la autoridad sobre el pedido.
De esta manera no permitimos productos o precios inventados.

 «La IA entiende la intención; el backend decide si el pedido
es válido y cuánto cuesta».

El modelo de conversación ahora se configura en el .env con `GEMINI_CHAT_MODEL`. 
No se cambia automáticamente porque los logs muestran
que la latencia también puede venir de la red, cuota o la segunda llamada después
de una tool. La configuración permite comparar modelos con el mismo flujo y
mediciones antes de tomar una decisión.

## 02. Reemplazar como operación explícita

**Problema:** «Cambiame el Big Mac por un Cuarto de Libra» es una sola intención.
Con `remove` seguido de `add`, el alta podría fallar después de borrar el original.

**Decisión:** `replace_item` valida el nuevo producto y configuración, conserva
cantidad e identidad de línea y recién entonces modifica. Emite un único evento
de actualización con la acción semántica correcta.

**Consecuencia:** facilita mostrar y auditar un reemplazo. La atomicidad aquí
significa que un error de validación no deja la línea a medio cambiar.

## 03. Tools autorizadas y ejecución manual

**Interpretación:** controlar el punto donde una sugerencia del modelo produce
un efecto permite validar, observar y limitar la ejecución.

**Alternativa:** delegar la ejecución automática al SDK. Reduce código propio,
pero dificulta ubicar ciertos controles específicos de esta prueba de concepto.

**Consecuencia:** hay lista explícita, límite de ciclos y detección de repetición
en un turno. Varias llamadas distintas de una misma respuesta se ejecutan en el
orden recibido y sus resultados se envían juntos al modelo; una llamada repetida
se detiene antes de ejecutarse. Las firmas tipadas ayudan
al SDK a describir las tools; Python no valida esos tipos en ejecución por sí solo.


## 05. HTTP para inicio y consulta, WebSocket para interacción

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

**Interpretación:** un JSON permite comprobar reglas sin depender de un
sistema de ventas y ampliar el menu siguiendo las mismas. 
Los modificadores modelados como grupos evitan que el precio
se deduzca de frases del usuario.

**Consecuencia** las tools reciben un diccionario genérico de
modificadores y consultan los grupos obligatorios del producto antes de mutar.
`OrderService` rechaza grupos desconocidos, valida opciones y recalcula precios;
el frontend recibe nombres visibles desde el backend. Los extras se modelan como
grupos opcionales independientes, lo que permite acumular tomate, lechuga, jamón
y queso sin habilitar valores inventados.

Se agregaron aliases conversacionales al catálogo. El
orquestador los entrega a Gemini como equivalencias explícitas —por ejemplo,
«hamburguesa simple» para Burger Clásica— sin convertirlos en precios o reglas
duplicadas en código.

Los precios enteros evitan aritmética flotante en este catálogo de pesos argentinos completos.
Antes de integrar un POS habrá que fijar moneda, unidad monetaria y redondeo.

## 07. Disponibilidad de IA para una operación de kiosco

**Estado:** pendiente para un piloto.

**Contexto comprobado:** los logs locales registraron dos respuestas `503
MODEL_OVERLOADED` de diversos modelos en ciertos momentos. Ese código indica que el proveedor no
tuvo capacidad disponible temporalmente. Es distinto de un `429`, que indica que
la aplicación excedió una cuota de solicitudes, tokens o gasto configurada.

**Decisión propuesta:** para un piloto, usar un plan pago adecuado al volumen,
medir errores y latencias por proveedor/modelo, y conservar una ruta de
continuidad cuando falle la IA: escritura y selección táctil deben permitir
completar el pedido. Los reintentos de fallas temporales deben estar asociados a
un identificador de operación y nunca repetir una mutación del carrito sin poder
demostrar que la anterior no se aplicó.

Un plan pago de Gemini aumenta límites de uso y habilita más
capacidad que el nivel gratuito, pero no convierte un proveedor compartido en
infalible ni elimina por sí mismo los `503`. Para una necesidad de capacidad
previsible, evaluar Vertex AI y su Provisioned Throughput solo después de medir
el tráfico y confirmar que el modelo elegido lo admite.

**Alternativas:** Gemini no es el único proveedor. STT (Speech-to-Text: tecnología 
que transforma voz en texto) puede implementarse con
Gemini, Google Cloud Speech-to-Text, Deepgram, Azure Speech, OpenAI o un motor
local; el LLM de interpretación puede ser Gemini, OpenAI, Anthropic o un modelo
local. No son reemplazos de configuración: cada proveedor tiene protocolos,
herramientas y formatos propios.

**Consecuencia de arquitectura:** antes de un piloto se debe definir un contrato
`SpeechToText` para voz y otro de interpretación estructurada para el LLM. Cada
adaptador traduce su proveedor a esos contratos; `OrderService` permanece como
autoridad de menú, precios y estado. Esto permite usar un proveedor alternativo
o hacer failover sin reescribir las reglas del pedido.
