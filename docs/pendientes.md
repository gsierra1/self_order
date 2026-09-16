# Pendientes del proyecto

Este documento contiene el trabajo que aun no esta implementado o verificado.
Un punto se retira de esta lista solo cuando existe codigo, documentacion y una
verificacion registrada junto con su cambio.

## Antes de una demostracion formal

- **Prueba manual con proveedor real:** completar la matriz de texto y voz con
  Gemini configurado y repetir texto con `LLM_PROVIDER=groq`, incluyendo
  producto incompleto, producto agotado,
  reemplazo, varios extras, pago QR/tarjeta/caja, vuelta desde pago y errores
  temporales del proveedor. Registrar modelo, fecha, latencias y resultado
  observado. Ya se verificaron manualmente el alta de una Burger Clásica con
  Agua y el cambio de extra con `openai/gpt-oss-20b`; aún falta ejecutar la
  matriz completa desde el navegador y por voz.
- **Prueba de microfono y parlantes fisicos:** verificar permisos, silencio,
  ruido, cancelacion, interrupcion, reconexion y calidad audible en el equipo
  de la demo. Las pruebas actuales usan audio y navegador simulados.
- **Detección automática de silencio y turnos de voz:** incorporar detección de
  fin de habla para no depender de que la persona pulse **Enviar audio**. La
  interfaz debe cerrar el turno solo cuando haya silencio suficiente y enviar
  una única transcripción final; mientras la persona continúa hablando, el
  texto provisional no debe agregar productos al carrito.
- **Estabilidad de IA:** medir por separado transcripcion y chat: latencia,
  errores 429/503 y tasa de exito para un conjunto de pedidos representativo.
  Definir ambos modelos y el plan de cuenta con evidencia, no solo por
  disponibilidad declarada.
- **Capacidades conversacionales futuras:** decidir si `change_quantity`, ya
  disponible en `OrderService`, debe exponerse al usuario por voz y texto. Si se
  incorpora, definir frases esperadas y pruebas. `clear_cart` ya está expuesto
  como una única tool para evitar encadenar eliminaciones individuales.

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
