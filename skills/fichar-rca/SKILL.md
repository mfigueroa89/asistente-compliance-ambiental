---
name: fichar-rca
description: Elabora la ficha estructurada de una Resolución de Calificación Ambiental (RCA) chilena ya leída por leer_pdf.py, con página, cita textual y fuente para cada dato, y "No consta" cuando el dato no está en el documento. Úsala cuando el usuario pida fichar, resumir en ficha o extraer los datos de identificación de una RCA.
---

# Fichar una RCA

Produces la ficha de **una** RCA en `salida/fichas/<archivo>.json`, siguiendo `plantilla_ficha.json` (en esta misma carpeta) y la sección 7 de ESPECIFICACION.md. El resultado es apoyo para un abogado: nunca reemplaza su revisión.

## Reglas que no se negocian

1. **Solo lo que dice el documento.** Si un dato no aparece, el valor es `"No consta"`, con `pagina_pdf` y `cita_textual` en `null`. No completes de memoria, no deduzcas, no uses conocimiento general sobre el proyecto o el titular.
2. **Cada dato lleva su respaldo:** `valor`, `pagina_pdf` (número real de la página del PDF, no el impreso), `cita_textual` (copia literal de unas 40 palabras como máximo) y `fuente`.
3. **Fuente:**
   - `"texto"`: copiaste la cita del texto digital de la página.
   - `"ocr_previo"`: la página está marcada "OCR PREVIO". Copia la cita **tal como aparece en el texto**, con sus errores de OCR; no la corrijas. Si el valor correcto se lee distinto en la imagen, escribe en `valor` lo que ves en la imagen y deja una observación.
   - `"imagen"`: el dato solo se ve en la imagen de la página (por ejemplo, el número de resolución de las RCAs firmadas electrónicamente, cuyo texto dice `<NUM_RES>`). Transcribe exactamente lo que ves.
4. **Listas** (`region`, `provincia`, `comuna`, `fases`, `componentes_ambientales_relevantes`, `efectos_articulo_11`, `permisos_ambientales_sectoriales`, `areas_protegidas_o_sensibles`): un elemento por cada dato, **cada uno con su página y cita**. Si no hay ninguno, la lista queda vacía `[]`.
5. **No interpretes.** Distingue lo que la resolución establece de lo que tú podrías inferir. Si algo es dudoso, déjalo en `observaciones_generales` en vez de ponerlo como dato.
6. **No leas la RCA completa.** Lee las páginas que propone el localizador y amplía solo con búsquedas exactas por código (paso 4). Esto debe funcionar igual con RCAs de 300 a 500 páginas.
7. **Datos personales:** la ficha no registra al representante legal (no hace falta para compliance y es dato personal); solo el titular. Nunca copies nombres de personas naturales, RUT, domicilios, teléfonos ni correos en la ficha.

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

`<archivo>` es el nombre del PDF sin extensión.

## Pasos

### 1. Preparar el texto y el mapa de secciones

**Procesamiento incremental:** si ya existe `salida/fichas/<archivo>.json` y su `sha256` es igual al del JSON de texto (es decir, al del PDF actual), no vuelvas a fichar: avisa que la ficha ya existe y sigue, salvo que el usuario pida rehacerla. Si el `sha256` es distinto, el PDF cambió: vuelve a fichar y avísalo.

Si no existen, genéralos:

```bash
.venv/bin/python scripts/leer_pdf.py rcas/<archivo>.pdf
.venv/bin/python scripts/localizar_secciones.py salida/texto/<archivo>.json
```

Lee el resumen del localizador: qué secciones ubicó, con qué confianza y qué avisos dio. Anota los avisos: los usarás en `observaciones_generales`.

- Una sección con confianza **media** se ubicó por un subtítulo o por un considerando sin "Que" recuperado por un hueco en la numeración (`"metodo": "considerando_sin_que"`): confirma leyendo esa página que de verdad empieza ahí antes de citarla.
- La sección `otros_tramite` (considerandos de reportes y avisos a la SMA, responsabilidad del titular, cambios de consideración) no aporta campos a la ficha: es para la extracción de obligaciones.
- `considerandos_excluidos` lista la cláusula estándar de seguimiento, que no pertenece a ninguna sección.
- Un tramo con `"aislado": true` (una página lejos del bloque principal, confianza baja) no forma parte del rango de la sección: no lo uses para `rango_localizador`.

### 2. Leer las páginas para la ficha

```bash
.venv/bin/python scripts/mostrar_paginas.py salida/texto/<archivo>.json --localizador ficha
```

Si son más de unas 40 páginas, léelas por partes con `--paginas` (por ejemplo `--paginas 1-20` y luego `--paginas 21-40`). Cada página aparece con su número real del PDF: es el que va en `pagina_pdf`.

### 3. Mirar las imágenes

Para cada página marcada `LECTURA VISUAL` entre las leídas (como mínimo la página 1), abre la imagen indicada (`salida/imagenes/<archivo>/pagina_N.png`) y lee los datos que el texto no trae, en especial número y fecha de la resolución. Si la imagen no se generó o es ilegible, dilo en `observaciones_generales`.

### 4. Ampliar con búsquedas exactas, sin adivinar

Para cada campo que no encontraste en las páginas leídas, busca por código y lee solo las páginas que aparezcan:

```bash
.venv/bin/python scripts/mostrar_paginas.py salida/texto/<archivo>.json --buscar "vida útil" --buscar "años"
.venv/bin/python scripts/mostrar_paginas.py salida/texto/<archivo>.json --paginas 4-6
```

Términos sugeridos por campo:

| Campo | Buscar |
|---|---|
| numero_expediente_o_codigo | "código", "expediente", "ID" |
| titular | "titular", "razón social" |
| reglamento_aplicable | "D.S. N", "Decreto Supremo N", "Reglamento del Sistema" (normalmente en los VISTOS, p. 1) |
| region, provincia, comuna | "comuna", "provincia", "región" |
| tipologia | "artículo 3", "literal", "tipología" |
| monto_inversion | "monto", "inversión", "US$", "MMUS" |
| vida_util | "vida útil" |
| superficie_o_dimensiones | "superficie", "hectáreas", "há", "MW" |
| pueblos_indigenas | "indígena", "GHPPI", "consulta" |
| permisos_ambientales_sectoriales | "permiso ambiental sectorial", "PAS", "artículo 1" (ej.: artículo 138) |
| areas_protegidas_o_sensibles | "área protegida", "sitio prioritario", "humedal", "glaciar" |
| hay_condiciones_exigencias | "condiciones o exigencias", "artículo 25" |
| hay_compromisos_voluntarios | "compromisos ambientales voluntarios", "compromiso voluntario" |
| hay_plan_contingencias | "contingencia", "emergencia" |

Si una sección no fue ubicada por el localizador, usa su propuesta (las páginas donde solo se menciona). **No des por cierta ninguna hipótesis sobre cómo está redactada una RCA**: confírmala leyendo el texto. Si después de ampliar el dato sigue sin aparecer, el valor es `"No consta"` y en `observaciones_generales` anotas qué secciones y páginas revisaste.

### 5. Llenar la ficha

Copia `plantilla_ficha.json` y completa:

- `archivo` y `sha256`: los del JSON de texto. `fecha_elaboracion`: hoy (AAAA-MM-DD). `paginas_leidas`: todas las páginas que efectivamente leíste.
- `fecha_resolucion`: formato `AAAA-MM-DD`; la cita conserva la fecha como aparece.
- `reglamento_aplicable`: el Reglamento del SEIA que cita la RCA (normalmente en los VISTOS). En `valor` va **exactamente** uno de los `nombre` de `config/equivalencias_articulo_11.yaml` (hoy: `"D.S. N° 40/2012, Ministerio del Medio Ambiente"` o `"D.S. N° 95/2001, Ministerio Secretaría General de la Presidencia"`), con la página y la cita donde la RCA lo nombra. Si la RCA no lo identifica, `"No consta"` (el validador solo advierte). Si cita otro reglamento, escríbelo tal cual y déjalo en observaciones.
- `tipo_instrumento`: `"DIA"` o `"EIA"`. `decision`: `"favorable"` o `"desfavorable"` (según el RESUELVO).
- `monto_inversion`, `vida_util`, `superficie_o_dimensiones`: cifra y unidad tal como aparecen (ej.: "US$ 150 millones").
- `tipologia`: el literal del artículo 3 del Reglamento del SEIA, si consta.
- `descripcion_breve`: dos o tres frases fieles al documento, sin agregar nada; la cita respalda la frase principal.
- `efectos_articulo_11`: un elemento por cada letra o efecto que la resolución **reconoce o descarta**; en `valor`, solo lo que dice el documento: la letra si la nombra, o el título que le da la RCA, y si se reconoce o se descarta (ej.: "Letra b), recursos naturales renovables: descartado"). Cada elemento lleva además `letra_equivalente`, tomado de la tabla **del reglamento aplicable** en `config/equivalencias_articulo_11.yaml` (la numeración cambia entre reglamentos): `{"valor": "letra c) (artículo 7 del D.S. N° 40/2012, Ministerio del Medio Ambiente)", "pagina_pdf": null, "cita_textual": null, "fuente": "equivalencia_legal"}`. Elígelo según la letra o el artículo del Reglamento que **mencione el propio efecto** (en su valor o su cita); si no menciona ninguno, `letra_equivalente` queda en `"No consta"` con fuente `null`. Es conocimiento jurídico agregado, no un dato del documento: dilo en `observaciones_generales`.
- `hay_medidas_mitigacion`, `hay_medidas_reparacion`, `hay_medidas_compensacion`, `hay_plan_seguimiento`: `"sí"` si la RCA las establece; `"no"` solo si la RCA dice expresamente que no hay (con su cita); si no se pronuncia, `"No consta"`.
- `areas_protegidas_o_sensibles`: cada elemento lleva además `categoria`: `"área protegida"`, `"sitio prioritario"`, `"humedal"`, `"zona de interés turístico"` u `"otra"`. No llames "protegido" a nada que el texto no declare protegido: si la RCA solo describe una formación (por ejemplo, humedales o bofedales en la línea de base), dilo así en el `valor`.
- `hay_condiciones_exigencias`, `hay_compromisos_voluntarios`, `hay_plan_contingencias`: misma regla (`"sí"`, `"no"` con cita expresa, o `"No consta"`). **Lee siempre la página de inicio** de cada sección que ubicó el localizador (`condiciones_exigencias`, `compromisos_voluntarios`, `contingencias`) y cita el encabezado. Cada uno lleva además `rango_localizador`: el rango de páginas que ubicó el localizador, escrito como él lo entrega (ej.: `"66-70"` o `"5-9, 20"`), o `"No ubicada"` si no la ubicó. Si el "sí" sale de una mención aislada fuera de una sección propia, dilo en el `valor` (ej.: "sí: mención aislada dentro de medidas, sin sección propia") (el validador acepta "sí: <nota>" y "no: <nota>"). Si no la ubicó, amplía con `--buscar` ("condiciones o exigencias", "compromisos ambientales voluntarios", "contingencia", "emergencia") antes de dejar `"No consta"`.
- `control.paginas_revisadas_en_imagen`: las páginas cuya imagen revisaste contra el texto. En PDFs con OCR, revisa en la imagen al menos las páginas de donde sacas números, fechas y siglas. Si el OCR leyó mal un número o una sigla, el `valor` sigue a la imagen, la cita conserva el texto del OCR y el dato lleva `"correccion_ocr": "el OCR dice \"51 O ha\"; la imagen dice \"510 ha\""`.
- `control.paginas_no_leidas`: cada página que no pudiste leer (escaneada sin texto que no leíste, o ilegible), con `{"pagina": N, "seccion": "medidas (pp. 51-53)", "motivo": "..."}`. Si está dentro de una sección de obligaciones, dilo en el motivo: la Etapa 4 debe leerla con visión.
- `control`: `paginas_totales` y `paginas_escaneadas` según el JSON de texto; `paginas_ocr_previo`: cantidad de páginas con OCR previo; `campos_no_consta`: exactamente los campos que quedaron en "No consta" o con lista vacía; `observaciones_generales`: límites del documento (páginas ilegibles, OCR, secciones no ubicadas, datos dudosos).

Guarda el resultado en `salida/fichas/<archivo>.json` (UTF-8).

### 6. Validar y corregir

```bash
.venv/bin/python scripts/validar_ficha.py salida/fichas/<archivo>.json salida/texto/<archivo>.json
```

El validador toma el mapa del localizador de `salida/secciones/<archivo>.json` para comprobar `rango_localizador`.

- Corrige todos los **ERRORES** y vuelve a validar hasta que diga "Ficha válida.". Una cita "no encontrada" se corrige copiando el texto exacto de la página, nunca cambiando la página a ciegas.
- Las **advertencias** no se ocultan: datos leídos en imagen, citas aproximadas por OCR y citas en otra página se informan al usuario.

### 7. Entregar

Muestra la ficha al usuario en una tabla con las columnas **campo, valor, página, cita, fuente**, seguida de las advertencias del validador y de las observaciones generales. Termina con: "Herramienta de apoyo. Requiere revisión de un abogado."
