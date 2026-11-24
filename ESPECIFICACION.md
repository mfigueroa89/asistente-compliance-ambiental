# ESPECIFICACION: Asistente de Compliance Ambiental

Versión 0.9. Documento vivo: lo voy a ir corrigiendo y ampliando. Si algo de aquí te parece ambiguo, pregúntame antes de decidir.

## 0. Propósito y alcance

Problema real: al revisar RCAs hay que leerlas completas, aplicar OCR a las escaneadas, armar fichas a mano, listar las obligaciones del titular y averiguar si hay obligaciones relacionadas con un tema (por ejemplo humedales). Es lento y propenso a errores.

Solución: un plugin de Claude Code que, a partir de una carpeta con RCAs en PDF, produce un Excel de compliance ambiental con trazabilidad (página y cita de cada dato) y permite consultar las obligaciones por tema o palabra clave.

IMPORTANTE, ENFOQUE: el centro del asistente son las OBLIGACIONES de compliance. Las palabras clave no son el centro: son una forma de consultar y filtrar las obligaciones. El flujo principal siempre extrae ficha y obligaciones, sin depender de ninguna palabra clave.

Dentro del alcance (MVP):
- Lectura de PDFs (texto, y lectura visual de páginas escaneadas).
- Ficha estructurada por RCA.
- Extracción de obligaciones con plazo, responsable, fase y medio de verificación.
- Etiquetado de las obligaciones por tema (temas y sinónimos configurables).
- Consulta de obligaciones por cualquier palabra, frase o tema.
- Verificación automática y semántica de las citas.
- Exportación a Excel agrupada por unidad fiscalizable (UF) y proyecto.
- Publicación en GitHub como plugin instalable.

Fuera del alcance por ahora (ver backlog, sección 14): cruce automático con SNIFA, descarga automática desde e-SEIA, interfaz web, análisis de EIA/DIA completos (solo la resolución).

## 1. Flujo general (pipeline)

Flujo principal (procesar):
1. El usuario deja PDFs en rcas/ y completa manifiesto.csv.
2. scripts/leer_pdf.py extrae el texto por página de cada PDF y marca las páginas escaneadas. Resultado: salida/texto/<archivo>.json
2b. scripts/localizar_secciones.py ubica, por código y sin IA, en qué páginas están las medidas, compromisos voluntarios, plan de seguimiento, contingencias, condiciones o exigencias y la parte resolutiva. Resultado: salida/secciones/<archivo>.json
3. Skill fichar-rca: Claude lee las primeras páginas (identificación) y las páginas ubicadas por el localizador (y las imágenes de las páginas que requieren lectura visual), y escribe la ficha. Resultado: salida/fichas/<archivo>.json
4. Skill extraer-obligaciones: Claude escribe la lista de obligaciones. Resultado: salida/obligaciones/<archivo>.json
5. scripts/buscar_palabras.py etiqueta cada obligación con los temas cuyos términos aparecen literalmente (config/temas.yaml) y busca además los términos en el texto completo. Resultado: salida/temas/<archivo>.json
6. Claude completa, para cada obligación, los temas relacionados aunque no aparezcan los términos (con justificación), dentro de la misma skill extraer-obligaciones.
7. scripts/verificar_citas.py comprueba por código que cada cita existe en la página indicada. Luego el agente verificador hace la revisión semántica. Resultado: salida/verificacion/<archivo>.json
8. scripts/exportar_excel.py une todo con el manifiesto y genera salida/compliance_ambiental.xlsx

Flujo de consulta (en cualquier momento, sobre RCAs ya procesadas):
- Skill consultar-obligaciones: el usuario pregunta con una palabra, frase o tema y el sistema devuelve las obligaciones relacionadas.

El orquestador es la skill procesar-carpeta, que ejecuta los pasos 2 a 8 en orden, procesa los archivos de uno en uno e informa avance.

## 2. Estructura de carpetas

```
asistente-compliance-ambiental/
├── .claude-plugin/
│   └── plugin.json
├── CLAUDE.md
├── ESPECIFICACION.md
├── README.md
├── requirements.txt
├── .gitignore                  (ignora rcas/, manifiesto.csv, salida/, .venv/, .env, __pycache__)
├── config/
│   ├── temas.yaml              (temas con sinónimos, editable)
│   └── equivalencias_articulo_11.yaml (letras a-f del art. 11 Ley 19.300 y su artículo, por reglamento del SEIA)
├── skills/
│   ├── procesar-carpeta/SKILL.md
│   ├── fichar-rca/SKILL.md
│   ├── extraer-obligaciones/SKILL.md
│   └── consultar-obligaciones/SKILL.md
├── agents/
│   └── verificador.md
├── scripts/
│   ├── leer_pdf.py
│   ├── localizar_secciones.py
│   ├── buscar_palabras.py
│   ├── verificar_citas.py
│   ├── exportar_excel.py
│   └── revisar_datos_personales.py (revisión antes de publicar PDFs)
├── ejemplos/
│   ├── manifiesto_ejemplo.csv
│   ├── rcas_publicas/          (hasta 3 RCAs públicas del e-SEIA, < 10 MB c/u; SÍ se suben a GitHub)
│   └── (salida de ejemplo, sin datos confidenciales)
├── tests/                      (pruebas automáticas con pytest)
├── rcas/                       (carpeta de trabajo del usuario; no se sube a GitHub)
└── salida/                     (resultados; no se sube a GitHub)
```

## 3. Entradas

### 3.1 rcas/
PDFs de RCAs públicas (la resolución de calificación, no el expediente completo). Un archivo por RCA.

### 3.2 manifiesto.csv
Un archivo CSV (UTF-8) con una fila por cada par RCA–unidad fiscalizable. La relación es de muchos a muchos: una misma RCA puede aparecer en varias filas (una por cada unidad fiscalizable a la que pertenece) y una unidad puede tener varias RCAs. Lo que no puede repetirse es el mismo par (archivo, unidad_fiscalizable): eso es un error que indica las dos filas.

Separador: coma o punto y coma (Excel en español suele guardar con punto y coma). El lector detecta cuál se usó y lo avisa.

Ubicación: el manifiesto real del usuario es manifiesto.csv, en la raíz, y no se sube a GitHub (está en .gitignore). El de ejemplo, con las 3 RCAs públicas, es ejemplos/manifiesto_ejemplo.csv y sí se sube. Los nombres de unidad fiscalizable del ejemplo vienen de la ficha de cada unidad en SNIFA (enlace en la columna enlace_uf_snifa).

Lector: scripts/leer_manifiesto.py.

Codificación: el lector asume UTF-8 (acepta también UTF-8 con BOM, que es como lo guarda Excel con la opción "CSV UTF-8"). Si el archivo no es UTF-8 válido o contiene caracteres mal codificados (por ejemplo "Ã³" en vez de "ó", o el símbolo "�"), el sistema se detiene con un error claro en español que indica la fila y cómo volver a guardar el archivo en UTF-8.

Columnas:

| Columna | Descripción | Obligatoria |
|---|---|---|
| archivo | Nombre exacto del PDF en rcas/ | Sí |
| unidad_fiscalizable | Nombre de la UF según SNIFA | Sí |
| id_uf_snifa | Código o ID de la UF en SNIFA, si se conoce (el número de su ficha) | No |
| enlace_uf_snifa | Enlace a la ficha de la UF en SNIFA, de donde sale su nombre | No |
| proyecto | Nombre del proyecto | Sí |
| titular | Titular del proyecto | No (se intenta extraer del PDF) |
| region | Región | No |
| notas | Comentarios libres | No |
| enlace_eseia | Enlace a la ficha del expediente de la RCA en el e-SEIA (basta en una fila por RCA; si hay dos distintos, se avisa y se usa el primero; si no empieza con http:// o https://, se avisa y se muestra sin hipervínculo) | No |
| nota_uf | Nota sobre la unidad fiscalizable, escrita por el usuario (por ejemplo, "No encontrada en SNIFA al 2026-11-23"); el sistema no la deduce | No |
| prefijo_id | Prefijo del ID visible de las obligaciones de esa RCA (2 a 5 letras mayúsculas, por ejemplo ARQ: ARQ-024 en vez de OBL-024). Uno por RCA y distinto entre RCAs; sin prefijo se muestra el ID interno | No |

Si una fila nombra un PDF que no está en la carpeta, el sistema avisa y lo marca "sin PDF en la carpeta". Un PDF de la carpeta sin fila en el manifiesto se incluye bajo "SIN UF ASIGNADA", con aviso. Una fila con unidad_fiscalizable vacía también queda como "SIN UF ASIGNADA".

### 3.4 Procesamiento incremental
- Cada ficha guarda el SHA-256 del PDF del que salió. Una RCA ya fichada con el mismo SHA-256 se salta (no se vuelve a fichar), salvo que el usuario pida rehacerla. Si el PDF cambió (SHA-256 distinto), se vuelve a fichar y se avisa.
- La misma regla se aplica a cada etapa con JSON propio (texto, secciones, obligaciones): si el JSON existe y corresponde al mismo SHA-256, se salta.
- El Excel nunca se edita: se regenera completo en cada ejecución, desde el manifiesto y todos los JSON de salida/. Si una ficha no corresponde al PDF actual, el Excel la marca "DESACTUALIZADA".

### 3.3 config/temas.yaml
Grupos de temas, cada uno con su lista de términos y sinónimos. Es editable por el usuario. Formato:

```yaml
humedales:
  - humedal
  - bofedal
  - vega
  - turbera
  - ecosistema lacustre
  - sitio Ramsar
recursos_hidricos:
  - derechos de agua
  - caudal ecológico
  - acuífero
  - napa
  - extracción de agua
pueblos_indigenas:
  - pueblos indígenas
  - comunidad indígena
  - Convenio 169
patrimonio_cultural:
  - patrimonio cultural
  - monumento nacional
  - hallazgo arqueológico
flora_y_fauna:
  - flora
  - fauna
  - especie en categoría de conservación
  - rescate y relocalización
areas_protegidas:
  - área protegida
  - parque nacional
  - sitio prioritario
glaciares:
  - glaciar
  - criósfera
```
Además, al consultar, el usuario puede escribir cualquier palabra o frase suelta que no esté en el archivo.

## 4. Scripts

Requisitos generales: Python 3; mensajes de error claros en español; no deben fallar completo por un PDF dañado (registran el error y siguen); funcionan en Windows y Mac.

### 4.1 leer_pdf.py
- Entrada: ruta de un PDF. Salida: JSON en salida/texto/.
- Usa PyMuPDF (pymupdf).
- Por página guarda: numero_pdf (empezando en 1), numero_impreso (si se detecta en el pie o encabezado; si no, null), texto, n_caracteres, escaneada (true si el texto tiene menos de 50 caracteres útiles).
- Para páginas escaneadas genera una imagen PNG en salida/imagenes/<archivo>/pagina_N.png, para que Claude la lea con visión. No instalar Tesseract por defecto. Si el usuario lo tiene instalado, usarlo como segunda opción (parámetro --ocr tesseract).
- Normaliza el texto: une palabras cortadas por guion al final de línea, colapsa espacios, conserva saltos de párrafo.
- Registra metadatos: nombre, n_paginas, n_paginas_escaneadas, fecha de procesamiento.
- Agregados aprobados en la Etapa 1 (por lo observado en RCAs reales):
  - estado de cada página: "texto", "escaneada" (poco texto y con imagen o dibujo), "poco_texto" (portadillas) o "en_blanco". Solo las escaneadas cuentan como páginas no revisables por texto.
  - requiere_lectura_visual y sus motivos: página escaneada, marcadores sin rellenar en el texto (por ejemplo "<NUM_RES>" o "<FECHA_RESOLUCION>", que en las RCAs firmadas electrónicamente esconden el número y la fecha, visibles solo en la imagen) o sello de firma visible. Se genera la imagen de esas páginas.
  - caracteres_dudosos: cantidad de "�" por página. No se corrigen.
  - origen_texto: "digital", "ocr_previo" o "sin_texto". Una página tiene OCR previo cuando casi todo su texto es invisible y está sobre una imagen que cubre la página (escaneo al que alguien ya aplicó OCR). Su calidad es variable: el texto se conserva tal cual y las citas de esas páginas deben confirmarse contra la imagen. Caso de prueba: RCA 21/2016 de Albemarle.
  - sha256 del archivo, para trazabilidad.
  - Rechaza con error claro lo que no es un PDF (por ejemplo, la página web que entrega infofirma.sea.gob.cl para documentos firmados en XML), además de PDFs dañados, vacíos o con contraseña.
  - Acepta varios PDFs a la vez; si uno falla, lo registra en salida/errores/ y sigue con los demás.

### 4.2 buscar_palabras.py
Es el motor de búsqueda exacta (sin IA). Tiene dos usos:
1. Etiquetar obligaciones: para cada obligación (descripción y cita), indica qué temas de config/temas.yaml aparecen literalmente. Resultado: temas_literales.
2. Buscar en el texto completo de una RCA cualquier tema, palabra o frase. Resultado: hallazgos.
Reglas:
- Búsqueda sin distinguir mayúsculas ni tildes, y tolerante a plural simple (humedal/humedales).
- Por hallazgo: termino, tema (si pertenece a uno), pagina_pdf, pagina_impresa, contexto (unos 200 caracteres antes y después).
- Resumen por término: total de apariciones y páginas.
- En páginas escaneadas sin texto no puede buscar: debe listarlas aparte como "páginas no revisadas por falta de texto", para que quede claro el límite.
- Acepta términos sueltos por línea de comandos (para las consultas).

### 4.3 verificar_citas.py
- Entrada: ficha y obligaciones JSON + texto JSON. Salida: JSON en salida/verificacion/.
- Para cada cita textual declarada, comprueba que exista en la página indicada (normalizando espacios y tildes; coincidencia exacta o muy aproximada, umbral configurable).
- Estados: "confirmada", "aproximada", "no encontrada en esa página", "encontrada en otra página" (indicando cuál).
- No modifica la ficha ni las obligaciones; solo informa.

### 4.4 exportar_excel.py
- Entrada: manifiesto.csv (leído con leer_manifiesto.py), la carpeta de PDFs (--rcas, para comprobar el SHA-256) y todos los JSON de salida/. Salida: salida/compliance_ambiental.xlsx (openpyxl), regenerado completo cada vez.
- Ninguna celda queda vacía: "No consta" cuando el dato no aparece en el documento; "—" cuando no aplica (por ejemplo, la página de un dato "No consta").
- Estructura en la sección 9.
- Formato: encabezados en negrita con fondo, filtros automáticos, primera fila fija, ancho de columnas razonable, texto con ajuste de línea, fechas como fecha.
- Colores en la columna de confianza (alta verde, media amarillo, baja rojo) y en verificación.
- Primera hoja con aviso: "Herramienta de apoyo. Requiere revisión de un abogado."

### 4.5 Pruebas
- Todas las pruebas están en tests/ y se ejecutan con pytest.
- Usan primero las RCAs de ejemplos/rcas_publicas/ (texto real, páginas reales).
- El caso de página escaneada usa un PDF sintético que las pruebas generan solas en una carpeta temporal: una página con texto y otra que es solo una imagen. El usuario no tiene que crearlo.
- Casos mínimos: PDF normal, página escaneada, PDF dañado o vacío (no debe detener el proceso) y manifiesto con caracteres mal codificados.
- Si ejemplos/rcas_publicas/ está vacía, las pruebas que la necesitan se saltan con un aviso, en vez de fallar.

### 4.6 localizar_secciones.py
Es el mapa de la RCA (sin IA). Permite que las skills lean solo las páginas relevantes, porque una RCA puede tener 300 a 500 páginas.
- Entrada: salida/texto/<archivo>.json (o el PDF, que lee con leer_pdf.py). Salida: salida/secciones/<archivo>.json y un resumen en pantalla.
- Secciones: identificación (primeras páginas), medidas (mitigación, reparación, compensación), compromisos ambientales voluntarios, plan de seguimiento, contingencias y emergencias, condiciones o exigencias, y parte resolutiva (RESUELVO).
- Busca títulos con frases flexibles (sin distinguir mayúsculas ni tildes, con o sin numeración), porque las RCAs antiguas redactan distinto. Por cada sección entrega las páginas donde aparece el título, el título encontrado y un rango de páginas propuesto (hasta el título siguiente de otra sección).
- Distingue títulos (párrafos cortos) de simples menciones dentro de un párrafo, e ignora las páginas de índice o de VISTOS donde se nombran muchas secciones juntas.
- Si no ubica una sección, no adivina: avisa "no se ubicó la sección X" y propone ampliar el rango (por ejemplo, las páginas donde la sección solo se menciona).
- Mantiene siempre el número real de página del PDF.

Versión 0.4.0: sección "normativa_aplicable" ("cumplimiento de la normativa (de carácter) ambiental", "normativa (de carácter) ambiental aplicable"). La Etapa 4 lee también los permisos sectoriales y la normativa aplicable (forman parte de paginas_para_obligaciones, no de las páginas para la ficha). Verificado: no cambia ningún otro rango en las 8 RCAs de prueba.

Versión 0.4.1: en las RCAs con títulos numerados, un título sin tema reconocido solo cierra una sección si su número es, como máximo, 3 más que el de la sección (la 7 la cierran la 8, la 9 o la 10). Además, un párrafo que empieza con un número seguido de códigos cortos de punto de muestreo ("23. LP-24. TB-1 ...", celda de tabla leída por OCR) no se trata como título. Caso: el plan de seguimiento de Albemarle, que el localizador cerraba en la p. 58, pasa a las pp. 53-64. Verificado: no cambia ningún otro rango en las 8 RCAs de prueba.

Reglas de la versión 0.3.0:
- Vocabulario de RCAs antiguas: "permisos de carácter ambiental" (D.S. 95/2001) cuenta como permisos sectoriales; "observaciones ciudadanas" y "observaciones de la comunidad", como participación ciudadana; "compromiso voluntario" (sin "ambiental", en singular o plural), como compromisos.
- Antes de clasificar el comienzo de un considerando, el texto entre comillas (rectas, curvas, bajas o « », que el OCR confunde) se reemplaza por un marcador, para que un nombre de proyecto largo no tape el tema. Solo afecta la clasificación.
- Considerandos sin "Que": si en la numeración falta un considerando (por ejemplo, hay 3 y 5 pero no 4), se busca entre ambos el primer párrafo que empiece con "4." (también "1 O." por 10, OCR), salvo que ese número ya se haya ubicado como título numerado. Esos considerandos se marcan con método "considerando_sin_que" y confianza media, en el tramo y en la sección; la skill debe confirmarlos leyendo la página.
- Considerandos de trámite ("deberá remitir/informar/comunicar ... a la Superintendencia", "son de responsabilidad del Titular", "cambio de consideración") no se clasifican como sección temática: van a la sección "otros_tramite", que forma parte de las páginas para obligaciones (pueden contener obligaciones de reporte o aviso). Solo la cláusula estándar de seguimiento ("para el debido y adecuado seguimiento de las condiciones, compromisos o medidas y permisos ...") queda fuera de toda sección; se lista en "considerandos_excluidos".
- Una sección que empieza en un considerando termina en el considerando siguiente o en un título numerado posterior, aunque esté en la misma página.
- Cada tramo lleva su confianza (alta, media o baja); la de la sección es la más baja de sus tramos.
- Títulos con palabras partidas por el OCR ("Medidas de m itigación"): si un título no se reconoce con la comparación normal, se compara una versión del título sin espacios contra las mismas frases sin espacios. Solo se aplica a títulos (párrafos cortos) y solo cuando la comparación normal no reconoce nada. Con esto Quetena ubica medidas en las pp. 343-346, sin cambios en las otras 7 RCAs de prueba.
- Tramos aislados: si una sección tiene un bloque principal (su tramo más largo, de 2 páginas o más), un tramo de una sola página a más de 10 páginas de los demás tramos se marca "aislado" con confianza baja. No se suma a las páginas que leen las skills ni al rango de la ficha (rango_localizador), y se avisa. Es una regla general; por ejemplo, descarta la p. 2 de Arbiodo como condiciones (un considerando de VISTOS que nombra el ICE).

### 4.3 bis Versión simple de verificar_citas.py (adelantada a la Etapa 2)
- Comprueba por código que cada cita de la ficha exista en el texto de la página indicada, normalizando espacios, tildes y mayúsculas, y tolerando errores de OCR (coincidencia aproximada con umbral) en las páginas con OCR previo.
- validar_ficha.py la usa. El agente verificador semántico sigue en la Etapa 7.

## 5. Skills

Formato: cada skill es una carpeta con SKILL.md (con frontmatter de nombre y descripción) y, si hace falta, archivos de apoyo. Las descripciones deben ser claras para que Claude sepa cuándo usarlas.

### 5.1 procesar-carpeta (orquestador)
Qué hace: procesa todas las RCAs de rcas/ de punta a punta.
Pasos:
1. Verifica que existan rcas/, manifiesto.csv y config/temas.yaml. Si falta algo, lo dice y se detiene.
2. Muestra cuántos PDFs encontró y cuáles no están en el manifiesto.
3. Para cada PDF: ejecuta leer_pdf.py, invoca fichar-rca y extraer-obligaciones, ejecuta buscar_palabras.py y verificar_citas.py, e invoca el agente verificador.
4. Al final ejecuta exportar_excel.py y entrega un resumen: archivos procesados, errores, cantidad de obligaciones por RCA, cantidad de citas no confirmadas, ruta del Excel.
5. Si un archivo falla, registra el error y continúa con el siguiente.
Debe poder retomar según la sección 3.4: si ya existe el JSON de una etapa para un archivo y corresponde al mismo SHA-256 del PDF, la salta salvo que el usuario pida rehacer; al final regenera el Excel completo.

### 5.2 fichar-rca
Qué hace: lee el texto de una RCA (salida/texto/<archivo>.json) y las imágenes de las páginas escaneadas, y escribe salida/fichas/<archivo>.json con los campos de la sección 7.
Reglas:
- Solo información que conste en el documento. Si no consta: "No consta".
- Cada campo con valor lleva pagina_pdf y cita_textual (máximo unas 40 palabras).
- No interpreta: distingue lo que dice la resolución de cualquier inferencia.
- Para fechas usa formato AAAA-MM-DD; para montos conserva la cifra y la unidad tal como aparece (por ejemplo "US$ 150 millones").
- No lee la RCA completa: lee las primeras páginas (identificación) y las páginas que ubique localizar_secciones.py, conservando siempre el número real de página del PDF. Debe funcionar con RCAs de 300 a 500 páginas. Si una sección no se ubicó, lo dice y amplía el rango según lo propuesto por el localizador.
- Cada dato lleva "fuente": "texto" (texto digital), "imagen" (leído en la imagen de la página) u "ocr_previo" (texto de OCR, a confirmar contra la imagen). La única excepción es letra_equivalente de los efectos del artículo 11: fuente "equivalencia_legal" (tabla fija en config/), sin página ni cita.
- Lee siempre la página de inicio de las secciones de condiciones o exigencias, compromisos voluntarios y contingencias, para llenar los campos hay_condiciones_exigencias, hay_compromisos_voluntarios y hay_plan_contingencias.
- En los campos que son listas, cada elemento lleva su propia página y cita.

### 5.3 extraer-obligaciones (skill central)
Qué hace: identifica todas las obligaciones del titular que surgen de la RCA y escribe salida/obligaciones/<archivo>.json con los campos de la sección 8.
Qué buscar: condiciones o exigencias de la RCA, compromisos ambientales voluntarios, medidas de mitigación, reparación y compensación, planes de seguimiento y monitoreo, reportes o informes a la autoridad (especialmente a la SMA), planes de contingencia o emergencia, permisos ambientales sectoriales con condiciones, y cualquier otra obligación con plazo o frecuencia.
Reglas:
- Una fila por obligación; no agrupar varias obligaciones distintas en una.
- Plazo y frecuencia textuales, como aparecen; si no hay, "No consta".
- Responsable: quien debe cumplir según el texto (normalmente el titular); si el texto menciona un tercero o la autoridad, indicarlo.
- Marcar confianza alta, media o baja según qué tan explícito es el texto. En caso de duda, baja.
- No inventar plazos ni responsables. No deducir obligaciones que el texto no establece.
- Una obligación: si una medida exige además un reporte (por ejemplo, capacitar y enviar un informe a la SMA), son dos filas (la medida y el reporte), unidas por el mismo ubicacion_en_documento.
- Posibles duplicados: si la misma obligación aparece en dos partes de la RCA (por ejemplo, en un PAS y en las condiciones), no se fusionan: dos filas, cada una con su página y cita, y en posible_duplicado cada una nombra el ID de la otra.
- Permisos sectoriales: solo los deberes explícitos ("el titular deberá…"), no la descripción del permiso. Normativa aplicable: solo las formas concretas de cumplimiento o de reporte que fija la RCA (registros, informes, plazos), no la ley en sí.
- Contingencias: por cada riesgo, las medidas preventivas y de control sin plazo propio pueden agruparse en una fila (agrupada = sí), con una cita por cada medida (cita principal más citas_adicionales) y el rango de páginas de respaldo; una sola cita no basta para un grupo. Cada medida con frecuencia o parámetro y cada aviso o reporte va en su propia fila.
- Cobertura (la revisa validar_obligaciones.py): cada página del rango de obligaciones debe quedar citada por alguna obligación, listada como "leída sin obligaciones" con motivo, o como "no leída" con motivo.
- Páginas escaneadas dentro de los rangos de obligaciones (por ejemplo, Arqueros pp. 166-167, dentro de medidas): se leen con visión sobre la imagen de la página (salida/imagenes/), nunca se omiten, y sus obligaciones llevan fuente "imagen". La ficha deja anotadas estas páginas en observaciones_generales para que esta etapa las lea.
- Temas: después de que buscar_palabras.py complete temas_literales, la skill agrega temas_relacionados: temas de config/temas.yaml que considera relacionados con la obligación aunque no aparezcan los términos, con una justificación de una frase. Estos se marcan "revisar" porque son interpretación.

### 5.4 consultar-obligaciones
Qué hace: responde preguntas del tipo "¿qué obligaciones hay relacionadas con humedales?" sobre las RCAs ya procesadas (o procesa primero las que falten, avisando).
Entrada: cualquier palabra, frase o tema, y opcionalmente una RCA o unidad fiscalizable específica.
Salida:
1. Coincidencia literal: obligaciones cuyo texto contiene el término o sus sinónimos (usa buscar_palabras.py). Es exacta y verificable.
2. Relación temática (revisar): obligaciones que la IA considera relacionadas aunque no contengan el término, con la justificación.
3. Mención sin obligación: si el término aparece en la RCA pero no en ninguna obligación (por ejemplo en la descripción del proyecto), lo informa por separado, con página.
4. Si no hay ninguna, lo dice claramente. No inventa relaciones.
Cada resultado incluye: UF y proyecto, ID de la obligación, descripción, plazo o frecuencia, responsable, página y cita.
Opcional: genera la hoja "Consulta" en el Excel con el resultado.
Puede agregar o quitar términos y temas en config/temas.yaml a pedido del usuario.

## 6. Agente verificador (agents/verificador.md)

Rol: revisor independiente. No participó en la extracción y no la corrige: la audita.
Entrada: ficha, obligaciones, texto y resultado de verificar_citas.py de una RCA.
Tarea:
1. Para cada obligación con confianza media o baja, y para una muestra de la ficha (decisión, titular, fecha, tipo de proyecto, monto), leer la página citada y decidir si el dato está respaldado.
2. Revisar las citas marcadas "no encontrada" o "encontrada en otra página".
3. Revisar los temas_relacionados y decir si la justificación es razonable.
4. Buscar omisiones: obligaciones importantes del texto que no aparecen en la lista (revisar los apartados de condiciones, compromisos y seguimiento).
Salida: salida/verificacion/<archivo>_semantica.json con, por ítem: estado (respaldado, parcialmente respaldado, no respaldado), comentario breve y propuesta de corrección si corresponde. También una lista de posibles omisiones.
Regla: no escribe sobre ficha ni obligaciones. Las correcciones las decide el usuario.

## 7. Esquema de la ficha (campos)

Cada campo con valor se guarda como: valor, pagina_pdf, cita_textual. Los marcados (L) son listas.

Identificación de la resolución
- numero_resolucion: N° de la Resolución Exenta (RCA)
- fecha_resolucion
- organo_calificador: Comisión de Evaluación de la región, Dirección Ejecutiva del SEA u otro
- numero_expediente_o_codigo: código o ID del expediente en el e-SEIA, si consta
- tipo_instrumento: DIA o EIA
- decision: favorable o desfavorable (calificación)
- reglamento_aplicable: Reglamento del SEIA que cita la RCA (por ejemplo D.S. N° 95/2001 o D.S. N° 40/2012), con página y cita. Si no lo identifica: "No consta" y el validador solo advierte.

Proyecto y titular
- nombre_proyecto
- titular
- region, provincia, comuna (L)
- tipologia: literal del artículo 3 del Reglamento del SEIA, si consta
- descripcion_breve: dos o tres frases fieles al documento
- monto_inversion
- vida_util
- fases (L): construcción, operación, cierre, otras
- superficie_o_dimensiones: lo que conste (hectáreas, MW, etc.)

Evaluación ambiental
- componentes_ambientales_relevantes (L): aire, agua, suelo, flora, fauna, humedales, paisaje, patrimonio cultural, medio humano, ruido, etc.
- efectos_articulo_11 (L): efectos, características o circunstancias del artículo 11 de la Ley 19.300 (letras a a f) que la resolución reconoce o descarta. "valor" dice solo lo que dice el documento. Cada elemento lleva además letra_equivalente, tomada de la tabla fija config/equivalencias_articulo_11.yaml (a=5, b=6, c=7, d=8, e=9, f=10, artículos del Reglamento SEIA), con fuente "equivalencia_legal" y sin página ni cita. La tabla es una por reglamento (D.S. 40/2012: a=5 … f=10; D.S. 95/2001, art. 2: a=5, b=6, c=8, d=9, e=10, f=11) y cada número se verificó contra el texto oficial de la BCN; un reglamento no verificado queda con tabla vacía y el validador solo advierte. El validador comprueba que la equivalencia no contradiga la letra o el artículo que menciona el efecto.
- participacion_ciudadana: sí o no, y observaciones relevantes, si consta
- pueblos_indigenas: mención a consulta o grupos humanos pertenecientes a pueblos indígenas, si consta
- permisos_ambientales_sectoriales (L): PAS mencionados
- areas_protegidas_o_sensibles (L): áreas protegidas, sitios prioritarios, humedales, glaciares, etc., mencionados. Cada elemento lleva "categoria" (área protegida, sitio prioritario, humedal, zona de interés turístico u otra). No se califica de protegido lo que el texto no declare protegido.

Medidas y seguimiento (resumen; el detalle va en obligaciones)
- hay_medidas_mitigacion, hay_medidas_reparacion, hay_medidas_compensacion (sí, no o No consta)
- hay_plan_seguimiento (sí, no o No consta)
- hay_condiciones_exigencias, hay_compromisos_voluntarios, hay_plan_contingencias (sí, no o No consta), con página y cita del encabezado de la sección, y rango_localizador: el rango de páginas que ubicó localizar_secciones.py, o "No ubicada"

Control
- paginas_totales, paginas_escaneadas
- campos_no_consta: lista de campos sin dato
- paginas_ocr_previo, paginas_revisadas_en_imagen (páginas cuya imagen se revisó contra el texto)
- paginas_no_leidas: lista de páginas no leídas, cada una con pagina, seccion y motivo (por ejemplo, una página escaneada ilegible dentro de medidas). Se muestran en el Excel (Léeme, y en la hoja de verificación cuando exista).
- observaciones_generales: dudas o límites del documento (por ejemplo, páginas ilegibles)

Marca de calidad de los datos con OCR: si el OCR leyó mal un número o una sigla, el valor sigue a la imagen, la cita conserva el texto del OCR y el dato lleva "correccion_ocr" (qué dice el OCR y qué dice la imagen). En el Excel, cada dato con OCR se marca como "OCR confirmado en la imagen", "OCR corregido según la imagen" o "Solo OCR (imagen no revisada)".

## 8. Esquema de obligaciones (una fila por obligación)

- id_obligacion: OBL-001, OBL-002... por archivo, correlativos en orden de aparición
- tipo: condición o exigencia / compromiso ambiental voluntario / medida de mitigación / medida de reparación / medida de compensación / plan de seguimiento o monitoreo / reporte o informe a la autoridad / trámite o aprobación ante la autoridad / plan de contingencia o emergencia / condición de PAS / forma de cumplimiento de normativa / otra
- componente_ambiental
- fase: construcción / operación / cierre / combinaciones en ese orden separadas por coma (por ejemplo "construcción, cierre") / todas / No consta
- descripcion: la obligación explicada con claridad y sin agregar nada
- plazo_o_frecuencia: textual, o "No consta"
- hito_o_gatillo: evento que activa el plazo (por ejemplo, "antes del inicio de la construcción"), o "No consta"
- responsable: titular u otro, según el texto
- autoridad_destinataria: a quién se informa o reporta (SMA, SEA, otro servicio), o "No consta"
- medio_de_verificacion: informe, registro, certificado, monitoreo, etc., o "No consta"
- parametro_o_indicador: si hay un valor, umbral o indicador exigido
- ubicacion_en_documento: considerando o sección
- pagina_pdf
- pagina_impresa
- cita_textual: máximo unas 40 palabras
- temas_literales: temas cuyos términos aparecen textualmente (detectado por código)
- temas_relacionados: temas relacionados sin que aparezcan los términos. Cada elemento: {"tema", "justificacion" (una frase que cita entre « » las palabras del PDF que la motivan), "palabras_pdf" (esas palabras, exactas), "pagina_pdf", "estado": "revisar"}. validar_obligaciones.py comprueba que el tema exista en config/temas.yaml, que no sea ya literal y que palabras_pdf esté en su página. El archivo lleva además "temas_relacionados_revisados" ({"temas", "fecha", "criterio"}) cuando la RCA ya se revisó; la consulta lo usa para informar el alcance.
- confianza: alta / media / baja
- seccion_localizador: clave de la sección del mapa del localizador donde está la obligación
- fuente: texto / imagen / ocr_previo (y correccion_ocr si el valor sigue a la imagen), como en la ficha
- posible_duplicado: lista de ID de la misma obligación en otra parte de la RCA (relación recíproca)
- agrupada: sí/no. Una fila agrupada reúne varias medidas sin plazo propio (por ejemplo, las medidas preventivas de un riesgo en contingencias)
- citas_adicionales: en una fila agrupada, una cita por cada medida que agrupa; en cualquier fila, una cita por cada dato de la descripción, plazo, hito o parámetro que esté en otra oración o página que la cita principal (cada una con pagina_pdf y cita_textual); el validador las verifica todas
- paginas_respaldo: en una fila agrupada, el rango de páginas que respalda todas sus medidas (ej.: "85-86"); debe cubrir todas las citas. En una fila no agrupada con citas en varias páginas, se recomienda indicarlo
- notas

Archivo: salida/obligaciones/<archivo>.json, con sha256, secciones leídas, la lista de obligaciones y un bloque de control (paginas_rango, paginas_sin_obligaciones, paginas_no_leidas, paginas_revisadas_en_imagen, observaciones_generales). Validador: scripts/validar_obligaciones.py.

## 9. Estructura del Excel (salida/compliance_ambiental.xlsx)

Hojas, en este orden:

1. Léeme: título, fecha de generación, aviso de revisión por abogado, cantidad de RCAs procesadas, explicación breve de cada hoja, cómo leer "No consta" y "—", leyenda de colores, avisos (del manifiesto y fichas desactualizadas o faltantes) y páginas no leídas (mientras no exista la hoja Verificación).
2. Índice UF: una fila por unidad fiscalizable. Columnas: unidad_fiscalizable, id_uf_snifa, enlace_uf_snifa, proyectos, titular (según ficha), cantidad de RCAs, archivos, cantidad de obligaciones, citas por revisar, páginas no leídas, estado de las fichas, nota_uf (la del manifiesto; si la fila reúne varias RCAs, cada nota va con su archivo).
2b. Resumen: una fila por RCA con sus datos clave: unidades fiscalizables (todas, si son varias), proyecto, archivo, enlace_eseia (con hipervínculo), N° y fecha de resolución, tipo, decisión, titular, región, medidas de mitigación, reparación y compensación, plan de seguimiento, compromisos voluntarios, plan de contingencias y estado de la ficha.
3. Obligaciones (hoja principal, vista compacta; mejora 3, 2026-11-24): una fila por obligación con lo esencial, en este orden: id_visible, unidad_fiscalizable, rca (proyecto, N° y año de la resolución), tipo, descripcion, plazo_o_frecuencia, responsable, pagina_pdf y revision_estado. Filtros, títulos y columna del ID fijos, descripción ancha con ajuste de línea. Tiene exactamente las mismas filas que la hoja siguiente.
3b. Obligaciones detalle: una fila por obligación (repetida por unidad fiscalizable si la RCA pertenece a varias). Columnas: unidad_fiscalizable, proyecto, archivo, numero_resolucion, y luego los campos de la sección 8 (temas_literales calculado por código sobre las citas; temas_relacionados con su marca [revisar], "(dudosa)" si corresponde, y la página de las palabras del PDF) más estado_verificacion (el peor estado entre la cita principal y las adicionales, comprobado por código). Incluye las columnas calidad (marca de OCR, como en Fichas), citas_adicionales, paginas_respaldo y duplicado_de (la obligación representante de su grupo de posibles duplicados; "—" en la representante, de modo que filtrar por "—" deja las obligaciones distintas). Colores en confianza, verificación, fuente y duplicados. El Índice UF muestra "obligaciones_filas_totales" y "obligaciones_distintas" (los posibles duplicados cuentan una vez).
4. Fichas: una fila por dato (y por elemento en los campos que son listas). Columnas: unidad_fiscalizable, id_uf_snifa, proyecto, archivo, numero_resolucion, grupo, dato, campo, elemento, valor, pagina_pdf, cita_textual, fuente, calidad (marca de OCR), verificacion (estado de la cita) y dato_complementario (equivalencia legal, categoría o rango del localizador). Las páginas no leídas y las observaciones generales van como filas del grupo "Control". Si una RCA pertenece a varias unidades, sus filas se repiten en cada unidad.
5. Menciones en texto (secundaria): una fila por hallazgo de un término en el texto completo. Columnas: unidad_fiscalizable, proyecto, archivo, termino, encontrado, tema, pagina_pdf, pagina_impresa, contexto, recogido_en_obligacion (ID de la obligación cuya cita contiene el hallazgo, "no" o "no revisada"), obligaciones_en_la_pagina y origen_texto. Las páginas sin texto y las páginas no leídas se listan con "no revisada".
6. Verificación: una fila por alerta. Columnas: unidad_fiscalizable, proyecto, archivo, id_obligacion o campo, estado, comentario, propuesta de corrección.
7. Consulta (opcional): se genera cuando hay consultas guardadas en salida/consultas/ (consultar-obligaciones). Es el historial de todas, la más reciente arriba, cada una tal como se guardó (no se recalcula). Columnas: consulta (con el tema y sus términos, "término del tema X, buscado solo" o "término libre"), fecha_hora, filtro (unidad fiscalizable, RCAs pedidas o todas las procesadas), alcance y las columnas del CSV de consulta, empezando por categoría (coincidencia literal en verde, relación temática en amarillo, mención sin obligación en gris). Una consulta sin resultados es una fila "No hay resultados" (rojo) con su alcance. Un JSON de consulta dañado se avisa en Léeme y no detiene el Excel.
8. Hojas por UF (opcional, activada con --hoja-por-uf): una hoja por cada unidad fiscalizable (nombre truncado a 31 caracteres, sin caracteres no permitidos), que contiene sus obligaciones y fichas una debajo de la otra.

En las hojas 3 a 6, las columnas unidad_fiscalizable y proyecto van primero, para poder filtrar y agrupar; excepción aprobada por Ignacio (mejora 3): Obligaciones y Obligaciones detalle empiezan por id_visible, seguido de unidad_fiscalizable.

## 10. Reglas de calidad

- Nunca inventar: sin dato, "No consta".
- Todo dato con página y cita.
- Si una cita no se encuentra, el dato se marca visiblemente en el Excel y no se oculta.
- No mezclar información entre RCAs distintas.
- No traducir ni cambiar términos jurídicos.
- Idioma: español.
- Si el PDF tiene páginas ilegibles, decirlo en observaciones_generales.
- El sistema no emite opiniones jurídicas ni evalúa cumplimiento: solo extrae y organiza.
- La relación temática (sin términos literales) siempre se presenta como interpretación a revisar, nunca como hecho.

## 11. Criterios de aceptación (cómo sabemos que funciona)

1. Con 3 RCAs reales (una con menciones a humedales, una sin ellas y una escaneada o parcialmente escaneada) el sistema corre de punta a punta sin intervención manual y genera el Excel.
2. Las apariciones de términos coinciden con una búsqueda manual en el visor de PDF.
3. En una muestra manual de 20 campos y obligaciones de una RCA, se mide el porcentaje correcto y se registra en el README.
4. Todas las citas "confirmadas" realmente existen en la página indicada.
5. Un PDF dañado o vacío no detiene el proceso.
6. Una RCA que no está en el manifiesto aparece bajo "SIN UF ASIGNADA" y con aviso.
7. La consulta "humedales" sobre las RCAs procesadas devuelve las obligaciones relacionadas, separadas en coincidencia literal y relación temática, y una consulta sin resultados lo dice claramente.
8. El plugin se instala desde GitHub en una máquina limpia siguiendo solo el README.

## 12. Orden de construcción (etapas)

Etapa 0: preparación. Detectar sistema operativo, crear la estructura de carpetas (incluidas ejemplos/rcas_publicas/ y tests/), requirements.txt (pymupdf, openpyxl, pyyaml, pytest), .gitignore, entorno virtual .venv dentro del proyecto, instalar dependencias, confirmar que todo importa sin error. Inicializar git.
Etapa 1: leer_pdf.py con prueba sobre una RCA real. Revisar juntos el JSON.
Etapa 2: primero localizar_secciones.py (revisar su resultado en las 3 RCAs de ejemplo y en una RCA larga local); luego la versión simple de verificar_citas.py y validar_ficha.py; luego la skill fichar-rca. Fichar Queltehue y revisarla campo por campo; después Arqueros 2013 y al final Albemarle.
Etapa 3: leer_manifiesto.py y exportar_excel.py básico (Léeme, Índice UF, Resumen y Fichas). Primer Excel.
Etapa 4: skill extraer-obligaciones. Revisar y ajustar. Es la etapa más importante.
Etapa 5: config/temas.yaml y buscar_palabras.py (etiquetado de obligaciones y búsqueda en texto). Contrastar con búsqueda manual. Agregar temas a la skill de obligaciones.
Etapa 6: skill consultar-obligaciones y hoja Consulta.
Etapa 7: verificar_citas.py y agente verificador.
Etapa 8: skill procesar-carpeta (orquestador), manejo de errores y reanudación. Excel completo.
Etapa 9: plugin.json, README, ejemplos, medición de calidad.
Etapa 10: subir a GitHub e instalar desde ahí para probar.

Regla: no pasar a la etapa siguiente sin mi OK.

### 12.1 Estado

> Nota: los códigos de commit citados en esta sección (por ejemplo 2314174 o 81aee45) corresponden al repositorio de desarrollo y no existen en el repositorio publicado en GitHub, que se publicó sin ese historial.

- Etapa 0: cerrada.
- Etapa 1: cerrada.
- Etapa 2: cerrada el 2026-11-22. Fichas validadas y aprobadas de Queltehue (DIA, D.S. 40/2012), Arqueros 2013 (EIA, D.S. 95/2001) y Albemarle 2016 (EIA, D.S. 95/2001, OCR previo en todas sus páginas); todas sus citas confirmadas por código. Se agregaron reglamento_aplicable, letra_equivalente (tablas por reglamento verificadas contra la BCN), categoria en áreas protegidas o sensibles y los campos hay_condiciones_exigencias, hay_compromisos_voluntarios y hay_plan_contingencias; se quitó representante_legal.

- Etapa 4: cerrada el 2026-11-23, con auditoría humana pendiente. Obligaciones extraídas y validadas de Queltehue (177 filas), Arqueros (289) y Albemarle (62). Detalle del cierre, pendientes y correcciones al final de esta sección.
- Etapa 5: cerrada el 2026-11-23 por Ignacio, con dos pendientes suyos: (1) revisar las relaciones temáticas en salida/verificacion/relacion_tematica_arqueros.csv y relacion_tematica_queltehue_albemarle.csv; (2) decidir si se agrega la posible obligación no extraída de Arqueros p. 189 (rescate y relocalización de fauna con profesionales con experiencia en la Región de Atacama y destino de ejemplares a colecciones). Las correcciones de la Etapa 5 viven solo en salida/obligaciones/ (respaldos en salida/respaldos/). Detalle: Hecho el 2026-11-23: config/temas.yaml (los 7 temas de §3.3; "pajonal hídrico" y "sistema vegetacional azonal" NO están en humedales por decisión de Ignacio) y scripts/buscar_palabras.py con sus pruebas (consultar, revisar, descripcion-sin-cita). La coincidencia literal se busca solo en las citas (principal y adicionales), no en la descripción. Toda consulta informa su alcance (RCAs, obligaciones, páginas sin texto, páginas no leídas, OCR previo y si la relación temática ya se revisó). Los CSV van en UTF-8 con BOM y separados por punto y coma (Excel en español de Chile). Caso de prueba "humedales" en Arqueros: literales OBL-006, 024 y 038; relación temática esperada OBL-060, 061 y 202. Respaldo previo a los cambios: salida/respaldos/obligaciones_20261123_etapa5/. Con aprobación de Ignacio: citas adicionales para los 26 casos de término en la descripción sin cita (22 obligaciones; Arqueros OBL-001 sin cita nueva: su descripción dice ahora "plan de rescate de reptiles", como el PDF) y cita de la p. 51 (considerando 6) en Albemarle OBL-009, 010 y 011. La hoja Obligaciones tiene ahora la columna calidad (marca de OCR, igual que Fichas). Criterio de relación temática aprobado por Ignacio (2026-11-23) sobre una muestra de 15 filas: hay relación solo si el PDF nombra con otras palabras el objeto que la obligación protege o mide (por ejemplo "SVAHT" o "pajonal hídrico" por humedal, "nivel freático" por napa, "Colla" por indígena); no basta con que la obligación ocurra cerca. Consecuencias aplicadas: Arqueros OBL-074 (balizado para aves en el tramo de los SVAHT) no se relaciona con humedales; una fila puede tener dos temas si cada uno tiene sus propias palabras del PDF; si el término literal está en la página pero fuera de las citas, queda como relación temática y se informa (no se agregan citas sin aprobación). Arqueros revisada el 2026-11-23: 108 relaciones en 98 obligaciones (flora y fauna 42, recursos hídricos 29, patrimonio cultural 15, pueblos indígenas 13, humedales 9; ninguna de áreas protegidas ni glaciares); lista en salida/verificacion/relacion_tematica_arqueros.csv. Las palabras de las pp. 166-167 (escaneadas) se leyeron en la imagen. Podrían pasar a literal con una cita adicional (decisión de Ignacio pendiente): OBL-043, 044 y 045 («comunidades Indígenas», p. 154), OBL-189 («rescate y relocalización de fauna», p. 189), OBL-209 («acuífero freático», p. 194) y OBL-223 («calidad del acuífero», p. 198). Queltehue y Albemarle revisadas el 2026-11-23 con el mismo criterio: Queltehue 22 relaciones en 22 obligaciones (patrimonio cultural 12, con el patrimonio paleontológico de la Ley 17.288; flora y fauna 5; recursos hídricos 5); Albemarle 46 relaciones en 43 obligaciones (recursos hídricos 32, que incluye el sistema de salmuera porque la RCA lo trata como variable "recurso hídrico", p. 51; humedales 6, por las lagunas y la vegetación azonal; flora y fauna 6; patrimonio cultural 2). Descartadas por el criterio: el control de vegetación para prevenir incendios y la fosa séptica de Queltehue, las variables meteorológicas, los tapetes microbianos y el "pozo Peine" (nombre de un pozo) de Albemarle. En las tablas de Albemarle leídas en la imagen (pp. 53-62) las palabras se transcribieron de la imagen y el validador solo advierte. Lista en salida/verificacion/relacion_tematica_queltehue_albemarle.csv. Resultado de la consulta "humedales" en las tres RCAs: 3 coincidencias literales (Arqueros OBL-006, 024 y 038), 15 relaciones temáticas (9 de Arqueros y 6 de Albemarle) y menciones sin obligación en las tres. Contraste con el visor (criterio de aceptación 2), 2026-11-23: scripts/contrastar_busqueda.py compara, página por página y para cada término de temas.yaml, el buscador con una búsqueda como la del visor (Cmd+F: trozo de texto sin distinguir mayúsculas, con y sin tildes) sobre la misma capa de texto del PDF. Resultado: 0 posibles omisiones en las tres RCAs (Arqueros 455 coincidencias, Queltehue 80, Albemarle 147). Toda diferencia es de dos tipos esperados: el visor encuentra el término dentro de otra palabra ("flora" en "afloramiento", "fauna" en "herpetofauna"; 29 casos) y el buscador encuentra plurales de frases que el visor no iguala ("comunidades indígenas", "Monumentos Nacionales"; 155 casos). El texto de leer_pdf.py no cambia ningún resultado. Límite: ninguno de los dos busca en páginas escaneadas sin texto ni corrige errores del OCR. Detalle en salida/verificacion/contraste_busqueda.csv. Búsqueda manual de Ignacio en Vista Previa (2026-11-23), sobre una muestra de 4 términos: Arqueros "humedal" (17 resultados en 8 páginas), Albemarle "bofedal" (8 en 6 páginas), Queltehue "flora" (19 en el visor, 10 en el buscador: los 9 de más son "afloramiento") y Queltehue "monumento nacional" (2 en el visor, 22 en el buscador: los 20 de más son "Monumentos Nacionales"). Todo coincide con lo esperado: criterio de aceptación 2 cumplido. Decisiones de Ignacio aplicadas el 2026-11-23 (respaldo previo: salida/respaldos/obligaciones_20261123_antes_salmuera/):
- Albemarle, recursos hídricos: se separan (a) agua y variables hídricas (25 filas; las mixtas OBL-004 interfase salina, OBL-045 y 046 salmuera y agua industrial se apoyan en el agua) y (b) salmuera (7 filas: OBL-001, 002, 007, 047, 048, 053 y 055; las dos del "núcleo" del salar, 047 y 048, por ser el cuerpo de salmuera). Las (b) quedan como relación temática con "dudosa": true y se justifican con la frase de la p. 51 («la variable ambiental "recurso hídrico" se comporta de acuerdo a lo evaluado»), sin calificar a la salmuera como agua en sentido jurídico. El campo opcional "dudosa" lo acepta validar_obligaciones.py y la consulta lo muestra como "(dudosa)".
- config/temas.yaml: "paleontológico" y "paleontológica" agregados a patrimonio_cultural. Pasan a literal Queltehue OBL-053, 062 y 089 (se quitó su relación temática); OBL-063, 066 y 067 siguen como relación.
- Arqueros: cita adicional aprobada en OBL-043, 044 y 045 («Entrega de forraje a comunidades Indígenas», p. 154), OBL-189 («rescate y relocalización de fauna», p. 189; revisar: la frase rige todo el programa de rescate), OBL-209 («acuífero freático», p. 194; respalda además las 5,5 pulgadas y el PVC ranurado) y OBL-223 («calidad del acuífero», p. 198; revisar: describe el Plan de Contingencia en todas sus fases). Las seis pasan a literal y perdieron la relación temática del mismo tema.
- Resuelto el 2026-11-24 (agregadas como OBL-290 y OBL-291): posible obligación no extraída: Arqueros p. 189, realizar el rescate y relocalización de fauna con profesionales con experiencia en la Región de Atacama y destinar ejemplares a colecciones herpetológicas o de micromamíferos.
Estado de la relación temática: Arqueros 102, Queltehue 19 y Albemarle 46 (7 dudosas). Contraste con el visor repetido con los términos nuevos: 0 posibles omisiones. Excel (2026-11-23): la hoja Obligaciones tiene las columnas temas_literales (calculada por código sobre las citas) y temas_relacionados («tema [revisar] (dudosa): justificación (p. N)»), y se agregó la hoja "Menciones en texto" (869 filas en las tres RCAs: 63 recogidas en la cita de una obligación, 802 sin obligación y 4 páginas no revisadas: Arqueros pp. 60, 166 y 167, sin texto, y Albemarle p. 52, no leída). La Léeme explica ambas. Etapa 5 cerrada con el OK de Ignacio (2026-11-23).

- Etapa 6: plan aprobado por Ignacio el 2026-11-23; en construcción por partes. Parte 1 hecha (2026-11-23): buscar_palabras.py consultar acepta --uf (sin mayúsculas ni tildes; una parte del nombre si no es ambigua; un PDF sin fila en el manifiesto es "SIN UF ASIGNADA") y --relaciones (JSON de relaciones propuestas para un término libre; cada una se acepta como "revisar" solo si sus palabras_pdf están en el texto de su página según verificar_citas.py, y si no se rechaza con su motivo; un tema de temas.yaml no las acepta). Cada consulta se guarda aparte como consulta_<termino>_<AAAAMMDD-HHMMSS>.json/.csv, con fecha_hora y filtro, para el historial de la hoja Consulta. Avisa las RCAs del manifiesto sin obligaciones extraídas y no las procesa. Las pruebas trabajan sobre una copia temporal de salida/ y no agregan consultas al historial real. Parte 2 hecha (2026-11-23): skills/consultar-obligaciones/SKILL.md. Para un término libre, las búsquedas auxiliares de sinónimos se hacen sobre una copia temporal de salida/ (no entran al historial) y las relaciones propuestas van en un JSON del scratchpad que se pasa con --relaciones; una relación rechazada no se reintenta cambiando las palabras. Ensayo en una copia temporal: "pajonal" en las tres RCAs da 0 literales, 62 menciones sin obligación y 2 relaciones propuestas y aceptadas (Arqueros OBL-202 y OBL-203, «Seguimiento al Pajonal hídrico salino, en el área planta», p. 191); OBL-060 a 063 se descartan porque protegen las unidades UC09 y UC10 (otros SVAHT) en compensación por la pérdida del pajonal, no el pajonal mismo. Corrección a la verificación manual prevista: "glaciares" en Queltehue no da "sin resultados": 0 obligaciones y 3 menciones sin obligación en la p. 49 (texto del art. 11 letra d); la prueba de "sin resultados" de la hoja Consulta usa datos sintéticos. Parte 3 hecha (2026-11-23): hoja Consulta en exportar_excel.py (§9, hoja 7) y explicación en Léeme; buscar_palabras.py guarda además tema_del_termino y archivos_pedidos para que la hoja diga qué se buscó y con qué filtro. Ensayo en una copia temporal con las consultas del plan: "humedales" en las tres RCAs (3 literales, 15 relaciones, 134 menciones), "glaciares" en Queltehue (3 menciones), "pajonal" con las 2 relaciones propuestas, "turbera" en la UF de Arqueros (No hay resultados, con alcance) y las 3 consultas guardadas en la Etapa 5 (sin hora ni filtro: "consulta anterior a la Etapa 6"). Pendiente: verificación manual de Ignacio con el plugin cargado. Ajustes del 2026-11-23, a pedido de Ignacio: (1) borradas las 3 consultas de la Etapa 5 de salida/consultas/ (humedales, glaciares y recursos_hidricos, sin hora ni filtro); (2) Excel regenerado con ejemplos/manifiesto_ejemplo.csv, porque no existe manifiesto.csv en la raíz: Índice UF con la nota_uf de Queltehue y el enlace de SNIFA de Arqueros y Albemarle; el enlace del e-SEIA de las tres RCAs está en la hoja Resumen, con hipervínculo (§9); sin consultas guardadas, no hay hoja Consulta; (3) Ignacio no está de acuerdo con descartar Arqueros OBL-060 a 063 para "pajonal". Propuesta pendiente de su aprobación, no aplicada: incluirlas como relación temática (revisar) con palabras_pdf «medidas ambientales por la pérdida del pajonal hídrico salino (1,1 ha)» (p. 159) y la nota de que protegen otras unidades (UC09 y UC10, SVAHT de mayor calidad), no el pajonal perdido. Las cuatro tienen su cita en la p. 159; la p. 161 no tiene texto de ellas (es 9.2.2 Fauna: OBL-073 a 075). Comprobado por código en una copia temporal: 6 relaciones aceptadas (OBL-060 a 063, 202 y 203) y 0 rechazadas. Por decidir con la aprobación: (a) si también se incluyen OBL-064 (medida 5 de la misma lista, charlas) y OBL-065 (seguimiento de UC09 y UC10, p. 160), que responden a la misma pérdida; (b) si se marcan "dudosa"; (c) precisión del criterio en la skill consultar-obligaciones: una medida que la RCA establece expresamente por el impacto sobre el objeto consultado cuenta como relación, aunque proteja otra unidad, y se dice en la justificación. Decisiones de Ignacio aplicadas el 2026-11-23: se incluyen OBL-060 a 065; OBL-064 (medida 5, charlas) y OBL-065 (seguimiento de UC09 y UC10, pp. 159-160) quedan "dudosa", con una nota, hasta que Ignacio confirme en el PDF que las vincula con la pérdida del pajonal; cada justificación indica su número de medida (1 a 5) o que es el seguimiento. Las 8 relaciones aprobadas para "pajonal" (OBL-060 a 065, 202 y 203) quedan en salida/consultas/relaciones_aprobadas/pajonal.json (palabras_pdf de OBL-060 a 065: «medidas ambientales por la pérdida del pajonal hídrico salino (1,1 ha)», p. 159; de OBL-202 y 203: «Seguimiento al Pajonal hídrico salino, en el área planta», p. 191); comprobadas por código: 8 aceptadas, 0 rechazadas. La skill usa ese archivo como base para "pajonal" y tiene el criterio precisado. buscar_palabras.py muestra la "nota" de una relación propuesta entre [ ]. El manifiesto sigue siendo ejemplos/manifiesto_ejemplo.csv; no se crea manifiesto.csv (decisión de Ignacio). Plugin (opción A, elegida por Ignacio): se adelantan de la Etapa 9 .claude-plugin/plugin.json (§13) y .claude-plugin/marketplace.json (catálogo local "compliance-ambiental-local", que apunta a la raíz del proyecto), con pruebas en tests/test_plugin.py. En el Mac de Ignacio no está instalado el comando claude de terminal. Resultado de la prueba de Ignacio: la app de escritorio solo acepta catálogos de GitHub o de una URL de Git, no de una carpeta local; se borró .claude/settings.local.json (la línea del .gitignore se mantiene). Plan alternativo aplicado el 2026-11-23: las skills con instrucciones (consultar-obligaciones, extraer-obligaciones y fichar-rca) quedan como skills del proyecto en .claude/skills/, cada una como enlace a skills/<nombre> (una sola copia; la documentación de Claude Code admite enlaces en la ubicación de proyecto). procesar-carpeta no se enlaza hasta tener SKILL.md (Etapa 8). Cada SKILL.md tiene una sección "Rutas": si la carpeta de trabajo tiene scripts/ y config/, es la raíz; si no (plugin instalado), la raíz es la carpeta de la skill resolviendo enlaces y subiendo dos niveles; sin variables propias de plugins. Los scripts ubican config/ y las plantillas desde su propia carpeta; los datos (rcas/, salida/, manifiesto) son relativos a la carpeta de trabajo. Pruebas en tests/test_rutas.py. Pendiente para la Etapa 9: en un plugin instalado no existe <raíz>/.venv (la skill se detiene y lo dice); el README debe resolver la instalación de dependencias. En Windows, Git puede bajar los enlaces de .claude/skills/ como archivos de texto; no afecta al plugin, que usa skills/. Plan:
  - Archivos:
    1. skills/consultar-obligaciones/SKILL.md (nueva): responde consultas en lenguaje natural ("¿qué obligaciones hay sobre humedales en Arqueros?"). Ejecuta buscar_palabras.py consultar y presenta las tres categorías (coincidencia literal, relación temática (revisar), mención sin obligación) con el alcance; un "no hay resultados" siempre va con su alcance. Si el término es un tema de config/temas.yaml, la relación temática sale de temas_relacionados (Etapa 5). Si es un término libre, Claude propone la relación temática en el momento con el criterio aprobado en la Etapa 5 (relación solo si el PDF nombra con otras palabras el objeto que la obligación protege o mide), con palabras_pdf y pagina_pdf; se verifica por código y queda "revisar". Si una RCA del manifiesto no tiene obligaciones extraídas, lo avisa y no la procesa (eso es la Etapa 8). Puede agregar o quitar términos de config/temas.yaml solo después de mostrar el cambio y recibir el OK de Ignacio.
    2. scripts/buscar_palabras.py (ajustes): filtro por unidad fiscalizable (--uf) además de --archivo; opción para incorporar a una consulta las relaciones propuestas por Claude para un término libre, comprobando por código que palabras_pdf esté en su página (si no está, se rechaza).
    3. scripts/exportar_excel.py: hoja "Consulta" con consulta, fecha, alcance, categoría y las columnas del CSV de consulta; una consulta sin resultados aparece con su alcance y el mensaje "No hay resultados".
  - Decisiones de Ignacio: (a) las relaciones propuestas para un término libre se guardan solo en el resultado de esa consulta (salida/consultas/), sin tocar los JSON de salida/obligaciones/; (b) la hoja Consulta acumula el historial de todas las consultas guardadas en salida/consultas/, con la más reciente arriba y columnas de consulta y fecha. (c) Cambio de diseño del 2026-11-24, que modifica (b): la consulta no regenera el Excel. Al final de cada consulta, la skill ofrece una línea: "Si quieres, la agrego a la hoja Consulta del Excel." Si Ignacio responde que sí, ejecuta exportar_excel.py --agregar-consulta <JSON>, que regenera el Excel y marca la consulta con "en_excel": true; desde entonces queda en el historial. Si no, la consulta queda solo en el chat y en salida/consultas/ (buscar_palabras.py la guarda con "en_excel": false). La hoja Consulta muestra solo las consultas marcadas; las guardadas antes de este cambio no tienen la marca y no aparecen hasta que se agreguen. Si el Excel está abierto (archivo de bloqueo de Excel o LibreOffice, o error de permiso en Windows), exportar_excel.py lo avisa, no cambia nada (ni el Excel ni la marca) y termina con código 3. Pruebas en tests/test_exportar_excel.py (consulta no pedida no entra; --agregar-consulta la incluye y la marca; Excel abierto; consulta inexistente) y en tests/test_buscar_palabras.py (la consulta no crea ni toca el Excel).
  - Pruebas (pytest): --uf entrega solo las RCAs de esa unidad (la UF de Arqueros: sus 289 obligaciones y nada de las otras dos RCAs); una relación de término libre con palabras que no están en la página se rechaza y una válida se acepta como "revisar"; la hoja Consulta muestra varias consultas con su fecha, la más reciente arriba, y una consulta sin resultados ("glaciares") con su alcance y "No hay resultados"; con los datos reales, "humedales" sigue dando 3 literales y 15 relaciones.
  - Verificación manual de Ignacio (con el plugin cargado, claude --plugin-dir .): "¿Qué obligaciones hay sobre humedales?" (3 literales, 15 relaciones, con alcance); "Busca glaciares en Queltehue" (sin resultados, con alcance); "Busca 'pajonal'" (término libre: literales, relaciones propuestas a revisar y menciones). Luego revisar la hoja Consulta.
- Propuesta aprobada por Ignacio el 2026-11-24 y aplicada tal como se describe (OBL-290 y OBL-291 al final, OBL-189 sin la cita adicional de la p. 189 y con su relación temática de vuelta): posible obligación no extraída de Arqueros p. 189 (considerando 11, 11.1 Fauna, d) Reptiles). Son dos deberes en la misma oración, por eso dos filas:
  - Fila A: "Realizar las actividades de rescate y relocalización de fauna con profesionales con experiencia y trayectoria en la Región de Atacama." Cita (p. 189, confirmada): «Las actividades de rescate y relocalización de fauna se realizarán con profesionales que cuenten con experiencia y trayectoria en el rescate y relocalización de fauna de la Región de Atacama».
  - Fila B: "Destinar ejemplares a colecciones herpetológicas o de micromamíferos existentes en el país." Cita (p. 189, confirmada): «se destinarán ejemplares a colecciones herpetológicas o de micromamíferos existentes en el país».
  - Campos propuestos en ambas: tipo "plan de seguimiento o monitoreo" (está en el Plan de Seguimiento, como OBL-189); fase "No consta" (el texto no la dice); plazo, hito, autoridad y medio de verificación "No consta"; responsable "Titular" con confianza media (la oración está en pasiva); seccion_localizador plan_seguimiento; pagina_impresa "189"; fuente "texto".
  - ID: se recomienda agregarlas al final como OBL-290 y OBL-291, con una nota de que se agregaron en la revisión de la Etapa 5, para no renumerar las 289 obligaciones ni romper las referencias (CSV, §12.1, posibles duplicados). La alternativa, renumerar en orden de aparición, cambia los ID desde OBL-190.
  - Efecto en OBL-189: la cita adicional de la p. 189 que se le agregó el 2026-11-23 («rescate y relocalización de fauna…», marcada revisar) corresponde mejor a la fila A. Se recomienda quitarla de OBL-189; con eso OBL-189 deja de ser literal en flora_y_fauna y vuelve a relación temática («relocalización de la herpetofauna», p. 189).

Pendientes que quedan de la Etapa 2 (resolver en la etapa indicada):
- Resuelto en el localizador 0.3.0 (2026-11-22): permisos sectoriales de Arqueros (pp. 209-225, sin el falso positivo de la p. 226) y de Albemarle (p. 67), participación ciudadana de Albemarle (pp. 14-49, confianza media) y la mención aislada de compromisos de Arqueros (p. 160). Etapa 4 en curso: Queltehue extraída y revisada por Ignacio (177 filas, 157 obligaciones distintas, 258 citas confirmadas, cobertura completa). Arqueros extraída el 2026-11-22 (289 filas, 234 obligaciones distintas, 353 citas confirmadas y 24 leídas en imagen en las pp. 166-167, cobertura completa de las pp. 146-228); revisada por Ignacio. Albemarle extraída el 2026-11-22 y actualizada el 2026-11-23 con el localizador 0.4.1 (62 filas, 56 obligaciones distintas; 46 citas OCR confirmadas por código y 40 leídas en imagen en las tablas del plan de seguimiento; p. 52 no leída por ilegible; cobertura completa de las pp. 51-72). La tabla resumen de las pp. 61-63 se comparó celda por celda con la tabla principal: solo la fila Columna de agua (p. 62) difiere y se registró como OBL-027; pendiente la revisión de Ignacio. Localizador 0.3.1: tramos aislados y títulos sin espacios internos. salida/secciones/ regenerado y fichas revalidadas sin cambios en sus rangos. Queda abierto: contingencias de Pampa Hermosa sin ubicar (decisión de Ignacio: dejarlo así).
- Etapa 4: leer con visión las páginas escaneadas dentro de los rangos de obligaciones: Arqueros pp. 166-167 (medidas; hecho, fuente "imagen"); Albemarle p. 52 (medidas): reintentada a 200 dpi y con contraste aumentado, sigue ilegible; registrada como no leída.
- Resuelto en el localizador 0.4.1 (2026-11-23): el plan de seguimiento de Albemarle se cortaba en la p. 58 por una celda de tabla ("23. LP-24 ...") leída como título; ahora va de la p. 53 a la p. 64.
- Etapa 4: considerar la revisión manual que hace Ignacio de las páginas que marcó el localizador.
- Resuelto el 2026-11-23 (pedido por Ignacio el 2026-11-23): agregado el tipo "trámite o aprobación ante la autoridad" (sección 8, skill extraer-obligaciones, plantilla con tipos_permitidos, validador y pruebas). Reclasificadas, con aprobación de Ignacio, 36 filas: Queltehue 9, Arqueros 21 y Albemarle 6 (solo cambia el campo tipo). Las filas "condición de PAS" y "forma de cumplimiento de normativa" conservan su tipo aunque sean trámites. Pedido original: agregar el tipo "trámite o aprobación ante la autoridad" (sección 8, skill extraer-obligaciones, plantilla y validador). "Reporte o informe a la autoridad" queda solo para informes periódicos o por evento. Reclasificar las filas que correspondan en Queltehue, Arqueros y Albemarle (ejemplos de Arqueros: OBL-166, 248, 253, 258 y 282), mostrando a Ignacio la lista de cambios antes de aplicarlos.
- Resuelto el 2026-11-23 con scripts/muestra_auditoria.py (prueba en tests/test_muestra_auditoria.py): muestra de 20 de las 528 filas con la semilla 20261123, sorteadas en el orden Queltehue, Arqueros, Albemarle (9, 9 y 2 filas según el CSV; el 2026-11-24 se corrigió aquí el conteo anterior «9, 8 y 3», que estaba mal); queda en salida/verificacion/muestra_auditoria_20261123.csv. Revisión de la muestra (2026-11-23): 5 filas corregidas con aprobación de Ignacio (Queltehue OBL-031 descripción, OBL-063 plazo, OBL-104 cita adicional de la p. 78; Arqueros OBL-001 cita adicional de la p. 147, OBL-158 cita principal en la p. 176 y citas adicionales en la p. 177). Búsqueda de plazos "No consta" con palabras de tiempo en la cita (72 filas): 18 corregidas (Queltehue 9 plazos "De inmediato" y 2 hitos; Arqueros 5 plazos, 1 hito y 1 parámetro, OBL-187); Arqueros OBL-102 y los momentos "antes de / previo a" quedan en hito_o_gatillo; "durante la fase" y falsos positivos sin cambios. La skill exige ahora una cita por cada dato de la descripción (citas_adicionales también en filas no agrupadas). Revisión de sustantivos en las filas "forma de cumplimiento de normativa" de Queltehue: OBL-023 (Formulario 138 y certificado, en la p. 59) y OBL-026 (4 barreras modulares fijas, en la p. 60) tenían datos de la página anterior sin cita; con aprobación de Ignacio se agregó a cada una la cita adicional de esa página (OBL-023 p. 59, OBL-026 p. 60). Pendiente: la auditoría de Ignacio contra el PDF. Pedido original: tabla de 20 obligaciones al azar entre Queltehue, Arqueros y Albemarle, con semilla fija anotada, para que Ignacio las audite contra el PDF. Columnas: ID, página, tipo, descripción, plazo, autoridad y cita textual.
- Etapa 7: cuando exista la hoja Verificación, cada página de control.paginas_no_leidas debe aparecer ahí como alerta (hoy se informa en Léeme). Albemarle p. 52 ya no es no leída: está en blanco, verificada por Ignacio el 2026-11-23 (ver "Pendientes abiertos de Albemarle").

- Resuelto el 2026-11-23 (pedido por Ignacio): columnas opcionales enlace_eseia y nota_uf en el manifiesto (los manifiestos sin ellas siguen sirviendo). La hoja Resumen muestra enlace_eseia con hipervínculo para las tres RCAs de ejemplo (Queltehue: expediente 2163162600, verificado por Ignacio; Arqueros y Albemarle, de FUENTES.md, que ahora incluye también el de Queltehue). El Índice UF muestra nota_uf: Queltehue queda como SIN UF ASIGNADA con la nota "No encontrada en SNIFA al 2026-11-23 (consulta de Ignacio Figueroa)."

Cierre de la Etapa 4 (2026-11-23): cerrada, con auditoría humana pendiente.

Pendientes de Ignacio:
- (a) Resuelto el 2026-11-24 (Ignacio: «todo ok»; registradas como confirmadas): verificar contra el PDF las 26 filas de Albemarle leídas en imagen (OBL-002 a OBL-027; citas en las pp. 53-62, páginas revisadas en imagen 53-63).
- (b) Resuelto el 2026-11-24: 20 de 20 calzan con el PDF (Ignacio: «todo ok»; registradas como confirmadas). Auditar las 20 filas de la muestra con semilla 20261123 (salida/verificacion/muestra_auditoria_20261123.csv; la versión anterior a las correcciones es muestra_auditoria_20261123_antes.csv) y registrar aquí cuántas calzan con el PDF.

Pendientes abiertos de Albemarle:
- Resuelto el 2026-11-24: p. 52. Ignacio revisó el PDF el 2026-11-23 y la página está en blanco (antes figuraba como no leída por ilegible, escaneo de unos 72 dpi). Registro aplicado con la opción B, elegida por Ignacio, con respaldo previo en salida/respaldos/salida_20261124_antes_p52/: en las obligaciones pasa de control.paginas_no_leidas a control.paginas_sin_obligaciones con el motivo "Página en blanco, verificada por Ignacio el 2026-11-23."; en la ficha sale de control.paginas_no_leidas (la ficha no tiene lista de páginas sin obligaciones) y sigue en paginas_escaneadas, como exige el validador. Se reescribieron las observaciones_generales de la ficha y de las obligaciones y la nota de OBL-001, que decían "no leída" o "ilegible". Ya no aparece como alerta en el alcance de las consultas, en la columna paginas_no_leidas del Índice UF, en Léeme ni en la hoja Menciones en texto. Cobertura de Albemarle: 17 páginas citadas, 5 leídas sin obligaciones, 0 no leídas. Queda una advertencia del validador de obligaciones («p. 52: escaneada y listada sin obligaciones; confirmar que se leyó con visión»), que se responde con la verificación de Ignacio. Mejora posible para la Etapa 9 (opción A, no aplicada): un campo propio control.paginas_en_blanco en la ficha y en las obligaciones, con página, quién la verificó y fecha, reconocido por los validadores, la búsqueda y el Excel como información y no como alerta.
- Verificado por Ignacio el 2026-11-23 contra el PDF: el resumen de las menciones sin obligación de la consulta de humedales en Albemarle (salida/consultas/consulta_humedales_20261123-235241) coincide con las pp. 17 (la consulta al titular sobre las lagunas Salada, Saladita e Interna «en su calidad de» ecosistemas lacustres) y 43 (artículos 58 y 63 del Código de Aguas sobre los acuíferos que alimentan vegas y bofedales, y «los humedales atacameños que usa Peine»).
- Borrada el 2026-11-24, a pedido de Ignacio: la consulta consulta_humedales_20261123-235234, que corrió con un manifiesto.csv inexistente (todo quedó como "SIN UF ASIGNADA"). Desde ahora buscar_palabras.py consultar usa ejemplos/manifiesto_ejemplo.csv cuando no existe manifiesto.csv, y lo avisa; si no hay ninguno, o si no existe el manifiesto indicado con --manifiesto, no guarda nada (pruebas en tests/test_buscar_palabras.py).
- Resuelto el 2026-11-23 (Etapa 5): las pp. 51 y 65-71 se revisaron en la imagen; todas las citas de obligaciones coinciden y ninguna obligación queda "Solo OCR". Única diferencia en una cita: OBL-053 (p. 69), "60 I/s" en el OCR y "60 l/s" en la imagen (correccion_ocr). Fuera de citas: p. 51 "-TOS-" (imagen "-TDS-") y p. 68 "Sistema Sanear" (imagen "Sistema Soncor").
- Medida de mitigación de Albemarle (OBL-001, p. 51): la p. 51 no trae cifra. Las cifras constan en la descripción del proyecto (p. 9: de 600 a 300 l/s como promedio anual adicional, incrementos semestrales de 60 l/s, total 442 l/s) y en las pp. 21 y 27. No se agregaron a la obligación: pendiente la decisión de Ignacio. La p. 51 letra d) es descriptiva (Ignacio, 2026-11-23): queda como mención sin obligación.
- Dudas de la p. 36 (Convenio 169): la ficha reproduce que el Convenio 169 de la OIT aún no entraba en vigencia al ingresar el EIA; falta la revisión de Ignacio.
- Registro de otras razones sociales del titular: la ficha registra a Rockwood Litio Limitada; Sociedad Chilena de Litio Ltda., "Sociedad Chile de Litio Ltda." y Rockwood Litio Ltda. constan solo en observaciones_generales. Falta decidir si se registran en un campo propio.

Alcance congelado (Ignacio, 2026-11-24): después de las mejoras 1 a 3, solo trabajo que corrija errores, el README y la publicación. Mejora 1 hecha (2026-11-24): scripts/respaldar_salida.py (respaldo con fecha y motivo de obligaciones/, fichas/, consultas/, verificacion/ y el Excel, en salida/respaldos/salida_AAAAMMDD-HHMMSS_<motivo>/, con respaldo.json y SHA-256 de cada archivo; omite texto/, imagenes/ y secciones/, que se regeneran desde los PDF; --listar; nunca borra respaldos), hook PreToolUse en .claude/settings.json (antes de un Edit/Write en una carpeta protegida de salida/, respalda si no hay un respaldo de los últimos 30 minutos; nunca bloquea; usa el python3 del sistema) y la sección "Cómo trabajamos (reglas permanentes)" de CLAUDE.md, repetida en las tres skills. Primer respaldo: salida/respaldos/salida_20261124-002214_mejora_1_respaldo_inicial (28 archivos, 1,7 MB). CLAUDE.md corrige además que salida/ "se puede borrar y regenerar": obligaciones/, fichas/, consultas/ y verificacion/ no se regeneran.

Decisiones y mejora 2 (2026-11-24; respaldo previo salida/respaldos/salida_20261124-002831_antes_de_pajonal_confirmado_arqueros_p_189_y_mejora_2): (1) Pajonal: Ignacio confirmó en el PDF OBL-064 y OBL-065; se quitó "dudosa" y su nota en salida/consultas/relaciones_aprobadas/pajonal.json (quedan con "confirmada_por_ignacio"). (2) Arqueros p. 189 aplicada según la propuesta: OBL-290 (profesionales con experiencia en la Región de Atacama; literal en flora_y_fauna por «rescate y relocalización de fauna») y OBL-291 (ejemplares a colecciones herpetológicas o de micromamíferos; relación temática flora_y_fauna por «colecciones herpetológicas o de micromamíferos», p. 189, agregada para que temas_relacionados_revisados siga siendo cierto: revisar), ambas tipo plan de seguimiento o monitoreo, fase No consta, responsable Titular con confianza media; OBL-189 pierde la cita adicional y vuelve a la relación temática «áreas escogidas para la relocalización de la herpetofauna, antes de liberar animales». Arqueros: 291 obligaciones; validar_obligaciones.py: válidas. (3) Mejora 2: columna opcional prefijo_id del manifiesto (2 a 5 letras mayúsculas, única por RCA; el ejemplo usa QUE, ARQ y ALB) y scripts/ids_visibles.py; ID visible (ARQ-024) en la hoja Obligaciones (id_visible antes del ID interno; posible_duplicado y duplicado_de también con prefijo), en las consultas (columna id_visible) y en la skill; buscar_palabras.py obligacion <ID> muestra una fila por ID visible o interno. Revisión humana: scripts/registrar_revision.py (planilla, importar con simulación y --aplicar con respaldo, resumen) y registro salida/revision/revision_humana.csv (vale la última revisión; se conserva el historial; no toca salida/obligaciones/); la hoja Obligaciones agrega revision_estado, revision_fecha, revision_por y revision_comentario (pendiente si no hay revisión) y el Índice UF filas_revisadas y filas_confirmadas. salida/revision/ se respalda y la protege el hook. (4) Auditorías de Ignacio («auditorías hechas: todo ok») registradas como confirmadas con las planillas salida/revision/planillas/planilla_auditoria_muestra_20261123_20261124-003528.csv (20) y planilla_auditoria_albemarle_leidas_en_imagen_20261124-003528.csv (26; OBL-012 está en ambas): 45 obligaciones confirmadas (Queltehue 9, Arqueros 9, Albemarle 27).

Mejora 3 hecha (2026-11-24): el Excel tiene dos hojas de obligaciones con las mismas filas: "Obligaciones" (vista compacta, §9 punto 3) y "Obligaciones detalle" (todas las columnas de antes, ahora con id_visible en la primera columna). Probado con los datos reales en una copia temporal: 530 filas, 45 confirmadas y 485 pendientes. El Excel real no se regeneró (se regenera a pedido de Ignacio). Con esto se cierran las mejoras 1 a 3: según el alcance congelado, queda solo corregir errores, el README y la publicación.

Cierre de las mejoras (2026-11-24): Excel de salida/ regenerado con las mejoras 2 y 3 (no estaba abierto; respaldo previo salida/respaldos/salida_20261124-004544_antes_de_regenerar_el_excel_con_las_mejoras_2_y_3). Ignacio aprobó la relación temática de ARQ-291 (OBL-291) con flora_y_fauna («colecciones herpetológicas o de micromamíferos», p. 189), que se mantiene marcada "revisar" (sin cambios en los datos). Etapa 10, decisiones de Ignacio: no se suben los PDF de las RCAs (el manifiesto de ejemplo y FUENTES.md tienen los enlaces al e-SEIA); no hace falta revisión manual de datos personales (datos públicos del e-SEIA y SNIFA; proyecto personal), solo un escaneo automático informativo. Escaneo del 2026-11-24 sobre los 57 archivos publicables (sin PDF): 4 correos, 1 teléfono y 4 RUT, todos ejemplos inventados en scripts/revisar_datos_personales.py y tests/test_revisar_datos_personales.py. Hallazgo: los 3 PDF de ejemplos/rcas_publicas/ están en el repositorio y en su historial (commits 2314174 y 03270a5): sacarlos del último commit no basta; pendiente la decisión de Ignacio sobre cómo publicar sin ese historial.

Etapa 9 (2026-11-24, plan aprobado por Ignacio): README.md para abogados (qué es, requisitos, instalación A plugin desde GitHub y B carpeta del proyecto, carpeta de trabajo y manifiesto, proceso manual en dos pasos fichar-rca y extraer-obligaciones sin prometer un comando único, skills, hojas del Excel, ejemplos sin PDF, calidad con cifras: 530 obligaciones, auditoría manual de 26 filas de Albemarle leídas en imagen y de la muestra de 20 con semilla 20261123, todas coincidentes; revisión asistida previa por Claude con problemas en 5 de las 20 filas, corregidos; 45 confirmadas de 530; sin porcentaje de exactitud general; límites y próximos pasos) y LICENSE (MIT). Las skills ofrecen preparar el entorno de Python (<raíz>/.venv con requirements.txt) solo con el OK del usuario, en vez de detenerse. Los PDF de ejemplos/rcas_publicas/ salen del repositorio (git rm --cached; siguen en la carpeta local y en .gitignore); CLAUDE.md regla 6 y FUENTES.md actualizados. Etapa 10, decisión de Ignacio: publicar un repositorio nuevo con un solo commit inicial (sin el historial, que contiene los PDF); el repositorio local conserva su historial.

Etapa 10 (2026-11-24): publicado en https://github.com/mfigueroa89/asistente-compliance-ambiental (público; 1 commit 6fa1984, 59 archivos, sin PDF ni salida/; comprobado desde fuera). Un primer intento con GitHub Desktop publicó la carpeta de trabajo con todo su historial (incluidos los PDF), pero quedó privado; Ignacio lo borró y publicó la carpeta ~/Desktop/asistente-compliance-ambiental. Se quitó la conexión (origin) de la carpeta de trabajo, para que su historial no vuelva a subirse: las publicaciones se hacen desde la carpeta del Escritorio. Prueba del modo plugin con la copia descargada de GitHub: entorno creado con el comando que ofrecen las skills; leer_pdf.py, localizar_secciones.py, buscar_palabras.py (consultar y obligacion), respaldar_salida.py y exportar_excel.py funcionan desde una carpeta de trabajo aparte (config/ y el manifiesto de ejemplo se toman del plugin; los resultados quedan en salida/ de la carpeta de trabajo). Error corregido: el aviso de RCA sin obligaciones remitía a la skill procesar-carpeta, que no existe; ahora remite a fichar-rca y extraer-obligaciones. Pendiente: la instalación del plugin desde la app (la hace Ignacio; Claude no puede usar la interfaz de la app por él).

Etapa 10 cerrada (2026-11-24): segundo commit publicado (aviso de RCA sin obligaciones y catálogo "compliance-ambiental"). Instalación probada por Ignacio desde la app de escritorio (Mac): catálogo de GitHub mfigueroa89/asistente-compliance-ambiental, plugin instalado, entorno nuevo Local con una sola carpeta ("RCAs prueba"); `/` muestra las tres skills con el prefijo asistente-compliance-ambiental:; "prepara el entorno del asistente" ubicó la carpeta del plugin (~/.claude/plugins/cache/compliance-ambiental/asistente-compliance-ambiental/0.1.0), pidió autorización y creó .venv (pymupdf 1.28.2, openpyxl 3.1.5, pyyaml 6.0.4, pytest 9.2.0); con el PDF de Albemarle movido a rcas/ y renombrado como en el manifiesto de ejemplo (mismo SHA-256), la lectura y el localizador dieron lo mismo que en el proyecto (72 páginas con OCR previo, p. 52 para lectura visual, 17 páginas para la ficha y 22 para obligaciones; compromisos voluntarios no ubicada). README ajustado con los pasos reales de la app, la carpeta rcas/ con el nombre exacto, el entorno que se pierde al actualizar el plugin y el resultado de la prueba. Opcional pendiente: fichar Albemarle en la carpeta de prueba y compararla con la ficha aprobada.

Dónde viven las correcciones: las de la Etapa 5 (citas adicionales, descripción de Arqueros OBL-001, revisión en imagen de Albemarle y correccion_ocr de OBL-053) también viven solo en salida/obligaciones/. Todas las correcciones de la Etapa 4 (reclasificación al tipo "trámite o aprobación ante la autoridad", plazos e hitos, citas adicionales y las correcciones de la muestra) viven solo en salida/obligaciones/, que está en .gitignore y no se sube a GitHub. No se debe reextraer ninguna RCA desde cero sin revisar antes la lista de correcciones registrada en esta sección 12.1, porque una extracción nueva las perdería.

## 13. Plugin, README y GitHub

- plugin.json (en .claude-plugin/): nombre en kebab-case "asistente-compliance-ambiental", nombre visible, versión 0.1.0, descripción en español, autor Ignacio Figueroa Moya.
- README.md para un abogado que no programa: qué es, qué problema resuelve, requisitos, cómo instalarlo, cómo usarlo paso a paso, ejemplo de resultado, medición de calidad, limitaciones, aviso de revisión por abogado y fuentes (documentos públicos del e-SEIA).
- .gitignore: rcas/, salida/, .venv/, .env, __pycache__/, *.pyc, .DS_Store
- Licencia: MIT, salvo que yo indique otra.
- Repositorio público en GitHub. ejemplos/rcas_publicas/ incluye hasta 3 RCAs públicas (< 10 MB c/u), y el README indica el enlace de origen de cada una en el e-SEIA.
- La revisión de datos personales se hace con scripts/revisar_datos_personales.py (búsqueda por código de RUT, correos, teléfonos y domicilios, con página) más la verificación del contexto de cada hallazgo.
- Antes de subir un PDF, revisión de datos personales. Es normal en una resolución pública: nombres de titular, representante legal y autoridades, y firmas. No es normal, y se avisa: RUT de personas naturales ajenas al proyecto, domicilios particulares, teléfonos o correos personales, o datos de salud.
- Criterio adoptado: los nombres de personas naturales que formularon observaciones en el proceso de participación ciudadana se aceptan como parte normal de una RCA con participación ciudadana (así las publica el SEA). Los correos institucionales de funcionarios en la lista de distribución también se aceptan.

## 14. Backlog (después del MVP)

- Cruce automático con SNIFA: tomar la UF y comparar las obligaciones de la RCA con los hallazgos de los informes de fiscalización.
- Lectura de procesos sancionatorios y formulación de cargos.
- Detección de cambios entre una RCA y sus modificaciones o resoluciones posteriores.
- Alertas de plazos próximos a vencer (calendario).
- Interfaz web sencilla.
