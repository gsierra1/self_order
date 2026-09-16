# Producto y alcance

## Contexto

El proyecto surge de una propuesta de SIA Interactive [sitio oficial](https://www.siainteractive.com/es/),
para explorar pedidos por voz. 

## Experiencia deseada

- La persona puede hablar o escribir dentro de una misma sesión de pedido.
- La pantalla refleja lo que se va pidiendo sin esperar al cierre del pedido.
- Si el producto no existe o está indisponible, el asistente lo informa.
- Si faltan opciones obligatorias, pregunta antes de agregar la línea al carrito.
- Se pueden corregir productos y opciones durante la conversación.
- El asistente puede responder por texto y por voz; la voz puede desactivarse.
- La confirmación debe representar el estado real del pedido.

Ejemplo: «Quiero una Burger Clásica» requiere preguntar la bebida pues la misma 
no es opcional sino obligatoria. Si la persona responde «con Coca y queso», 
recién entonces se agrega la hamburguesa configurada y se actualiza el importe. 
El queso es un extra opcional; no se agrega si la persona no lo indicó. 
«Quiero una pizza» no debe crear un producto inexistente.

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
DEX/POS deberá manejar esas responsabilidades en una etapa futura.

La prioridad fue completar el pedido por voz manteniendo el canal escrito. Ampliar el
menú y mejorar la estética quedan para después. 

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
