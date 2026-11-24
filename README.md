# Asistente de Compliance Ambiental

> **Herramienta de apoyo. Requiere revisión de un abogado.**
> El asistente extrae y ordena lo que dicen las resoluciones; no emite opiniones jurídicas ni evalúa cumplimiento.

Un asistente para abogados y equipos de cumplimiento que revisan **Resoluciones de Calificación Ambiental (RCA)** chilenas. Funciona dentro de **Claude Code** (la aplicación de Claude para trabajar con archivos) y, a partir del PDF de una RCA:

1. **Ficha la RCA**: número, fecha, órgano, titular, proyecto, tipología, efectos del artículo 11, permisos sectoriales, áreas sensibles y otros datos, cada uno con su página y una cita textual.
2. **Extrae las obligaciones de compliance**: condiciones, compromisos voluntarios, medidas, planes de seguimiento, reportes a la SMA y otras, una por fila, con tipo, fase, plazo o frecuencia, responsable, autoridad, página y cita. Es el centro del asistente.
3. **Consulta las obligaciones por tema o palabra** ("¿qué obligaciones hay sobre humedales?"), separando lo que dice literalmente el texto de lo que es una interpretación a revisar.
4. **Genera un Excel** organizado por unidad fiscalizable (el concepto que usa la SMA en SNIFA) y por proyecto.

Es un proyecto personal de demostración, hecho para una postulación laboral. No es un producto comercial.

---

## Qué hace distinto

- **Nunca inventa datos.** Si algo no está en el documento, el valor es "No consta".
- **Todo dato lleva su página del PDF y una cita textual**, y un programa comprueba que cada cita esté realmente en esa página.
- **La búsqueda de palabras la hace un programa, no la IA**: es exacta y repetible (sin distinguir mayúsculas, tildes ni plural simple). La IA se usa para leer, interpretar y ordenar.
- **Tres resultados separados en cada consulta**: *coincidencia literal* (el término está en la cita de la obligación), *relación temática (revisar)* (una interpretación, con las palabras del PDF que la motivan) y *mención sin obligación* (el término aparece en la RCA, pero fuera de toda obligación). Cada resultado informa su **alcance**: qué se buscó y qué páginas no se pudieron revisar.
- **Revisión humana registrada**: cada obligación puede marcarse como confirmada, corregida o descartada por el abogado, con fecha y nombre.

---

## Requisitos

- La aplicación de escritorio de Claude (pestaña **Code**) o Claude Code en la terminal, con una cuenta de Claude. No se necesita ninguna clave de API ni pagos aparte: todo el trabajo lo hace Claude dentro de la sesión.
- **Python 3** (versión 3.10 o superior) instalado en el computador. En Mac suele venir instalado; si no, se descarga desde [python.org](https://www.python.org/downloads/). En Windows, al instalarlo, marque "Add Python to PATH".
- Mac o Windows.

---

## Instalación

### Opción A (recomendada): instalar el plugin desde GitHub

Probada el 24-11-2026 en Mac, con la aplicación de escritorio.

1. **Instalar el plugin.** En la aplicación de Claude, pestaña **Code**, haga clic en **+** (junto al cuadro de mensaje) y entre a **Plugins**. Agregue el catálogo (marketplace) de GitHub `mfigueroa89/asistente-compliance-ambiental` (https://github.com/mfigueroa89/asistente-compliance-ambiental); aparece como **compliance-ambiental**. Instale el plugin **asistente-compliance-ambiental**.
2. **Preparar su carpeta de trabajo.** En el Finder (o el Explorador de Windows), cree una carpeta para sus RCAs, por ejemplo `Mis RCAs`, con una subcarpeta `rcas` donde dejará los PDF (ver [Su carpeta de trabajo](#su-carpeta-de-trabajo)).
3. **Abrir una sesión en esa carpeta.** En **Code**, cree un entorno nuevo de tipo **Local** (en su computador, no en la nube) cuya única carpeta sea la de sus RCAs, y abra una sesión en él. Si la lista de carpetas incluye otras, quítelas.
4. **Comprobar las skills.** Escriba `/` en el cuadro de mensaje: deben aparecer **asistente-compliance-ambiental:fichar-rca**, **…:extraer-obligaciones** y **…:consultar-obligaciones**.
5. **Preparar el entorno, una sola vez.** Escriba **"prepara el entorno del asistente"**. Claude le explica que debe crear el entorno de Python del asistente (las bibliotecas para leer PDF y crear el Excel, descargadas de PyPI, el repositorio oficial de Python) y lo hace solo si usted lo autoriza; la aplicación también puede pedirle aprobar el comando. Tarda alrededor de un minuto y termina confirmando que las bibliotecas cargan. Si Claude no reconoce la petición, escriba `/asistente-compliance-ambiental:fichar-rca prepara el entorno del asistente`.

El entorno queda dentro de la carpeta de la versión instalada del plugin: **si actualiza el plugin, vuelva a pedir "prepara el entorno del asistente"**.

Para desinstalar: **+ › Plugins › Manage plugins**.

### Opción B: descargar el proyecto y abrir su carpeta

1. Descargue el repositorio (botón **Code › Download ZIP** en GitHub) y descomprímalo.
2. En la aplicación de Claude, pestaña **Code**, abra una sesión **Local** en esa carpeta. Las skills quedan disponibles como skills del proyecto (en `/` aparecen como **fichar-rca**, **extraer-obligaciones** y **consultar-obligaciones**).
3. Escriba **"prepara el entorno del asistente"**, igual que en la opción A.

En Windows, la opción B puede no reconocer las skills (usa enlaces de carpeta que Windows no siempre conserva); en ese caso use la opción A.

---

## Su carpeta de trabajo

```
mi-carpeta/
├── rcas/              aquí van los PDF de las RCAs (uno por RCA)
├── manifiesto.csv     una fila por cada par RCA–unidad fiscalizable
└── salida/            lo crea el asistente: fichas, obligaciones, consultas, respaldos y el Excel
```

**manifiesto.csv** se abre y edita en Excel (guárdelo como "CSV UTF-8"). Columnas obligatorias: `archivo` (nombre exacto del PDF), `unidad_fiscalizable` (nombre según SNIFA) y `proyecto`. Opcionales: `id_uf_snifa`, `enlace_uf_snifa`, `titular`, `region`, `notas`, `enlace_eseia`, `nota_uf` y `prefijo_id` (2 a 5 letras, por ejemplo ARQ, para que las obligaciones se vean como ARQ-024). Una misma RCA puede estar en varias unidades fiscalizables, en filas distintas. Hay un modelo en [`ejemplos/manifiesto_ejemplo.csv`](ejemplos/manifiesto_ejemplo.csv).

---

## Cómo procesar una RCA nueva (hoy, en dos pasos)

Hoy el proceso es manual y en dos pasos; todavía **no existe un comando único** que procese una carpeta completa.

1. Deje el PDF dentro de `rcas/` (no suelto en la carpeta) y agregue su fila en `manifiesto.csv`, con el nombre del archivo escrito exactamente igual. Sin `manifiesto.csv`, las consultas usan el manifiesto de ejemplo y lo avisan, y el Excel necesita que se le indique uno; una RCA que no figure en el manifiesto queda como "SIN UF ASIGNADA".
2. **Paso 1, ficha.** En una sesión nueva escriba, por ejemplo: *"ficha la RCA rcas/rca_151_2013_arqueros_atacama.pdf"*. Claude lee el PDF (y la imagen de las páginas escaneadas), ubica las secciones relevantes, escribe la ficha y la valida. Revise lo que le muestra.
3. **Paso 2, obligaciones.** En otra sesión nueva: *"extrae las obligaciones de rca_151_2013_arqueros_atacama"*. Claude lee sección por sección, registra cada obligación con su página y cita, y comprueba que todas las páginas de las secciones de obligaciones quedaron revisadas.
4. Cuando quiera el Excel: *"genera el Excel"*. El Excel solo se regenera cuando usted lo pide.

Se trabaja **una RCA por sesión**: así cada sesión tiene a la vista una sola resolución y es más fácil revisar su resultado. Una RCA de 300 o 500 páginas no se lee completa: el asistente ubica primero las secciones (medidas, compromisos, plan de seguimiento, condiciones, contingencias, permisos sectoriales y parte resolutiva) y lee esas páginas.

---

## Uso: lo que puede pedir

| Skill | Ejemplos de lo que puede escribir |
|---|---|
| **fichar-rca** | "ficha la RCA rcas/X.pdf" |
| **extraer-obligaciones** | "extrae las obligaciones de X", "revisa las obligaciones de la página 150" |
| **consultar-obligaciones** | "¿qué obligaciones hay sobre humedales?", "busca 'pajonal' en Arqueros", "busca glaciares en la UF Planta Cloruro de Litio", "muéstrame ARQ-024" |

Además:
- **Excel**: "genera el Excel". Para incluir una consulta en el Excel, Claude se lo ofrece al terminar la consulta.
- **Revisión del abogado**: "dame una planilla para revisar ARQ-100 a ARQ-120". Usted la llena en Excel (confirmada, corregida o descartada, con comentario) y escribe "importa mi revisión"; Claude le muestra el resumen y la registra solo con su OK.
- **Respaldos**: "respalda salida" o "lista los respaldos". El asistente también respalda solo antes de modificar sus datos.
- **Temas de búsqueda**: los temas y sinónimos (humedales, recursos hídricos, pueblos indígenas, patrimonio cultural, flora y fauna, áreas protegidas, glaciares) están en [`config/temas.yaml`](config/temas.yaml). Puede pedir "agrega 'pajonal hídrico' al tema humedales": Claude le muestra el efecto antes de cambiar nada.

### El Excel (`salida/compliance_ambiental.xlsx`)

| Hoja | Contenido |
|---|---|
| Léeme | Aviso, explicación de cada hoja y colores, avisos y páginas no leídas |
| Índice UF | Una fila por unidad fiscalizable: RCAs, obligaciones, filas revisadas y confirmadas |
| Resumen | Una fila por RCA, con el enlace a su expediente en el e-SEIA |
| Obligaciones | Vista compacta: ID, unidad, RCA, tipo, descripción, plazo, responsable, página y revisión |
| Obligaciones detalle | Todas las columnas: citas, temas, verificación de la cita, calidad del OCR, duplicados |
| Fichas | Una fila por dato de la ficha, con página, cita y fuente |
| Menciones en texto | Cada aparición de un término de los temas en el texto completo |
| Consulta | Las consultas que usted pidió agregar, la más reciente arriba |

---

## Ejemplos incluidos

El proyecto se probó con tres RCAs públicas del e-SEIA, elegidas por ser distintas entre sí:

| Proyecto | RCA | Por qué es un buen caso |
|---|---|---|
| Parque Fotovoltaico Queltehue (DIA) | N° 202513001415, 2025, Región Metropolitana | Firmada electrónicamente: el número y la fecha solo se ven en la imagen |
| Proyecto Arqueros (EIA) | N° 151, 2013, Región de Atacama | 228 páginas, con humedales (vegas y bofedales) y páginas escaneadas |
| Pozas de evaporación solar en el Salar de Atacama, Albemarle (EIA) | N° 21, 2016, Región de Antofagasta | Escaneo antiguo con OCR de calidad variable |

**Los PDF no están en el repositorio.** Los enlaces al e-SEIA, el nombre de archivo esperado y la huella (SHA-256) de cada uno están en [`ejemplos/rcas_publicas/FUENTES.md`](ejemplos/rcas_publicas/FUENTES.md). Para probar con un ejemplo, descargue el PDF y guárdelo en `rcas/` de su carpeta de trabajo **con el nombre exacto de FUENTES.md** (por ejemplo `rca_021_2016_albemarle_salar_atacama.pdf`): así el manifiesto de ejemplo lo reconoce, con su unidad fiscalizable y sus ID (ALB-001…). Cambiar el nombre no cambia el contenido: la huella SHA-256 sigue siendo la misma.

---

## Calidad: qué se midió y qué no

Con las tres RCAs de ejemplo:

- **530 obligaciones extraídas**: Queltehue 177, Arqueros 291 y Albemarle 62.
- **Citas comprobadas por código**: un programa verifica que cada cita (de la ficha y de las obligaciones) esté en la página indicada; las que no calzan se marcan en el Excel.
- **Auditoría manual del autor contra el PDF**, con todas las filas revisadas coincidiendo con el documento:
  - las **26 obligaciones de Albemarle leídas en la imagen** de tablas escaneadas (pp. 53 a 62);
  - una **muestra aleatoria de 20 obligaciones** de las tres RCAs (semilla 20261123, para que la muestra se pueda repetir). Antes de esa auditoría, una revisión asistida de la misma muestra (hecha por Claude) encontró problemas en **5 de las 20 filas** (una descripción, un plazo y citas que faltaban o estaban en otra página), que se corrigieron con aprobación del autor.
- **Hoy hay 45 obligaciones confirmadas por revisión humana, de 530.**
- **Búsqueda de términos**: se contrastó con la búsqueda del visor de PDF en las tres RCAs, sin omisiones (las diferencias se explican por palabras que contienen el término, como "flora" en "afloramiento", y por plurales de frases).

Esto es una **muestra pequeña**. No permite afirmar un porcentaje de exactitud general del asistente, y no se presenta ninguno.

**Instalación desde GitHub** (24-11-2026, Mac): con el plugin instalado desde la aplicación, el asistente preparó su entorno con autorización, leyó el PDF de Albemarle y ubicó sus secciones con el mismo resultado que en el proyecto original (72 páginas con OCR previo; 17 páginas para la ficha y 22 para obligaciones).

Las pruebas automáticas del código (236) se ejecutan con `pytest`. Las que usan las RCAs de ejemplo se omiten, con un aviso, si los PDF y sus resultados no están en la carpeta.

---

## Límites

- **El OCR puede leer mal.** En documentos escaneados, el texto que trae el PDF puede tener errores (por ejemplo "I/s" por "l/s"). El asistente lee la imagen de esas páginas, marca cada dato con su calidad ("OCR confirmado en la imagen", "solo OCR") y una búsqueda exacta no encuentra un término mal leído. Una página ilegible se informa como no leída.
- **La relación temática es una propuesta.** Cuando una obligación se relaciona con un tema sin nombrarlo literalmente, es una interpretación del asistente, siempre marcada "revisar", con las palabras del PDF que la motivan. Nunca se presenta como hecho.
- **Unidades fiscalizables**: el asistente no consulta SNIFA; el nombre de la unidad lo pone el usuario en el manifiesto.
- **Solo la resolución**: no analiza el EIA o la DIA completos, ni sus anexos ni adendas.
- **No evalúa cumplimiento** ni emite opiniones jurídicas.
- **Todo resultado requiere la revisión de un abogado.**

---

## Próximos pasos

- **Matriz de cumplimiento**: pasar de la lista de obligaciones a una matriz con estado, evidencia y responsable interno por obligación.
- **Verificación de unidades fiscalizables en SNIFA**: comprobar que cada RCA esté asociada a la unidad correcta y cruzar las obligaciones con fiscalizaciones y procesos sancionatorios.
- **Procesamiento de carpetas**: una sola instrucción que fiche y extraiga todas las RCAs nuevas de una carpeta, retomando donde quedó.

---

## Para quien quiera revisar el código

- `skills/`: las instrucciones que sigue Claude (fichar-rca, extraer-obligaciones, consultar-obligaciones).
- `scripts/`: los programas en Python que hacen el trabajo exacto (leer el PDF, ubicar secciones, buscar términos, verificar citas, respaldar, registrar la revisión y generar el Excel). Ninguno usa IA.
- `config/`: temas de búsqueda y la tabla de equivalencias del artículo 11 de la Ley 19.300 por reglamento del SEIA.
- `tests/`: pruebas automáticas.
- [`ESPECIFICACION.md`](ESPECIFICACION.md): la especificación completa y el registro de decisiones (sección 12.1).

## Fuentes y licencia

Los documentos de ejemplo son resoluciones públicas del Sistema de Evaluación de Impacto Ambiental ([e-SEIA](https://seia.sea.gob.cl)); los nombres de unidades fiscalizables provienen de [SNIFA](https://snifa.sma.gob.cl) (Superintendencia del Medio Ambiente).

Código bajo licencia MIT. Autor: Ignacio Figueroa Moya.

> **Herramienta de apoyo. Requiere revisión de un abogado.**
