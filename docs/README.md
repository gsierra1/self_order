# Documentación del proyecto

Este proyecto busca permitir que una persona haga su pedido hablando o
escribiendo, vea cómo se va modificando su carrito en pantalla y reciba 
aclaraciones antes de agregar productos incompletos. 

## Recorrido sugerido

1. [Producto y alcance](producto.md): qué se quiere construir y qué debe hacer.
2. [Arquitectura y contratos](arquitectura.md): módulos, funciones y recorrido
   de una interacción, junto con las razones y límites de las decisiones vigentes.
3. [Pendientes](pendientes.md): trabajo pendiente, prioridad y criterio para darlo por resuelto.
4. [README principal](../README.md): configuración y ejecución local.
5. [Voz por turnos](voz.md): arquitectura implementada, protocolo y pruebas.
6. [Recorrido visual de un pedido](recorrido-pedido.html): diagrama interactivo con archivos y funciones.

## Cómo mantener estos documentos

Cada implementación debe actualizar el documento correspondiente en el mismo
cambio. Una capacidad pasa a «verificada» solo si se registra cómo se comprobó.
Las decisiones arquitectónicas vigentes y sus justificaciones se mantienen en
`arquitectura.md`, dentro de la sección a la que afectan. Conservar los
pendientes hasta resolverlos con evidencia.
