# Cómo seguir los cambios desde VS Code

## Acuerdo de trabajo

Cada etapa incluye explicación del problema y del cambio, verificación apropiada,
actualización documental y un commit local con una oración breve en español.
Al terminar se informa su identificador y cómo reproducir las pruebas. Un commit
registra una versión local; `push` es la operación separada que la publica en el
remoto. Los cambios documentales o de Git pueden no tener efecto en pantalla.

## Qué es AGENTS.md

Es un archivo Markdown de instrucciones para asistentes de programación que
trabajan en el repositorio. Codex reconoce ese nombre y utiliza sus reglas como
contexto de trabajo, según la [documentación oficial](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
No ejecuta procesos ni crea agentes. En este proyecto no se envía al Gemini del
bot: sus instrucciones se construyen en `_build_system_instruction()` dentro de
`backend/ai/orchestrator.py`.

## Levantar el frontend

En VS Code, abrir la carpeta del proyecto y luego **Terminal → Nueva terminal**.
Elegir PowerShell. Con el entorno y `.env` ya configurados:

```powershell
Set-Location C:\Users\User\Desktop\self_order
.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --reload
```

Mantener esa terminal abierta y visitar `http://127.0.0.1:8000/` en el navegador.
No hace falta Live Server: FastAPI sirve frontend y backend. Si ya está corriendo,
usar ese servidor. `Ctrl+C` lo detiene. `--reload` recarga el backend ante cambios
de código; para cambios en JS/CSS, recargar el navegador con `Ctrl+F5`.
Reiniciar el backend pierde las sesiones en memoria: recargar la página para
crear una nueva.

Prueba manual escrita sugerida (usa Gemini y puede consumir cuota):

1. Escribir «Quiero un Big Mac». Debe pedir tamaño y bebida y mantener vacío el carrito.
2. Responder «Grande con Coca». Debe aparecer una unidad y un total de $12.500.
3. Escribir «Confirmo el pedido». Debe aparecer el estado confirmado y bloquearse la escritura.

Esta es una guía de prueba para la autora, no evidencia de una prueba real nueva.
Los controles de micrófono y voz siguen parcialmente implementados; consultar
`estado-y-pruebas.md` antes de atribuirles nuevas capacidades.

## Revisar cambios y logs

En una segunda terminal PowerShell, desde la raíz:

```powershell
git status --short
git log -5 --oneline
git show --stat HEAD
git show HEAD
```

`status` muestra trabajo pendiente; `log`, commits recientes; `show`, el último
cambio. Si Git abre un visor paginado, salir con `q`.

Para ver eventos del bot mientras se prueba:

```powershell
Get-Content .\logs\runtime.log -Tail 30 -Wait
```

Detener esa lectura con `Ctrl+C`. No copiar claves ni conversaciones privadas
al compartir diagnósticos.
