---
name: extraer-obligaciones
description: Extrae, una por una, las obligaciones de compliance que establece una Resolución de Calificación Ambiental (RCA) chilena ya procesada por leer_pdf.py y localizar_secciones.py, con tipo, fase, plazo, autoridad, página y cita textual. Úsala cuando el usuario pida extraer, listar o revisar las obligaciones, condiciones, compromisos o reportes de una RCA.
---

# Extraer las obligaciones de una RCA

Produces `salida/obligaciones/<archivo>.json` siguiendo `plantilla_obligaciones.json` (en esta carpeta) y la sección 8 de ESPECIFICACION.md. Es la parte central del asistente. El resultado es apoyo para un abogado: nunca reemplaza su revisión.

## Reglas que no se negocian

1. **Solo lo que establece el documento.** No deduzcas obligaciones que el texto no impone. No inventes plazos, responsables ni autoridades: si no constan, `"No consta"`.
2. **Una fila por obligación.** Si una medida exige además un reporte (por ejemplo, "capacitar" y "enviar informe a la SMA"), son **dos filas**: una para la medida y otra de tipo `"reporte o informe a la autoridad"`, unidas por el mismo `ubicacion_en_documento` (ej.: `"Compromiso 9.1.1"`).
3. **Posibles duplicados:** si la misma obligación aparece en dos secciones (por ejemplo, en un PAS y en las condiciones), **no las fusiones**: dos filas, cada una con su página y cita, y en `posible_duplicado` cada una nombra el ID de la otra. Explica la relación en `notas`.
4. **Cada obligación lleva respaldo:** `pagina_pdf` (número real del PDF), `pagina_impresa` (la que detectó leer_pdf.py, o `"No consta"`), `cita_textual` (copia literal, unas 40 palabras como máximo) y `fuente` (`"texto"`, `"imagen"` u `"ocr_previo"`, con las mismas reglas que la ficha; en OCR, la cita se copia con sus errores y, si un número se lee distinto en la imagen, el dato sigue a la imagen y se agrega `correccion_ocr`).
   **Cada dato relevante de la descripción, el plazo, el hito o el parámetro debe estar respaldado por una cita.** Si un dato está en otra oración o en otra página que la cita principal, agrega esa cita en `citas_adicionales` (`[{"pagina_pdf": N, "cita_textual": "..."}]`, también en filas no agrupadas) y, si son varias páginas, `paginas_respaldo` (ej.: `"77-78"`). Antes de cerrar cada fila, relee la descripción y comprueba que cada dato (cantidades, distancias, objetos, plazos) aparezca en alguna de sus citas; lo que no tenga cita se quita o se cita.
5. **Confianza:** `"alta"` si el texto impone el deber de forma expresa (deberá, se implementará, se enviará, con objeto claro); `"media"` si el deber es claro pero algún elemento queda implícito (por ejemplo, el responsable); `"baja"` si es dudoso si es una obligación. En caso de duda, baja, con una nota que explique por qué.
6. **No interpretes ni evalúes cumplimiento.** Describe la obligación con las palabras del documento, sin agregar.
7. **Temas:** `temas_literales` queda como lista vacía `[]`: la coincidencia literal la calcula `scripts/buscar_palabras.py` sobre las citas. `temas_relacionados` se completa después de la extracción, por RCA, con el criterio de ESPECIFICACION.md §12.1 (Etapa 5): solo si el PDF nombra con otras palabras el objeto que la obligación protege o mide. Cada elemento: `{"tema", "justificacion", "palabras_pdf", "pagina_pdf", "estado": "revisar"}`, donde la justificación es una frase que cita entre « » las palabras del PDF. Al terminar una RCA se agrega `"temas_relacionados_revisados": {"temas", "fecha", "criterio"}` y se valida con `validar_obligaciones.py`.

## Qué es una obligación (y qué no)

Sí: condiciones o exigencias; compromisos ambientales voluntarios; medidas de mitigación, reparación y compensación; planes de seguimiento y monitoreo (cada monitoreo con su frecuencia); reportes, informes o avisos a la autoridad (SMA, SEA u otros servicios); planes de contingencia o emergencia (por cada riesgo: las medidas preventivas y de control sin plazo propio pueden ir en una fila con `"agrupada": true`, pero entonces lleva **una cita por cada medida**: la cita principal más `citas_adicionales` (`[{"pagina_pdf": N, "cita_textual": "..."}]`) y `paginas_respaldo` con el rango que las cubre, ej. `"85-86"`; una sola cita no basta para un grupo. Cada medida con frecuencia o parámetro y cada aviso o reporte va en su propia fila); deberes explícitos de los permisos sectoriales ("el titular deberá presentar sectorialmente…"); formas concretas de cumplimiento o de reporte que la RCA fija para la normativa aplicable (informes, registros, plazos); deberes de trámite del titular (informar el inicio de fases a la SMA, comunicar cambios de titularidad, etc.).

Cómo distinguir dos tipos parecidos:
- `"reporte o informe a la autoridad"`: solo informes periódicos (mensuales, semestrales, anuales, después de cada campaña) o por evento (emergencias, hallazgos, incidentes, impactos no previstos), incluido el deber general de entregar el seguimiento a la SMA.
- `"trámite o aprobación ante la autoridad"`: presentar, someter o solicitar algo para aprobación, validación, visación o registro (planes, programas, umbrales, TDR, especificaciones, permisos); proponer equipos o ubicaciones a la SMA; inscribirse en un registro; informar el inicio de fases o de la ejecución; comunicar cambios de titularidad, representante o domicilio; someter modificaciones al SEIA.
- Si la obligación nace de un PAS o de la normativa aplicable, se mantiene `"condición de PAS"` o `"forma de cumplimiento de normativa"` aunque sea un trámite.

No: la descripción del proyecto; la descripción de un permiso o de sus requisitos legales; la simple cita de una norma sin una forma de cumplimiento fijada en la RCA; antecedentes de la evaluación; obligaciones de la autoridad (salvo para registrar a quién se reporta).

## Tipos y fases permitidos

- `tipo`: condición o exigencia · compromiso ambiental voluntario · medida de mitigación · medida de reparación · medida de compensación · plan de seguimiento o monitoreo · reporte o informe a la autoridad · trámite o aprobación ante la autoridad · plan de contingencia o emergencia · condición de PAS · forma de cumplimiento de normativa · otra.
- `fase`: construcción · operación · cierre · combinaciones en ese orden separadas por coma (ej.: `"construcción, cierre"`) · todas · No consta. Usa `"todas"` solo si el texto dice todas las fases o nombra construcción, operación y cierre.

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

### 1. Preparar
Si no existen `salida/texto/<archivo>.json` y `salida/secciones/<archivo>.json`, genéralos con `leer_pdf.py` y `localizar_secciones.py`. **Procesamiento incremental:** si ya existe `salida/obligaciones/<archivo>.json` con el mismo `sha256`, no la rehagas salvo que el usuario lo pida.

Lee del mapa de secciones las que forman `paginas_para_obligaciones`: medidas, compromisos voluntarios, plan de seguimiento, contingencias, condiciones o exigencias, otros_tramite, permisos sectoriales, normativa aplicable y parte resolutiva. Anota su confianza: una sección con confianza media o un tramo aislado se confirma leyendo la página.

### 2. Leer sección por sección
Nunca leas el rango completo de una vez. Por cada sección:

```bash
.venv/bin/python scripts/mostrar_paginas.py salida/texto/<archivo>.json --paginas 66-70
```

Si una sección es larga (más de unas 15 páginas), léela por partes. Las páginas marcadas `LECTURA VISUAL` o escaneadas se leen **con visión** sobre `salida/imagenes/<archivo>/pagina_N.png`; sus obligaciones llevan `fuente: "imagen"`. Si una página no se puede leer, va a `control.paginas_no_leidas` con su sección y motivo.

### 3. Registrar las obligaciones
Para cada obligación, completa todos los campos del `modelo_obligacion`. `ubicacion_en_documento` es el considerando, tabla o numeral (ej.: `"Considerando 8°, Tabla 8.1, Condición 1"`); `seccion_localizador` es la clave de la sección del mapa (ej.: `"condiciones_exigencias"`). Numera `OBL-001`, `OBL-002`… en orden de aparición.

### 4. Cobertura
En `control.paginas_rango` copia `paginas_para_obligaciones` del mapa. Cada página del rango debe quedar en uno de tres estados: citada por al menos una obligación; en `paginas_sin_obligaciones` con un motivo breve (ej.: "continuación de la tabla 8.3; sin deberes nuevos", "antecedentes de la evaluación"); o en `paginas_no_leidas` con su motivo. Si una obligación continúa en la página siguiente y esa página no lleva ninguna cita (ni principal ni adicional), va en `paginas_sin_obligaciones` con el motivo "continuación de OBL-0xx".

### 5. Validar y corregir

```bash
.venv/bin/python scripts/validar_obligaciones.py salida/obligaciones/<archivo>.json salida/texto/<archivo>.json
```

Corrige todos los ERRORES hasta que diga "Obligaciones válidas.". Una cita "no encontrada" se corrige copiando el texto exacto de la página. Las advertencias se informan.

### 6. Entregar
Muestra al usuario una tabla con: ID, tipo, descripción, plazo o frecuencia, autoridad, fase, página y confianza; después, las páginas leídas sin obligaciones con su motivo, las no leídas, los posibles duplicados y las advertencias del validador. Termina con: "Herramienta de apoyo. Requiere revisión de un abogado."
