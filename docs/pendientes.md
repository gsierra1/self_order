# Pendientes del proyecto

Este documento contiene el trabajo que aun no esta implementado o verificado.
No repite el historial: la evidencia de cada cambio queda en
[estado-y-pruebas.md](estado-y-pruebas.md). Un punto se retira de esta lista solo
cuando existe codigo, documentacion y una verificacion registrada.

## Antes de una demostracion formal

- **Prueba manual con proveedor real:** completar la matriz de texto y voz con
  Gemini configurado, incluyendo producto incompleto, producto agotado,
  reemplazo, varios extras, pago y vuelta desde pago. Registrar modelo, fecha,
  latencias y resultado observado.
- **Prueba de microfono y parlantes fisicos:** verificar permisos, silencio,
  ruido, cancelacion, interrupcion y calidad audible en el equipo de la demo.
  Las pruebas actuales usan audio y navegador simulados.
- **Estabilidad de IA:** medir latencia, errores 429/503 y tasa de exito para un
  conjunto de pedidos representativo. Definir el modelo y plan de cuenta con
  evidencia, no solo por disponibilidad declarada.

## Para un piloto de kiosco

- **Contrato de proveedores:** definir adaptadores para STT y LLM de modo que se
  pueda evaluar Gemini, otro proveedor cloud o un motor local sin modificar
  `OrderService`.
- **Evaluacion Edge/STT local:** comparar latencia total, transcripcion con
  ruido, costo, hardware disponible y funcionamiento sin internet.
- **Persistencia e idempotencia:** guardar pedidos y sesiones en almacenamiento
  durable y asociar operaciones a identificadores que eviten duplicados ante
  reintentos o reconexiones.
- **Stock administrado:** reemplazar el JSON local por un adaptador a una fuente
  de disponibilidad real, conservando las validaciones de `OrderService`.

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
