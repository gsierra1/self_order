# Pendientes del proyecto

Este documento contiene el trabajo que aun no esta implementado o verificado.
Un punto se retira de esta lista solo cuando existe codigo, documentacion y una
verificacion registrada junto con su cambio.

## Antes de una demostracion formal

En la revisión del 17/09/2026, el único comportamiento visible de la demo que
continúa sin implementar es el cierre automático del turno por silencio. Los
demás puntos de esta sección son verificaciones y mediciones previas a la
presentación, no funciones ausentes del recorrido actual.

- **Cierre formal de la matriz con proveedores reales:** las corridas del 16 y
  17/09/2026 ya comprobaron en navegador y con micrófono físico transcripción
  Gemini, interpretación Groq, altas y eliminaciones, cantidades agrupadas,
  vuelta desde un método al selector, selección de QR, tarjeta y caja, cierre
  del pedido y creación de una sesión nueva. También se escuchó la síntesis del
  navegador. Las 65 pruebas automáticas cubren reglas, adaptadores, transporte,
  caché del frontend y pago mediante simulaciones. Antes de la demostración
  falta registrar en una sola corrida real, con el modelo elegido para exponer,
  producto incompleto, producto agotado, reemplazo, varios extras y finalización
  de los tres pagos. Registrar modelo, fecha, resultado y latencia de cada caso.
- **Prueba ambiental en el equipo de la demo:** el funcionamiento básico del
  micrófono y los parlantes físicos ya fue comprobado. Falta evaluar ruido de
  fondo representativo, distancia al micrófono, cancelación durante una frase,
  pérdida y recuperación de red y calidad audible en el equipo concreto de la
  presentación. Las pruebas automáticas cubren cancelación y reconexión con
  simulaciones, pero no reproducen el ambiente físico.
- **Detección automática de silencio y turnos de voz:** incorporar detección de
  fin de habla para no depender de que la persona pulse **Enviar audio**. La
  interfaz debe cerrar el turno solo cuando haya silencio suficiente y enviar
  una única transcripción final; mientras la persona continúa hablando, el
  texto provisional no debe agregar productos al carrito.
- **Estabilidad de IA:** medir por separado transcripcion y chat: latencia,
  errores 429/503 y tasa de exito para un conjunto de pedidos representativo.
  Esta medición no bloquea la preparación del speech, pero sí hace falta para
  justificar qué modelos y plan de cuenta se usarían en un piloto.

## Para un piloto de kiosco

- **Evaluación de proveedores ya desacoplados:** los contratos `SpeechToText` y
  `OrderInterpreter`, las fábricas y los adaptadores Gemini, OpenAI y Groq ya
  están implementados. Para sumar **Anthropic u otro LLM**, crear cliente y
  lectura segura de su clave, configuración de modelo, clase `OrderInterpreter`
  que traduzca tool use a las tools existentes, rama en `backend/ai/factories.py`,
  manejo de errores y pruebas simuladas; luego ejecutar la matriz manual real.
  Para sumar **otro STT**, crear cliente y autenticación local del proveedor,
  adaptador `SpeechToText` con conexión, fragmentos, parciales, final,
  cancelación y cierre, configuración y rama en la fábrica STT; después validar
  audio real, latencia, ruido y reconexión. No seleccionar un proveedor futuro
  en `.env` hasta que su adaptador y pruebas existan.
- **Evaluacion Edge/STT local:** comparar latencia total, transcripcion con
  ruido, costo, hardware disponible y funcionamiento sin internet.
- **Persistencia e idempotencia:** guardar pedidos y sesiones en almacenamiento
  durable y asociar operaciones a identificadores que eviten duplicados ante
  reintentos o reconexiones.
- **Catálogo y stock escalables:** la demo usa `config/menu.json` porque el menú
  actual es pequeño y el archivo resulta sencillo de leer, actualizar,
  versionar y probar sin depender de servicios externos. Antes de producción se
  deben evaluar otras fuentes de catálogo y disponibilidad: una API de DEX, si
  ese sistema ofrece el contrato necesario; el POS del local; una API propia; o
  una base de datos como PostgreSQL cuando la aplicación sea responsable de
  administrar el catálogo. La integración elegida debe implementarse detrás de
  un contrato como `MenuRepository` o `CatalogProvider`, con un adaptador JSON
  para la demo y adaptadores separados para cada fuente futura. De esa manera,
  `Menu` y `OrderService` continúan validando productos, modificadores,
  disponibilidad y precios sin depender del lugar donde se almacenan.
- **Búsqueda de catálogo para menús grandes:** no enviar el catálogo completo al
  LLM en cada turno cuando crezca considerablemente, porque aumentaría la
  latencia, el consumo de contexto, el costo y la posibilidad de confundir
  productos. Incorporar una búsqueda previa por nombre, alias y categoría que
  entregue al intérprete solamente los candidatos relevantes. El LLM podrá
  proponer una operación sobre ese conjunto, pero `OrderService` deberá volver
  a validarla contra el catálogo vigente antes de modificar el carrito.
- **Copia local y sincronización del catálogo:** evitar consultar DEX, el POS o
  una API remota en cada frase. Mantener en el backend una copia local
  versionada del catálogo para responder con baja latencia y actualizarla por
  intervalos, webhooks o eventos, según las capacidades de la fuente. Antes del
  piloto se debe definir cada cuánto se actualiza, cómo se invalidan precios y
  disponibilidad, y si el kiosco puede seguir usando la última copia válida
  cuando la fuente remota no responde. También se debe comprobar que todos los
  kioscos reciban la misma versión y que los identificadores externos se
  traduzcan a identificadores internos estables.

## Para operar en un local

- **Pago real:** reemplazar QR de texto, tarjeta y caja simulados por un adaptador a la
  pasarela o sistema de cobro aprobado por el local. No almacenar datos de
  tarjetas en el proyecto.
- **POS, cocina y ticketera:** integrar clientes separados que reciban el pedido
  confirmado, registren fallas y permitan reintentos sin cobrar o enviar dos
  veces el mismo pedido.
- **Hardware y experiencia de kiosco:** probar pantalla tactil, microfono de
  matriz, cancelacion de eco, modo kiosco, red y monitoreo en ambiente real.

## Criterio de escalabilidad

El nucleo que valida menu, precios, disponibilidad y estados debe permanecer
estable. Las integraciones nuevas se agregaran como adaptadores en los bordes:
voz, IA, stock, pagos, POS y cocina. Asi una prueba de concepto puede evolucionar
sin reescribir el carrito ni las reglas del pedido.
