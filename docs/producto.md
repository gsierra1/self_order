# Producto y alcance

## Contexto

Según su autora, el proyecto surge de una propuesta de Adrián, de SIA Interactive,
para explorar pedidos por voz. Además de mostrar una demo, la autora necesita
entender y defender el diseño técnico como parte de una oportunidad laboral.

SIA presenta soluciones digitales para espacios físicos y audiovisuales en su
[sitio oficial](https://www.siainteractive.com/es/). Esa orientación es compatible
con el escenario de una interfaz de pedidos en un punto de atención; esto último
es una interpretación del contexto, no un requisito de integración confirmado.

La referencia de inspiración es [el video compartido por la autora](https://www.youtube.com/watch?v=tsxXTB78RUE).
No fue posible recuperar su contenido durante esta revisión. No se atribuyen al
video funciones, proveedores ni arquitectura que no se hayan podido verificar.

## Experiencia deseada

- La persona puede hablar o escribir dentro de una misma sesión de pedido.
- La pantalla refleja lo que se va pidiendo sin esperar al cierre del pedido.
- Si el producto no existe o está indisponible, el asistente lo informa.
- Si faltan opciones obligatorias, pregunta antes de agregar la línea al carrito.
- Se pueden corregir productos y opciones durante la conversación.
- El asistente puede responder por texto y por voz; la voz puede desactivarse.
- La confirmación debe representar el estado real del pedido.

Ejemplo: «Quiero una Burger Clásica» requiere preguntar la bebida. Si la persona
responde «con Coca y queso», recién entonces se agrega la hamburguesa configurada
y se actualiza el importe. El queso es un extra opcional; no se agrega si la
persona no lo indicó. «Quiero una pizza» no debe crear un producto inexistente.

## Qué significa mostrar el pedido mientras se habla

Hay dos estados distintos que la interfaz debe representar:

1. **Información provisional:** transcripción parcial o producto todavía por
   completar. Puede cambiar si la persona se corrige.
2. **Carrito validado:** líneas completas aceptadas por `OrderService`, con precios
   calculados por el backend.

Esta separación se implementó en la primera versión de voz por turnos: la
interfaz muestra transcripción provisional y agrega al carrito solo después de
enviar el turno y completar la validación. Todavía no muestra tarjetas de
productos provisionales ni agrega líneas mientras se sigue hablando.

## Alcance actual y futuro

La implementación actual es una prueba de concepto local. Hay dos hamburguesas
de ejemplo, chat escrito y voz por turnos, estado en memoria y confirmación local. No existen pagos,
envío a cocina, persistencia de pedidos ni integración real con un sistema de
ventas. El código menciona DEX/POS como futuro destino; el contrato real con SIA
todavía debe conocerse.

La prioridad expresada es completar voz manteniendo el canal escrito. Ampliar el
menú y mejorar la estética quedan para después. Una presentación y un speech
se prepararán sobre capacidades demostrables y decisiones comprendidas.

## Disponibilidad de productos y opciones

El catalogo diferencia dos situaciones: `available` en un producto base indica
si esa hamburguesa se puede pedir; `available` en una opcion indica si se puede
elegir esa bebida o extra. Ambos valores son configurables en `config/menu.json`
y hoy comienzan en `true`.

Si se marca, por ejemplo, Coca-Cola con `"available": false`, el asistente debe
explicar que existe pero esta agotada y ofrecer Sprite o agua, sin agregar una
Coca-Cola al carrito. Si no queda ninguna alternativa en un grupo obligatorio
como Bebida, la hamburguesa no se agrega porque no puede quedar incompleta.
`OrderService` aplica esta regla para texto, voz y botones; Gemini recibe el
catalogo como contexto, pero no decide el estado valido del pedido.

Esta disponibilidad es local y manual para la demo. En una integracion real, el
valor deberia llegar desde el sistema de stock mediante un adaptador, sin cambiar
las reglas de carrito ni los canales de interaccion.
