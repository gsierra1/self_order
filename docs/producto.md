# Producto y alcance

## Experiencia deseada

- La persona puede hablar o escribir dentro de una misma sesión de pedido.
- La pantalla refleja lo que se va pidiendo sin esperar al cierre del pedido.
- La columna conversacional muestra bebidas y extras del catálogo como guía visual;
  es informativa y no agrega productos por sí sola.
- Si el producto no existe o está indisponible, el asistente lo informa.
- Si faltan opciones obligatorias, pregunta antes de agregar la línea al carrito.
- Se pueden corregir productos y opciones durante la conversación.
- Altas repetidas con el mismo producto y configuración se agrupan en una sola
  línea con su cantidad total. Pedir que se quite una unidad reduce esa cantidad;
  solo una solicitud de eliminar el producto completo borra toda la línea.
- El asistente puede responder por texto y por voz; la voz puede desactivarse.
- La confirmación debe representar el estado real del pedido.
- Después de elegir un método de pago se muestra únicamente su flujo. Volver
  atrás permite elegir otro método; desde el selector se puede volver al carrito.

## Estados en la interfaz

Hay dos estados distintos que la interfaz debe representar:

1. **Información provisional:** transcripción parcial o producto todavía por
   completar. Puede cambiar si la persona se corrige.
2. **Carrito validado:** líneas completas aceptadas por `OrderService`, con precios
   calculados por el backend.

## Alcance actual y futuro

La implementación actual es una prueba de concepto local. El pedido vive en memoria
y dispone de un flujo de pago simulado con QR, tarjeta o caja. No existe cobro real,
envío a cocina, persistencia de pedidos ni integración con un sistema de ventas.
Una integración futura deberá delegar esas responsabilidades en los sistemas de
catálogo, stock, POS, cocina y pago que se elijan para el local.

La prioridad fue completar el pedido por voz manteniendo el canal escrito. El
frontend actual permite demostrar el recorrido y el menú sigue deliberadamente
acotado; ampliar el catálogo y realizar ajustes visuales adicionales son etapas
posteriores.

## Disponibilidad de productos y opciones

El catalogo diferencia dos situaciones: `available` en un producto base indica
si esa hamburguesa se puede pedir; `available` en una opcion indica si se puede
elegir esa bebida o extra. Ambos valores son configurables en `config/menu.json`
y hoy comienzan en `true`.

Si se marca, por ejemplo, Coca-Cola con `"available": false`, el asistente debe
explicar que existe pero esta agotada y ofrecer otra bebida, sin agregar una
Coca-Cola al carrito. Si no queda ninguna alternativa en un grupo obligatorio
como Bebida, la hamburguesa no se agrega porque no puede quedar incompleta.
`OrderService` aplica esta regla para texto, voz y botones; el LLM configurado recibe el
catalogo como contexto, pero no decide el estado valido del pedido.

Esta disponibilidad es local y manual para la demo. En una integracion real, el
valor deberia llegar desde el sistema de stock mediante un adaptador, sin cambiar
las reglas de carrito ni los canales de interaccion.
