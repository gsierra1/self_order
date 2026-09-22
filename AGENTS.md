# Reglas de trabajo del proyecto

## Objetivo y alcance

Consultar `docs/README.md` y la documentación relacionada únicamente cuando el
cambio afecte comportamiento, contratos o arquitectura. Para cambios locales,
inspeccionar solo los archivos necesarios.

## Documentación obligatoria

- Toda función Python nueva o modificada debe tener docstring de estilo Google,
  en español, con descripción y secciones `Args`, `Returns` y `Raises` cuando
  correspondan. Documentar efectos sobre el estado si existen.
- Conservar y actualizar los docstrings existentes.
- En JavaScript, documentar funciones nuevas o modificadas mediante comentarios
  JSDoc con propósito, parámetros, retorno y efectos relevantes.
- Actualizar `docs/` y `README.md` cuando el cambio altere comportamiento
  documentado, contratos, configuración, arquitectura o instrucciones de uso.
  No modificar documentación por cambios internos que no alteren lo documentado.
- `docs/arquitectura.md` es la fuente principal para documentar la arquitectura
  actual y justificar sus decisiones relevantes. Cuando una decisión
  arquitectónica nueva o modificada afecte el diseño, incorporar su motivo,
  alternativa relevante, consecuencia o límite en la sección correspondiente de
  `docs/arquitectura.md`, solo si esa explicación aporta valor para comprender el
  sistema.
- No crear ni mantener un registro separado de decisiones arquitectónicas ni un
  archivo `docs/decisiones.md`. Evitar duplicar en documentación la misma
  explicación bajo formatos distintos.
- La documentación debe describir el estado actual del proyecto. El historial de
  cambios pertenece a Git; no convertir `docs/arquitectura.md` en un changelog.
- Explicar los cambios en español, conectando el problema, la solución y sus
  límites. No presentar propuestas como implementaciones ni pruebas simuladas
  como verificaciones reales del funcionamiento del LLM o STT.
- Mantener la documentación impersonal: no incluir nombres de personas,
  destinatarios de demostraciones ni referencias a conversaciones privadas como
  justificación técnica.

## Commits y seguimiento de cada etapa

- No crear commits salvo solicitud explícita de la autora. Al finalizar una tarea,
  informar los archivos modificados y las verificaciones realizadas. Cuando se
  solicite un commit, revisar previamente el diff y ejecutar las verificaciones
  apropiadas.
- Incluir código y documentación correspondiente en el mismo commit. Separar
  cambios con objetivos distintos; no incluir modificaciones ajenas por accidente.
- Cuando se haya realizado un commit, informar su identificador y qué se verificó.
  Un commit local no implica publicar los cambios mediante push.
- Trabajar de forma concisa. Antes de realizar un cambio de alcance amplio o
  potencialmente riesgoso, explicar brevemente el plan. Para cambios locales,
  proceder directamente. Al finalizar, resumir qué cambió, qué se verificó y
  cualquier riesgo o pendiente.
- Cuando sea necesaria una verificación manual por parte de la autora,
  proporcionar los comandos exactos para PowerShell desde la raíz del proyecto,
  junto con las acciones y resultados esperados. Si requiere Python, indicar
  primero la activación del entorno con `.\.venv\Scripts\Activate.ps1`.
- Diferenciar pruebas automáticas, pruebas manuales con el proveedor real y
  pruebas con simulaciones. No dar por ejecutadas las pruebas propuestas a la
  autora.
- Al finalizar una tarea que haya modificado archivos, proponer una única oración
  breve en español como mensaje de commit. No crear el commit salvo solicitud
  explícita de la autora.

## Invariantes de producto

- `OrderService` es la autoridad sobre validación, precios y estado del pedido.
  Voz, texto, frontend y LLM deben utilizar esa misma lógica.
- Rechazar productos inexistentes o no disponibles. Preguntar por modificadores
  obligatorios faltantes; no elegirlos por el usuario ni agregar ítems
  incompletos.
- Separar transcripciones o selecciones provisionales del carrito validado.
- Preservar la línea original cuando falla un reemplazo.
- No repetir automáticamente mutaciones ante fallas de IA o reconexiones.
- No ampliar el menú ni rediseñar el frontend como efecto incidental de
  incorporar voz. Son etapas posteriores según la prioridad del proyecto.
- No exponer claves ni incorporar `.env`, conversaciones locales o audio de
  usuarios a documentación/versionado sin una necesidad explícita.

## Uso eficiente del contexto

- No recorrer todo el repositorio por defecto.
- Empezar por los archivos mencionados por la autora y sus dependencias directas.
- Usar `docs/arquitectura.md` como índice para localizar responsabilidades antes
  de explorar archivos adicionales.
- No leer documentos completos si solo se necesita una sección concreta.
- No ejecutar la suite completa cuando una prueba específica permita verificar el
  cambio, salvo cambios transversales o solicitud explícita.
- No volver a inspeccionar archivos cuyo contenido relevante ya esté disponible
  en el contexto, salvo que hayan cambiado.
- Ampliar la exploración solamente cuando aparezca evidencia de que el cambio
  afecta otros módulos.
- No realizar refactors, mejoras, limpieza de código, cambios visuales ni
  ampliaciones de alcance no solicitadas, salvo que sean imprescindibles para
  completar correctamente la tarea; en ese caso, explicarlo antes.
