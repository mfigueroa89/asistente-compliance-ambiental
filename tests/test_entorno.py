"""Prueba de entorno (Etapa 0).

Comprueba que las librerías del proyecto están instaladas y funcionan:
- PyMuPDF puede crear un PDF en memoria y volver a leer su texto.
- openpyxl puede crear un Excel en memoria.
- PyYAML puede leer un texto con formato YAML (como config/temas.yaml).
"""

import io


def test_pymupdf_crea_y_lee_pdf():
    import pymupdf

    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), "Resolucion de Calificacion Ambiental de prueba")
    datos = documento.tobytes()
    documento.close()

    leido = pymupdf.open(stream=datos, filetype="pdf")
    assert leido.page_count == 1
    assert "Calificacion Ambiental" in leido[0].get_text()
    leido.close()


def test_openpyxl_crea_excel():
    import openpyxl

    libro = openpyxl.Workbook()
    libro.active["A1"] = "Requiere revisión de un abogado"
    salida = io.BytesIO()
    libro.save(salida)
    assert salida.getbuffer().nbytes > 0


def test_pyyaml_lee_temas():
    import yaml

    temas = yaml.safe_load("humedales:\n  - humedal\n  - bofedal\n")
    assert temas == {"humedales": ["humedal", "bofedal"]}
