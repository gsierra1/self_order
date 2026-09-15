# Documentación del proyecto

Primera revisión: 14 de septiembre de 2026.

Este proyecto busca permitir que una persona haga su pedido hablando o
escribiendo, vea cómo se arma en pantalla y reciba aclaraciones antes de agregar
productos incompletos. La presentación técnica debe explicar tanto la experiencia
como las decisiones que la hacen confiable.

## Recorrido sugerido

1. [Producto y alcance](producto.md): qué se quiere construir y qué debe hacer.
2. [Arquitectura y contratos](arquitectura.md): módulos, funciones y recorrido
   de una interacción.
3. [Decisiones de arquitectura](decisiones.md): razones, alternativas y límites.
4. [Estado y pruebas](estado-y-pruebas.md): evidencia, problemas y siguientes etapas.
5. [README principal](../README.md): configuración y ejecución local.
6. [Seguimiento desde VS Code](seguimiento.md): acuerdos de commits y comandos
   para probar el frontend y revisar cambios.
7. [Voz por turnos](voz.md): arquitectura implementada, protocolo y pruebas.

## Cómo mantener estos documentos

Cada implementación debe actualizar el documento correspondiente en el mismo
cambio. Una capacidad pasa a «verificada» solo si se registra cómo se comprobó.
Una decisión propuesta pasa a «adoptada» cuando se decide y se implementa según
su alcance. Conservar los pendientes hasta resolverlos con evidencia.

La revisión inicial leyó todos los archivos fuente, configuración no secreta,
scripts de pruebas, historial Git reciente y estadísticas de logs locales.
No se inspeccionó el contenido de `.env` ni se escucharon audios de usuarios.
No se ejecutó una conversación real nueva contra Gemini durante esta revisión.

Los motivos históricos que no están escritos en código o commits se presentan
como interpretaciones, no como recuerdos de decisiones de la autora.
