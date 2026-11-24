"""Pruebas de scripts/verificar_citas.py (versión simple)."""

import verificar_citas as vc

PAGINAS = [
    {"numero_pdf": 1, "origen_texto": "digital", "texto": "Califica Ambientalmente el proyecto “Parque Fotovoltaico Queltehue”."},
    {"numero_pdf": 2, "origen_texto": "digital", "texto": "El titular deberá informar a la Superintendencia del Medio Ambiente\ndentro de 30 días."},
    {"numero_pdf": 3, "origen_texto": "ocr_previo", "texto": "Servido de Evaluaci6n Ambiental, Comisi6n de Evaluaci6n II Regi6n de Antofagasta."},
]


def test_cita_exacta_sin_tildes_ni_mayusculas():
    r = vc.verificar_cita("el TITULAR debera informar a la Superintendencia del Medio Ambiente dentro de 30 dias", 2, PAGINAS)
    assert r["estado"] == "confirmada"


def test_cita_en_otra_pagina():
    r = vc.verificar_cita("Parque Fotovoltaico Queltehue", 2, PAGINAS)
    assert r == {"estado": "encontrada en otra página", "similitud": 1.0, "pagina_encontrada": 1}


def test_cita_inexistente():
    r = vc.verificar_cita("el titular deberá compensar 40 hectáreas de bofedal", 2, PAGINAS)
    assert r["estado"] == "no encontrada en esa página"


def test_tolera_errores_de_ocr():
    # La cita correcta contra un texto de OCR con "6" en vez de "ó" y "Servido" en vez de "Servicio".
    r = vc.verificar_cita("Servicio de Evaluación Ambiental, Comisión de Evaluación II Región de Antofagasta", 3, PAGINAS)
    assert r["estado"] == "aproximada"
    assert r["similitud"] >= vc.UMBRAL_OCR


def test_misma_diferencia_en_texto_digital_no_se_acepta_si_es_grande():
    # En texto digital el umbral es más exigente: una cita muy distinta no pasa como aproximada.
    r = vc.verificar_cita("El titular deberá informar a la SMA dentro de 90 días hábiles siguientes", 2, PAGINAS)
    assert r["estado"] == "no encontrada en esa página"


def test_dato_leido_en_imagen_no_se_verifica_con_texto():
    r = vc.verificar_cita("Resolución Exenta N° 202513001415", 1, PAGINAS, fuente="imagen")
    assert r["estado"] == "leída en imagen"


def test_verificar_recorre_campos_y_listas():
    ficha = {
        "campos": {
            "nombre_proyecto": {"valor": "Parque Fotovoltaico Queltehue", "pagina_pdf": 1, "cita_textual": "Parque Fotovoltaico Queltehue", "fuente": "texto"},
            "comuna": [{"valor": "Calera de Tango", "pagina_pdf": 2, "cita_textual": "comuna de Calera de Tango", "fuente": "texto"}],
            "monto_inversion": {"valor": "No consta", "pagina_pdf": None, "cita_textual": None},
        }
    }
    informe = vc.verificar(ficha, {"archivo": "x.pdf", "paginas": PAGINAS})
    campos = [c["campo"] for c in informe["citas"]]
    assert campos == ["campos.nombre_proyecto", "campos.comuna[0]"]
    assert informe["resumen"] == {"confirmada": 1, "no encontrada en esa página": 1}
