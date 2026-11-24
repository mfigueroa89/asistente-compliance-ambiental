# Asistente de Compliance Ambiental (plugin de Claude Code)

## Qué estamos construyendo
Un plugin de Claude Code que procesa Resoluciones de Calificación Ambiental (RCA) chilenas en PDF y entrega:
1. una ficha estructurada por RCA,
2. una extracción de obligaciones de compliance (con plazos, responsables y página de origen), que es el CENTRO del asistente,
3. una consulta de esas obligaciones por tema o palabra clave (humedal, bofedal, etc.), con búsqueda exacta y relación temática marcada como "revisar",
4. un Excel organizado por unidad fiscalizable (concepto de SNIFA, SMA) y proyecto.

Es un proyecto personal de demostración. Debe verse profesional, funcionar de punta a punta con 2 o 3 RCAs reales y estar publicado en GitHub. No es un producto comercial.

La especificación completa está en ESPECIFICACION.md. Léela antes de proponer nada.

## Quién soy
Soy Ignacio, abogado especialista en derecho ambiental y regulatorio. No sé programar. Por eso:
- Explícame en simple qué hace cada archivo que creas y por qué.
- Antes de escribir código, muéstrame un plan corto y espera mi OK.
- Avanza por etapas pequeñas y probables. Después de cada etapa dime cómo verificar que funciona.
- Si tienes que elegir entre dos caminos, dime las opciones en una línea cada una y recomienda una.
- Si un paso me exige instalar algo, dame el comando exacto o instálalo tú, y dime qué es.
- Responde siempre en español de Chile, neutro y claro.

## Reglas del proyecto (no negociables)
1. Nunca inventar datos. Si algo no consta en el documento, el valor es "No consta". Nada de inferir ni completar de memoria.
2. Todo dato extraído lleva la página del PDF de donde salió y una cita textual breve de respaldo.
3. La búsqueda exacta de términos es determinista (código, sin IA). La IA se usa para interpretar y estructurar, no para buscar texto exacto. Toda relación entre una obligación y un tema que no aparezca literalmente se presenta como interpretación a revisar.
4. Solo se trabaja con documentos públicos (RCAs del e-SEIA). Nada de información confidencial de clientes.
5. No hay API key ni dinero de por medio: todo el trabajo "inteligente" lo hace Claude Code dentro de la sesión. No uses la API de Anthropic ni pidas claves.
6. Qué se sube a GitHub:
   - Sí se suben: el código, las skills, la configuración, las pruebas, la documentación, el manifiesto de ejemplo y ejemplos/rcas_publicas/FUENTES.md con el enlace al e-SEIA de cada RCA de ejemplo.
   - Nunca se suben: los PDF de las RCAs (tampoco los de ejemplos/rcas_publicas/; decisión de Ignacio, 2026-11-24: se descargan del e-SEIA), rcas/ (mi carpeta de trabajo), salida/, .venv/, archivos .env ni credenciales. Todo eso debe quedar en .gitignore.
   - Los datos de las RCAs son públicos (e-SEIA y SNIFA): antes de publicar basta un escaneo automático informativo de correos, teléfonos y RUT en los archivos que se suben, sin revisión manual. Nada se sube a GitHub sin el OK de Ignacio.
7. El sistema es apoyo al abogado, no reemplazo. Los resultados llevan el aviso "Requiere revisión de un abogado".

## Cómo trabajamos (reglas permanentes)
1. Mostrar antes de aplicar. Todo cambio de datos se presenta primero: qué archivo, qué fila o campo, valor antes y después.
2. Esperar el OK de Ignacio antes de modificar datos en salida/ o config/. Una aprobación vale para el cambio mostrado, no para otros.
3. Respaldar antes de modificar salida/. Antes de editar obligaciones/, fichas/, consultas/relaciones_aprobadas/ o verificacion/ (también con un script de Python), ejecutar `.venv/bin/python scripts/respaldar_salida.py --motivo "<motivo>"` y decir dónde quedó el respaldo. El hook de .claude/settings.json respalda solo antes de una edición directa (Edit/Write), como red de seguridad: no reemplaza esta regla. Ignacio puede pedir un respaldo en cualquier momento ("respalda salida") y la lista de respaldos ("lista los respaldos", con --listar).
4. Una RCA por sesión para fichar, extraer o corregir. Las consultas de solo lectura pueden abarcar varias RCAs.
5. No tocar el Excel sin que Ignacio lo pida: exportar_excel.py solo se ejecuta a pedido.
6. Cerrar cada respuesta con una sección "Pendientes": una línea por pendiente, con su responsable entre corchetes ([Ignacio] o [Claude]). Si no hay pendientes, decir "Pendientes: ninguno".

## Convenciones técnicas
- Python 3. Dependencias en requirements.txt. Scripts en scripts/. Un archivo, una responsabilidad.
- Entradas en rcas/ y manifiesto.csv (si no existe, se usa ejemplos/manifiesto_ejemplo.csv). Salidas en salida/. Ojo: texto/, imagenes/ y secciones/ se regeneran desde los PDF, pero obligaciones/, fichas/, consultas/ y verificacion/ tienen correcciones y decisiones de Ignacio que NO se regeneran (ver ESPECIFICACION.md §12.1): nunca se borran y se respaldan antes de modificarlas.
- Nombres de archivos y columnas en español, sin tildes en nombres de archivos.
- Los scripts reciben rutas por argumentos y funcionan en Windows y Mac. Ignacio trabaja en Mac (macOS, Apple Silicon); la compatibilidad con Windows se mantiene para quien instale el plugin desde GitHub.
- Cada script debe tener pruebas mínimas con pytest, en tests/. Las pruebas usan primero las RCAs de ejemplos/rcas_publicas/. El caso de página escaneada se prueba con un PDF sintético que las propias pruebas generan al ejecutarse.
- El README debe estar escrito para un abogado que no programa.

## Estructura del plugin
Ver sección 2 de ESPECIFICACION.md. La carpeta raíz de este proyecto ES la raíz del plugin. En la app de escritorio, las skills se usan como skills del proyecto: .claude/skills/<nombre> es un enlace a skills/<nombre>. Desde la terminal también se puede probar como plugin: claude --plugin-dir .
