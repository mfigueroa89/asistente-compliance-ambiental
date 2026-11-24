# Fuentes de las RCAs de ejemplo

Documentos públicos del Sistema de Evaluación de Impacto Ambiental (SEIA). **Los PDF no están en el repositorio**: descárguelos desde el enlace de cada fila (en el expediente, la resolución de calificación ambiental), guárdelos en esta carpeta con el nombre de la columna Archivo y compare su SHA-256. El número, la fecha y el órgano de cada resolución se verificaron visualmente en la primera página del PDF.

| Archivo | Resolución | Proyecto y titular | Instrumento | Páginas | Enlace de origen | SHA-256 |
|---|---|---|---|---|---|---|
| rca_202513001415_queltehue_rm.pdf | Res. Ex. N° 202513001415, 20-11-2025, Comisión de Evaluación Región Metropolitana | Parque Fotovoltaico Queltehue; Queltehue SpA | DIA | 98 | https://firma.sea.gob.cl/publicaciones/2025/11/21/1763760937_2166936831 (descargado 2026-11-19); ficha del expediente en el e-SEIA: https://seia.sea.gob.cl/expediente/ficha/fichaPrincipal.php?modo=normal&id_expediente=2163162600 (verificada por el autor el 2026-11-23) | 5723cf4ba1b6843f57170e92c7e0752dc455225b913a6517d5258ad86b8b768a |
| rca_151_2013_arqueros_atacama.pdf | Res. Ex. N° 151, 05-07-2013, Comisión de Evaluación III Región de Atacama | Proyecto Arqueros; Laguna Resources Chile Ltda. | EIA | 228 | https://seia.sea.gob.cl/expediente/ficha/fichaPrincipal.php?modo=normal&id_expediente=6441836 (ficha del expediente en el e-SEIA) | a2d169f43f3cad80ae7a1e3e66a8a3602cb9f4594fd267eb2687487427803494 |
| rca_021_2016_albemarle_salar_atacama.pdf | Res. Ex. N° 0021, 20-01-2016, Comisión de Evaluación II Región de Antofagasta | EIA Modificaciones y Mejoramiento del Sistema de Pozas de Evaporación Solar en el Salar de Atacama; Sociedad Chilena de Litio Ltda. | EIA | 72 | https://seia.sea.gob.cl/expediente/ficha/fichaPrincipal.php?modo=normal&id_expediente=3788682 (ficha del expediente en el e-SEIA) | 8f67f985b2568f17df554ad3bc775f5d8665ea3a8a0b71f5fa46666db56249b3 |

Arqueros y Albemarle provienen del archivo de investigación del autor (RCAs del e-SEIA reunidas en 2024); el enlace de cada uno es la ficha de su expediente en el e-SEIA, verificada por el autor.

Notas sobre cada documento:
- Queltehue: firmada electrónicamente; el número y la fecha solo se ven en la imagen de la página 1 (el texto dice "<NUM_RES>").
- Arqueros: texto digital; las páginas 60, 166 y 167 son imágenes sin texto.
- Albemarle: escaneo con OCR previo en sus 72 páginas (calidad variable, por ejemplo "Servido" por "Servicio"); la página 52 no tiene texto y su imagen es casi ilegible (registrada como página en blanco).

El SHA-256 es una "huella digital" del archivo: permite comprobar que el PDF que usted descargó es idéntico al que se usó en este proyecto.

## Revisión de datos personales (regla 6), 2026-11-19

Revisión hecha con `scripts/revisar_datos_personales.py` y verificación manual del contexto de cada hallazgo:
- Queltehue: RUT de la sociedad titular y RUT, nombre y correo del representante legal (p. 1 y lista de distribución, p. 97); correos de funcionarios en la lista de distribución. Se aceptan como parte normal de una resolución pública (criterio en ESPECIFICACION.md, sección 13).
- Arqueros: sin RUT de personas, correos ni teléfonos. El único "RUT" detectado es el código BNA de una estación fluviométrica de la DGA (p. 85). Las páginas 60, 166 y 167 no tienen texto y no se pudieron revisar por código.
- Albemarle: sin correos ni teléfonos. El único RUT es el de la Comunidad Indígena Atacameña de Toconao (persona jurídica, p. 14). Por ser OCR, la revisión por código es menos confiable; la página 52 no tiene texto.
