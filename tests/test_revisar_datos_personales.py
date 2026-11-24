"""Pruebas de scripts/revisar_datos_personales.py con un PDF sintético."""

import pymupdf

import revisar_datos_personales as revisar


def test_detecta_datos_personales(tmp_path):
    documento = pymupdf.open()
    pagina = documento.new_page()
    lineas = [
        "Observación de Juan Pérez, RUT 12.345.678-9, domiciliado en calle Los Aromos N° 123.",
        "Contacto: juan.perez@correo.cl, teléfono +56 9 8765 4321.",
        "Distribución: Superintendencia del Medio Ambiente <contacto@sma.gob.cl>.",
        "Período de monitoreo 2009-2010.",
    ]
    for indice, linea in enumerate(lineas):
        pagina.insert_text((40, 72 + 16 * indice), linea, fontsize=9)
    ruta = tmp_path / "datos.pdf"
    documento.save(ruta)

    hallazgos = revisar.revisar(ruta)["hallazgos"]
    assert [h["valor"] for h in hallazgos["rut"]] == ["12.345.678-9"]
    assert [h["valor"] for h in hallazgos["correo_otro"]] == ["juan.perez@correo.cl"]
    assert [h["valor"] for h in hallazgos["correo_institucional"]] == ["contacto@sma.gob.cl"]
    assert len(hallazgos["telefono"]) == 1  # el par de años 2009-2010 no cuenta como teléfono
    assert len(hallazgos["domicilio"]) == 1
    assert all(h["pagina"] == 1 for lista in hallazgos.values() for h in lista)


def test_documento_limpio(tmp_path):
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), "Resolución Exenta N° 21. El titular deberá informar a la SMA.")
    ruta = tmp_path / "limpio.pdf"
    documento.save(ruta)
    hallazgos = revisar.revisar(ruta)["hallazgos"]
    assert all(lista == [] for lista in hallazgos.values())
