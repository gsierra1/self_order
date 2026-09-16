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
- **Estabilidad de IA:** medir por separado transcripcion y chat: latencia,
  errores 429/503 y tasa de exito para un conjunto de pedidos representativo.
  Definir ambos modelos y el plan de cuenta con evidencia, no solo por
  disponibilidad declarada.
- **Capacidades conversacionales futuras:** decidir si `change_quantity` y
  `clear_cart`, ya disponibles en `OrderService`, deben exponerse al usuario por
  voz y texto. Si se incorporan, definir frases esperadas y pruebas.

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
