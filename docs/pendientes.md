# Pendientes del proyecto

Este documento contiene el trabajo que aun no esta implementado o verificado.
Un punto se retira de esta lista solo cuando existe codigo, documentacion y una
verificacion registrada junto con su cambio.


- **Calibración del fin de habla:** el navegador considera terminada una frase
  después de 1,4 segundos de silencio posteriores a voz detectada. En una
  corrida manual se distinguió correctamente el silencio, pero falta comparar
  habla continua, pausas naturales y una persona que duda antes de decidir si
  el intervalo se conserva o se aumenta. El botón de envío manual debe seguir
  disponible durante la evaluación.
- **Inicio de escucha y privacidad:** evaluar si una experiencia manos libres
  puede evitar que la persona pulse «Hablar» en cada turno. El botón actual
  puede resultar incómodo en una conversación larga, pero también hace visible
  cuándo se enciende el micrófono y evita que el sistema escuche continuamente.
  Antes de cambiarlo se debe diseñar una activación clara —por toque inicial,
  palabra de activación o ventana acotada de conversación— con indicador visual,
  cancelación accesible y descarte del audio fuera del turno.

## Para un piloto de sistema

- **Evaluacion Edge/STT local:** comparar latencia total, transcripcion con
  ruido, costo, hardware disponible y funcionamiento sin internet.
- **Pruebas ambientales y estabilidad de IA:** medir en el hardware y ambiente
  del sistema distancia al micrófono, ruido, cancelación de eco, pérdida de red,
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
  disponibilidad, y si el sistema puede seguir usando la última copia válida
  cuando la fuente remota no responde. También se debe comprobar que todos los
  sistemas reciban la misma versión y que los identificadores externos se
  traduzcan a identificadores internos estables.

## Para operar en un local

- **Pago real:** reemplazar QR de texto, tarjeta y caja simulados por un adaptador a la
  pasarela o sistema de cobro aprobado por el local. No almacenar datos de
  tarjetas en el proyecto.
- **POS, cocina y ticketera:** integrar clientes separados que reciban el pedido
  confirmado, registren fallas y permitan reintentos sin cobrar o enviar dos
  veces el mismo pedido.
- **Hardware y experiencia de sistema:** probar pantalla tactil, microfono de
  matriz, cancelacion de eco, modo sistema, red y monitoreo en ambiente real.


