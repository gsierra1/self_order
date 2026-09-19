# Pendientes del proyecto

Este documento contiene el trabajo que aun no esta implementado o verificado.
Un punto se retira de esta lista solo cuando existe codigo, documentacion y una
verificacion registrada junto con su cambio.

## Antes de una demostracion formal

En la revisión del 17/09/2026 no quedan fallas bloqueantes conocidas para el
recorrido previsto de la demo. Resta calibrar el fin de habla y ejecutar y
registrar la corrida final.

- **Cierre formal de la matriz con proveedores reales:** las corridas del 16 y
  17/09/2026 ya comprobaron en navegador y con micrófono físico transcripción
  Gemini, interpretación Groq, altas y eliminaciones, cantidades agrupadas,
  vuelta desde un método al selector, selección de QR, tarjeta y caja, cierre
  del pedido y creación de una sesión nueva. También se escuchó la síntesis del
  navegador. Las 92 pruebas automáticas cubren reglas, adaptadores, transporte,
  caché del frontend y pago mediante simulaciones. Antes de la demostración
  falta registrar en una sola corrida real, con el modelo elegido para exponer,
  producto incompleto, producto agotado, reemplazo, varios extras y finalización
  de los tres pagos. Registrar modelo, fecha y resultado de cada caso.
- **Calibración del fin de habla:** el navegador considera terminada una frase
  después de 1,4 segundos de silencio posteriores a voz detectada. En una
  corrida manual se distinguió correctamente el silencio, pero falta comparar
  habla continua, pausas naturales y una persona que duda antes de decidir si
  el intervalo se conserva o se aumenta. El botón de envío manual debe seguir
  disponible durante la evaluación.
- **Matriz manual de Whisper local en navegador:** `whisper_browser` quedó
  implementado con el modelo `onnx-community/whisper-tiny`, WebGPU o CPU y
  pruebas simuladas de transporte. Falta ejecutar y registrar una comparación
  real contra Gemini y Vosk con el mismo micrófono: frases con «Sprite», «QR» y
  modificadores, español rioplatense, pausas, ruido y pedidos largos. Registrar
  por separado la primera carga del modelo, los turnos siguientes, el dispositivo
  realmente usado, el texto final y el tiempo hasta que el carrito responde.
- **Inicio de escucha y privacidad:** evaluar si una experiencia manos libres
  puede evitar que la persona pulse «Hablar» en cada turno. El botón actual
  puede resultar incómodo en una conversación larga, pero también hace visible
  cuándo se enciende el micrófono y evita que el kiosco escuche continuamente.
  Antes de cambiarlo se debe diseñar una activación clara —por toque inicial,
  palabra de activación o ventana acotada de conversación— con indicador visual,
  cancelación accesible y descarte del audio fuera del turno.

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
  en `.env` hasta que su adaptador y pruebas existan. Vosk ya cumple ese contrato
  y puede seleccionarse; su validación con modelo y micrófono reales sigue pendiente.
- **Selección de STT sin costo de uso o con cuota limitada:** la investigación del
  18/09/2026 no encontró un STT cloud ilimitado y gratis que sea adecuado para
  producción. Las alternativas locales no cobran por minuto: **Vosk** funciona
  sin internet y su modelo español disponible es Apache 2.0, pero el modelo
  grande ocupa 1,4 GB; **Whisper** y **faster-whisper** también pueden correr
  localmente y Whisper publica código y pesos bajo MIT, aunque requieren
  descargar el modelo y consumir CPU/GPU. Vosk fue el primer candidato local
  evaluado porque su reconocimiento incremental se adapta naturalmente a los
  fragmentos y parciales de `SpeechToText`; el adaptador quedó implementado el
  18/09/2026 con pruebas simuladas. Falta medir su precisión con español
  rioplatense, ruido y el micrófono real. `whisper_browser` ya implementa
  Whisper al finalizar el turno, sin enviar PCM al servidor; falta su matriz
  real. Whisper/faster-whisper en backend seguirían siendo alternativas futuras
  que requerirían modelo instalado, adaptador `SpeechToText` y una estrategia de
  parciales o ventanas de audio.

  Entre las alternativas cloud con cuota inicial, Google Cloud Speech-to-Text
  ofrece 60 minutos mensuales sin cargo y streaming bidireccional, aunque exige
  habilitar facturación; Azure Speech F0 ofrece una cuota gratuita limitada y
  una sola transcripción concurrente; Deepgram ofrece crédito promocional, no
  gratuidad permanente. OpenAI requiere crédito de API, como confirmó la prueba
  local de `credit_balance_exhausted`. Groq ofrece Whisper muy rápido, pero su
  endpoint actual procesa archivos y publica precios por hora: serviría como
  adaptador final al cerrar el audio, no como reemplazo inmediato del streaming
  actual. Antes de implementar, comparar Vosk local, Google Cloud streaming y
  Azure/Deepgram según costo, español rioplatense, ruido, latencia y hardware.
  Fuentes: [Vosk y modelos](https://github.com/alphacep/vosk-space/blob/master/models.md),
  [Whisper](https://github.com/openai/whisper),
  [Google Cloud STT](https://cloud.google.com/speech-to-text/pricing),
  [cuotas streaming de Google](https://cloud.google.com/speech-to-text/docs/quotas),
  [Azure Speech](https://learn.microsoft.com/azure/ai-services/speech-service/speech-services-quotas-and-limits),
  [Deepgram](https://deepgram.com/pricing) y
  [Groq Speech-to-Text](https://console.groq.com/docs/speech-to-text).
- **Evaluacion Edge/STT local:** comparar latencia total, transcripcion con
  ruido, costo, hardware disponible y funcionamiento sin internet.
- **Pruebas ambientales y estabilidad de IA:** medir en el hardware y ambiente
  del kiosco distancia al micrófono, ruido, cancelación de eco, pérdida de red,
  calidad audible, latencia por etapa, errores 429/503 y tasa de éxito. Definir
  con esa evidencia los modelos, hardware y plan de cuenta del piloto.
- **Persistencia e idempotencia:** guardar pedidos y sesiones en almacenamiento
  durable y asociar operaciones a identificadores que eviten duplicados ante
  reintentos o reconexiones.
- **Vencimiento de sesiones en memoria:** la demo conserva las sesiones en el
  proceso para permitir reconexión y mostrar el cierre local. Antes de un uso
  continuo se debe definir TTL, limpieza de sesiones confirmadas/inactivas y
  cierre de clientes de IA, o mover ese estado a la persistencia durable.
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
