# Reglas de trabajo del proyecto

## Objetivo y alcance

Construir un autoservicio conversacional de pedidos por voz, con escritura
alternativa y actualización visual del pedido. El proyecto también debe poder
explicarse y defenderse técnicamente por su autora. Consultar `docs/README.md`
antes de modificar comportamiento o arquitectura.

## Documentación obligatoria

- Toda función Python nueva o modificada debe tener docstring de estilo Google,
  en español, con descripción y secciones `Args`, `Returns` y `Raises` cuando
  correspondan. Documentar efectos sobre el estado si existen.
- Conservar y actualizar los docstrings existentes. Hay deuda previa identificada
  en `Cart.total`, `Menu.get_product` y `load_menu`; no usarla como precedente.
- En JavaScript, documentar funciones nuevas o modificadas mediante comentarios
  JSDoc con propósito, parámetros, retorno y efectos relevantes; es la adaptación
  de la misma exigencia de documentación al lenguaje.
- Todo cambio de comportamiento, contratos, módulos o configuración debe incluir
  la actualización de los documentos afectados en `docs/` y, si corresponde,
  del README. Registrar validación y pendientes en `docs/estado-y-pruebas.md`.
- Registrar decisiones de arquitectura con contexto, alternativas, motivos,
  consecuencias y estado en `docs/decisiones.md`. Diferenciar intención expresada
  por la autora, comportamiento comprobado e interpretación de decisiones previas.
- Explicar los cambios en español, conectando el problema, la solución y sus
  límites. No presentar propuestas como implementaciones ni pruebas simuladas
  como verificaciones reales de Gemini.

## Commits y seguimiento de cada etapa

- Cada cambio coherente debe quedar acompañado de su commit local, después de
  revisar el diff y ejecutar las verificaciones apropiadas. El mensaje debe ser
  una oración breve en español que explique qué cambia y/o por qué se necesita.
- Incluir código y documentación correspondiente en el mismo commit. Separar
  cambios con objetivos distintos; no incluir modificaciones ajenas por accidente.
- Informar al finalizar los identificadores de los commits y qué se verificó.
  Un commit local no implica publicar los cambios mediante push.
- Antes de cada etapa, explicar qué se hará y para qué. Durante el trabajo,
  comunicar hallazgos y resultados de pruebas de forma comprensible.
- Entregar comandos exactos para PowerShell en la terminal integrada de VS Code,
  indicando directorio, URL del frontend, acciones de prueba y resultados esperados.
  Si el cambio no tiene efecto visual, explicar cómo verificarlo por terminal.
- Al dar comandos para ejecutar Python o levantar el bot, incluir primero la
  activación del entorno en PowerShell: `.\.venv\Scripts\Activate.ps1` desde
  la raíz del proyecto. Recordar que se activa en cada terminal nueva.
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
