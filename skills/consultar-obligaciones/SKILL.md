---
name: consultar-obligaciones
description: Responde consultas sobre las obligaciones de compliance de las RCAs chilenas ya procesadas, por tema o por cualquier palabra o frase (por ejemplo "¿qué obligaciones hay sobre humedales?", "busca glaciares en Queltehue", "busca 'pajonal' en la UF de Arqueros"). Separa coincidencia literal, relación temática (a revisar) y mención sin obligación, siempre con su alcance. Úsala cuando el usuario pregunte qué obligaciones hay sobre un tema, término, componente o lugar, o pida agregar o quitar términos de config/temas.yaml.
---

# Consultar las obligaciones por tema o palabra

Respondes preguntas del tipo "¿qué obligaciones hay relacionadas con X?" sobre las RCAs **ya procesadas** (las que tienen `salida/obligaciones/<archivo>.json`). Sigues la sección 5.4 de ESPECIFICACION.md y el plan de la Etapa 6 (§12.1). El resultado es apoyo para un abogado: nunca reemplaza su revisión.

## Reglas que no se negocian

1. **La búsqueda exacta la hace el código, no tú.** Toda coincidencia literal y toda mención sale de `scripts/buscar_palabras.py consultar`. Nunca afirmes que un término aparece o no aparece en una RCA sin haber ejecutado el script.
2. **Tres categorías, siempre separadas:**
   - **Coincidencia literal**: el término (o un sinónimo del tema) está en una cita de la obligación, es decir, en texto del PDF. Es exacta y verificable.
   - **Relación temática (revisar)**: interpretación. Nunca la presentes como hecho.
   - **Mención sin obligación**: el término está en la RCA, pero fuera de toda cita de obligación (por ejemplo, en la descripción del proyecto o la evaluación).
3. **El alcance va siempre**, también, y sobre todo, cuando no hay resultados: cuántas RCAs y obligaciones se buscaron, qué páginas no tienen texto o no se leyeron, el OCR previo y si la relación temática ya está revisada. "No hay resultados" sin alcance está prohibido.
4. **No inventes relaciones.** Con un término libre solo propones una relación con el criterio aprobado (más abajo) y con palabras del PDF que el código pueda comprobar. Si dudas, no la propongas.
5. **No modificas obligaciones ni fichas.** Las relaciones que propones para un término libre viven solo en el resultado de esa consulta (`salida/consultas/`), nunca en `salida/obligaciones/` (decisión de Ignacio, 2026-11-23).
6. **No procesas RCAs.** Si una RCA del manifiesto no tiene obligaciones extraídas, lo dices y sigues con las demás: procesarla corresponde a las skills fichar-rca y extraer-obligaciones (dos pasos, una RCA por sesión; ver README).
7. **No emites opinión jurídica** ni evalúas cumplimiento: solo encuentras y ordenas.

## Rutas (dónde están los scripts y la configuración)

Los comandos de esta skill se escriben como si la carpeta de trabajo fuera la **raíz del asistente**: la carpeta que contiene `scripts/`, `config/` y `skills/`. Antes del primer comando, ubícala así (sin variables propias de plugins):

1. Si la carpeta de trabajo tiene `scripts/buscar_palabras.py` y `config/temas.yaml`, esa es la raíz. Es el caso de este proyecto, donde la skill está disponible como skill del proyecto (`.claude/skills/<nombre>` es un enlace a `skills/<nombre>`). Los comandos de abajo funcionan tal cual.
2. Si no, la raíz está dos niveles arriba de la carpeta de esta skill (`<carpeta de la skill>/../..`), que es lo que ocurre cuando la skill viene de un plugin instalado. Obtén su ruta absoluta resolviendo los enlaces: `cd -P "<carpeta de la skill>" && cd ../.. && pwd`. Después, en cada comando, antepón esa ruta a `scripts/`, a `config/` y al Python (`"<raíz>/.venv/bin/python" "<raíz>/scripts/..."`). Los datos del usuario (`rcas/`, `salida/`, el manifiesto) siguen siendo relativos a la carpeta de trabajo. Los scripts encuentran solos `config/` y las plantillas, porque los ubican desde su propia carpeta.
3. Si no encuentras la raíz, detente y dilo. Si no existe `<raíz>/.venv` (falta el entorno de Python, por ejemplo después de instalar el plugin desde GitHub), explica que hay que prepararlo una vez y **ofrece hacerlo; solo con el OK del usuario** ejecuta:
   - Mac o Linux: `python3 -m venv "<raíz>/.venv" && "<raíz>/.venv/bin/python" -m pip install -r "<raíz>/requirements.txt"`
   - Windows: `py -3 -m venv "<raíz>\.venv"` y luego `"<raíz>\.venv\Scripts\python" -m pip install -r "<raíz>\requirements.txt"`
   Si no hay Python 3 instalado, dilo y remite al README (sección Requisitos). Después confirma que el entorno funciona ejecutando `"<raíz>/.venv/bin/python" -c "import pymupdf, openpyxl, yaml"`.

Python: `.venv/bin/python` (en Windows, `.venv\Scripts\python`), dentro de la raíz.

**Respaldo antes de modificar salida/.** Antes de escribir o corregir un archivo existente en `salida/obligaciones/`, `salida/fichas/`, `salida/consultas/relaciones_aprobadas/` o `salida/verificacion/` (también si lo haces con un script de Python), ejecuta `.venv/bin/python scripts/respaldar_salida.py --motivo "<motivo breve>"` y di dónde quedó el respaldo. Muestra el cambio y espera el OK de Ignacio antes de aplicarlo. Trabaja una sola RCA por sesión cuando fiches, extraigas o corrijas.

## Pasos

### 1. Entender la consulta

Identifica en la pregunta:
- **Qué buscar**: un tema de `config/temas.yaml` (humedales, recursos_hidricos, pueblos_indigenas, patrimonio_cultural, flora_y_fauna, areas_protegidas, glaciares; también en singular o con espacios, como "recursos hídricos") o un **término libre** (cualquier otra palabra o frase). Si la palabra es uno de los términos de un tema (por ejemplo "bofedal"), el script la busca sola y avisa que existe el tema; transmite ese aviso y ofrece consultar el tema completo.
- **Dónde** (opcional):
  - una RCA ("en Queltehue", "en la RCA 151/2013"): busca su archivo con `ls salida/obligaciones/` y usa `--archivo <nombre>.pdf`;
  - una unidad fiscalizable ("en la UF Planta Cloruro de Litio"): usa `--uf "<nombre o parte>"`.
  Si la pregunta es ambigua (dos RCAs posibles), pregunta antes de buscar.

Manifiesto: **no pases `--manifiesto`** salvo que el usuario indique otro. El script usa `manifiesto.csv` y, si no existe, `ejemplos/manifiesto_ejemplo.csv`, con un `AVISO` que debes repetir en la respuesta ("se usó el manifiesto de ejemplo"). Si no hay ninguno, el script responde `ERROR` y no guarda la consulta: dilo y no reintentes sin manifiesto. El JSON de la consulta registra el manifiesto usado en `filtro.manifiesto`. (Regla agregada el 2026-11-24, después de una consulta que corrió con un `manifiesto.csv` inexistente y dejó todo como "SIN UF ASIGNADA".)

### 2. Ejecutar la búsqueda exacta

```bash
.venv/bin/python scripts/buscar_palabras.py consultar "<consulta>" [--archivo X.pdf] [--uf "<UF>"]
```

El script imprime el alcance, los avisos y las tres categorías, y guarda la consulta en `salida/consultas/consulta_<termino>_<AAAAMMDD-HHMMSS>.json` y `.csv`. **La consulta no toca el Excel**: entra en la hoja Consulta solo si el usuario lo pide (paso 5). Si responde `ERROR` (UF inexistente o ambigua), muestra el mensaje y la lista de unidades que trae, y pregunta.

**Si la consulta es un tema de temas.yaml**, la relación temática ya viene de `temas_relacionados` (anotada y revisada en la Etapa 5). No agregues relaciones nuevas: pasa al paso 4.

### 3. Solo con un término libre: proponer la relación temática

Un término libre no tiene relación temática anotada. La propones en el momento con el **criterio aprobado por Ignacio en la Etapa 5**:

> Hay relación solo si el PDF nombra **con otras palabras** el objeto que la obligación protege o mide (por ejemplo, "SVAHT" o "pajonal hídrico" por humedal, "nivel freático" por napa, "Colla" por indígena). No basta con que la obligación ocurra cerca del objeto, en la misma página o en el mismo sector.
>
> Precisión aprobada por Ignacio (2026-11-23, Etapa 6): una medida que la RCA establece **expresamente por el impacto sobre el objeto consultado** también cuenta como relación, aunque proteja o mida otra unidad. La justificación lo dice ("…pero protege otras unidades (…), no el <objeto> perdido") e indica qué medida es (por ejemplo, "es la medida 3 de esa lista"). Las palabras_pdf son las que vinculan la medida con ese impacto. Caso: Arqueros OBL-060 a 063, establecidas «por la pérdida del pajonal hídrico salino (1,1 ha)» (p. 159), que protegen las unidades UC09 y UC10. Si la vinculación de una fila con el impacto no es explícita en su propio texto (por ejemplo, una medida al final de la lista o un seguimiento que empieza en otra página), se marca `"dudosa": true` con una `"nota"` que diga qué debe confirmar el abogado.

**Relaciones ya aprobadas.** Si existe `salida/consultas/relaciones_aprobadas/<termino>.json` (por ejemplo `pajonal.json`), contiene las relaciones que Ignacio ya aprobó para ese término libre. Úsalo como base: pásalo con `--relaciones` (o copia sus relaciones al JSON de la consulta y agrega solo las nuevas que encuentres) y dilo en la respuesta. No modifiques ese archivo ni quites la marca "dudosa" sin el OK de Ignacio; las relaciones nuevas que propongas se muestran aparte, como propuestas a aprobar.

Cómo buscar candidatas sin leer las RCAs completas:
1. Piensa en las formas en que una RCA nombra el objeto del término (sinónimos técnicos, siglas, nombres locales). Busca cada una con el mismo script, por separado, para obtener sus coincidencias literales en las citas:
   ```bash
   .venv/bin/python scripts/buscar_palabras.py --salida <carpeta temporal> consultar "<sinónimo>" [mismos filtros]
   ```
   Usa como `--salida` una copia temporal de `salida/` (texto, obligaciones y fichas, en el scratchpad) para que estas búsquedas auxiliares **no** queden en el historial de Ignacio.
2. Revisa también las obligaciones que el resultado del paso 2 lista en `obligaciones_en_la_pagina` de las menciones sin obligación.
3. Por cada candidata, lee su cita (y, si hace falta, la página con `scripts/mostrar_paginas.py`) y decide con el criterio. Descarta las que solo ocurren cerca.

Escribe las relaciones propuestas en un JSON en el scratchpad (no en `salida/obligaciones/`):

```json
{"relaciones": [
  {"archivo": "rca_151_2013_arqueros_atacama.pdf", "id_obligacion": "OBL-061",
   "palabras_pdf": "SVAHT", "pagina_pdf": 159,
   "justificacion": "La señalética se instala en los «SVAHT», sistemas vegetacionales azonales hídricos."}
]}
```

- `palabras_pdf`: las palabras **exactas** del PDF que motivan la relación (copiadas del texto de la página, no de la descripción).
- `pagina_pdf`: la página donde están esas palabras.
- `justificacion`: una frase que cita entre « » esas palabras.
- Opcional `"dudosa": true` si la relación es discutible; se muestra como "(dudosa)".
- Opcional `"nota"`: qué falta confirmar (se muestra entre [ ] al final de la justificación).

Vuelve a ejecutar la consulta del paso 2 (la misma, con los mismos filtros) agregando `--relaciones <ruta del JSON>`. El código acepta como "revisar" solo las relaciones cuyas palabras están en el texto de su página; las demás las rechaza con su motivo (`RELACIÓN RECHAZADA`). **Nunca reintentes una relación rechazada cambiando las palabras para que calcen**: si las palabras no están, la relación no se sostiene. Corrige solo errores de copia evidentes (por ejemplo, la página equivocada, cuando el motivo dice en qué página están), y explica el cambio. Las páginas sin texto (escaneadas) no se pueden comprobar: no propongas relaciones con palabras de esas páginas; menciónalo como límite.

Esta segunda ejecución es la consulta que queda guardada con sus relaciones. La primera también queda guardada en `salida/consultas/`, sin relaciones; dilo para que Ignacio no la confunda. Si después pide agregar la consulta al Excel, agrega solo la segunda.

### 4. Responder

Responde en español de Chile, con este orden:

1. **Qué se buscó**: el tema y sus términos, o el término libre; el filtro (RCA o UF), si lo hubo, y el manifiesto usado.
2. **Alcance**: las líneas de alcance del script, en palabras simples (RCAs, obligaciones buscadas, páginas sin texto o no leídas, OCR previo, si la relación temática está revisada). Si alguna RCA del manifiesto no tiene obligaciones extraídas, dilo.
3. **Coincidencia literal**: tabla con UF, proyecto, **ID visible** (columna `id_visible`, por ejemplo ARQ-024; nunca muestres solo el ID interno OBL-024 si hay prefijo), descripción breve, plazo o frecuencia, responsable, página y término encontrado (y dónde: cita principal o adicional). Si hay posibles duplicados (`duplicado_de` distinto de "—"), indícalo.
4. **Relación temática (revisar)**: tabla con las mismas columnas y la justificación con su página, marcando "(dudosa)" y "(propuesta en esta consulta)" cuando corresponda. Si hubo relaciones rechazadas, lístalas con su motivo.
5. **Mención sin obligación**: por RCA, las páginas donde aparece el término y un contexto breve de las más relevantes (el CSV tiene todos). No las presentes como obligaciones.
6. Si no hay resultados en ninguna categoría: "No hay resultados para «X»", seguido del alcance. Si las páginas sin texto o no leídas podrían contener el término, dilo.
7. Las rutas del CSV y del JSON de la consulta.
8. Cierra con: "Herramienta de apoyo. Requiere revisión de un abogado."
9. Después del cierre, una sola línea: "Si quieres, la agrego a la hoja Consulta del Excel." **No regeneres el Excel por tu cuenta** (decisión de Ignacio, 2026-11-24).

### 5. Solo si el usuario responde que sí: agregar la consulta al Excel

```bash
.venv/bin/python scripts/exportar_excel.py --agregar-consulta salida/consultas/<consulta>.json
```

(Mismo `--manifiesto` y `--rcas` que el Excel de siempre: `manifiesto.csv` y `rcas/`, o `ejemplos/manifiesto_ejemplo.csv` y `ejemplos/rcas_publicas` si no existe `manifiesto.csv`.)

- El script regenera el Excel completo y marca la consulta con `"en_excel": true` en su JSON: desde entonces queda en el historial de la hoja Consulta. Solo entran las consultas que el usuario pidió agregar.
- Si responde `AVISO: … está abierto en Excel` (código 3), no se cambió nada: dile que cierre el archivo y ofrece repetirlo. No reintentes por tu cuenta.
- Si dice que no, o no responde, la consulta queda solo en el chat y en `salida/consultas/`.

Si la lista es larga (más de unas 20 filas por categoría), muestra las primeras y remite al CSV, indicando el total.

## Ver una obligación por su ID

Si el usuario pide una obligación por su ID ("muéstrame ARQ-024", "qué dice OBL-024 de Albemarle"), ejecuta:

```bash
.venv/bin/python scripts/buscar_palabras.py obligacion "<ID>"
```

Acepta el ID visible (prefijo de la RCA, columna `prefijo_id` del manifiesto; también "arq 24") o el interno (OBL-024: si existe en varias RCAs, muestra todas y pregunta cuál). Muestra todos los campos, la página y la cita, sin resumir la cita.

## Registrar la revisión humana de un abogado

Las revisiones (confirmada, corregida o descartada) se registran con `scripts/registrar_revision.py` en `salida/revision/revision_humana.csv`, nunca en `salida/obligaciones/`. Flujo:
1. Si Ignacio quiere auditar filas, crea la planilla: `.venv/bin/python scripts/registrar_revision.py planilla --ids "ARQ-024 ALB-002..027" --nombre <nombre>` (o `--muestra <CSV de la muestra>`). Dile la ruta: la llena en Excel o Numbers (columnas resultado, comentario, revisado_por y fecha_revision) y la guarda como CSV.
2. Cuando diga "importa mi revisión", ejecuta primero sin `--aplicar` y muéstrale el resumen y los errores. Si hay errores, no se registra nada.
3. Solo con su OK, repite con `--aplicar` (el script respalda `salida/` antes de registrar).
4. Si Ignacio declara el resultado en el chat ("revisé ARQ-024: todo ok"), llena tú la planilla con lo que dijo, usando sus palabras en el comentario y `revisado_por` "Ignacio", y sigue los pasos 2 y 3.
Una fila "corregida" registra que hubo corrección; la corrección del dato sigue la regla de siempre: mostrar, esperar el OK, respaldar y aplicar.

## Agregar o quitar términos de config/temas.yaml

Solo a pedido del usuario, y **solo después de mostrarle el cambio y recibir su OK**:
1. Muestra el cambio exacto (tema, término que entra o sale) y su efecto: ejecuta la consulta del tema sobre una copia temporal de `salida/` con un `temas.yaml` temporal (`--temas <ruta>`) y compara con el resultado actual: qué obligaciones pasarían a literal y cuáles dejarían de serlo.
2. Advierte que una obligación que pasa a literal debe perder la relación temática del mismo tema (validar_obligaciones.py lo marca como error) y que eso exige editar `salida/obligaciones/`, con respaldo previo y aprobación de Ignacio.
3. Con el OK, edita `config/temas.yaml` respetando su formato (nombre de tema sin tildes ni espacios; un término por línea con "  - "), deja una línea de comentario con la decisión y la fecha, y ejecuta `.venv/bin/python -m pytest tests/test_buscar_palabras.py -q`.
4. Registra la decisión en ESPECIFICACION.md §12.1.
