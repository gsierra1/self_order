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
  JSDoc con propósito, parámetros, retorno y efectos relevantes; es la adaptación
  de la misma exigencia de documentación al lenguaje.
- Actualizar docs/ y README cuando el cambio altere comportamiento documentado, 
  contratos, configuración, arquitectura o instrucciones de uso. No modificar 
  documentación por cambios internos que no alteren lo documentado.
- Registrar una decisión arquitectónica únicamente cuando se adopte una decisión 
  nueva o se cambie una existente.
- Explicar los cambios en español, conectando el problema, la solución y sus
  límites. No presentar propuestas como implementaciones ni pruebas simuladas
  como verificaciones reales del funcionamiento del LLM o STT.

## Commits y seguimiento de cada etapa

- Cada cambio coherente debe quedar acompañado de su commit local, después de
  revisar el diff y ejecutar las verificaciones apropiadas. El mensaje debe ser
  una oración breve en español que explique qué cambia y/o por qué se necesita.
- Incluir código y documentación correspondiente en el mismo commit. Separar
  cambios con objetivos distintos; no incluir modificaciones ajenas por accidente.
- Informar al finalizar los identificadores de los commits y qué se verificó.
  Un commit local no implica publicar los cambios mediante push.
- Trabajar de forma concisa. Antes de realizar un cambio de alcance amplio o 
  potencialmente riesgoso, explicar brevemente el plan. Para cambios locales, 
  proceder directamente. Al finalizar, resumir qué cambió, qué se verificó y 
  cualquier riesgo o pendiente.
- Entregar comandos exactos para PowerShell en la terminal integrada de VS Code,
  indicando directorio, URL del frontend, acciones de prueba y resultados esperados.
  Si el cambio no tiene efecto visual, explicar cómo verificarlo por terminal.
- Diferenciar pruebas automáticas, pruebas manuales con el proveedor real y
  pruebas con simulaciones. No dar por ejecutadas las pruebas propuestas a la autora.

## Invariantes de producto

- `OrderService` es la autoridad sobre validación, precios y estado del pedido.
  Voz, texto, frontend y LLM deben utilizar esa misma lógica.
- Rechazar productos inexistentes o no disponibles. Preguntar por modificadores
  obligatorios faltantes; no elegirlos por el usuario ni agregar ítems incompletos.
- Separar transcripciones o selecciones provisionales del carrito validado.
- Preservar la línea original cuando falla un reemplazo.
- No repetir automáticamente mutaciones ante fallas de IA o reconexiones.
- No ampliar el menú ni rediseñar el frontend como efecto incidental de incorporar
  voz. Son etapas posteriores según la prioridad expresada por la autora.
- No exponer claves ni incorporar `.env`, conversaciones locales o audio de
  usuarios a documentación/versionado sin una necesidad explícita.

## Uso eficiente del contexto

- No recorrer todo el repositorio por defecto.
- Empezar por los archivos mencionados por la autora y sus dependencias directas.
- Usar docs/arquitectura.md como índice para localizar responsabilidades antes 
  de explorar archivos adicionales.
- No leer documentos completos si solo se necesita una sección concreta.
- No ejecutar la suite completa cuando una prueba específica permita verificar el 
  cambio, salvo cambios transversales o solicitud explícita.
- No volver a inspeccionar archivos cuyo contenido relevante ya esté disponible en 
  el contexto, salvo que hayan cambiado.
- Ampliar la exploración solamente cuando aparezca evidencia de que el cambio afecta 
  otros módulos.