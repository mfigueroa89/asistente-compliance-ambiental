"""Pruebas de scripts/contrastar_busqueda.py."""

from pathlib import Path

import pymupdf
import pytest

import contrastar_busqueda as cb
import leer_pdf

RAIZ = Path(__file__).resolve().parent.parent
ARQUEROS = RAIZ / "ejemplos" / "rcas_publicas" / "rca_151_2013_arqueros_atacama.pdf"


def test_misma_palabra_coincide():
    r = cb.contrastar_pagina("Se protegerán los humedales.", "Se protegerán los humedales.", "humedal")
    assert (r["buscador"], r["visor"], r["coinciden"], r["clasificacion"]) == (1, 1, 1, [])


def test_visor_encuentra_dentro_de_otra_palabra():
    r = cb.contrastar_pagina("Afloramiento de aguas y ruta para navegar.", "", "flora")
    assert r["buscador"] == 0 and r["visor"] == 1 and r["solo_visor"] == ["Afloramiento"]
    assert cb.DENTRO in r["clasificacion"] and cb.OMISION not in r["clasificacion"]


def test_buscador_encuentra_plural_de_frase():
    r = cb.contrastar_pagina("Ley de Monumentos Nacionales.", "Ley de Monumentos Nacionales.", "monumento nacional")
    assert (r["buscador"], r["visor"]) == (1, 0) and r["solo_buscador"] == ["Monumentos Nacionales"]
    assert r["clasificacion"] == [cb.VARIANTE]


def test_visor_prueba_grafia_sin_tildes():
    r = cb.contrastar_pagina("ACUIFERO del sector", "ACUIFERO del sector", "acuífero")
    assert (r["buscador"], r["visor"], r["coinciden"]) == (1, 1, 1)


def test_texto_de_leer_pdf_distinto():
    r = cb.contrastar_pagina("los hume- dales", "los humedales", "humedal")
    assert cb.LEER_PDF in r["clasificacion"]


def test_pdf_sintetico_con_pagina_escaneada(tmp_path):
    borrador = pymupdf.open()
    hoja = borrador.new_page()
    hoja.insert_text((72, 100), "humedal", fontsize=20)
    foto = hoja.get_pixmap(dpi=72)
    borrador.close()
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), "El titular protegera el humedal y las vegas del sector.")
    escaneada = documento.new_page()
    escaneada.insert_image(escaneada.rect, pixmap=foto)
    ruta = tmp_path / "x.pdf"
    documento.save(ruta)
    documento.close()
    texto = leer_pdf.leer_pdf(ruta)
    filas = cb.contrastar_rca(ruta, texto, {"humedales": ["humedal", "vega"]})
    assert [(f["pagina_pdf"], f["termino"], f["buscador"], f["visor"]) for f in filas] == [(1, "humedal", 1, 1), (1, "vega", 1, 1)]


@pytest.mark.skipif(not ARQUEROS.exists() or not (RAIZ / "salida" / "texto" / "rca_151_2013_arqueros_atacama.json").exists(),
                    reason="Faltan el PDF o el texto de Arqueros")
def test_arqueros_sin_posibles_omisiones():
    import json
    import buscar_palabras as bp
    texto = json.loads((RAIZ / "salida" / "texto" / "rca_151_2013_arqueros_atacama.json").read_text(encoding="utf-8"))
    filas = cb.contrastar_rca(ARQUEROS, texto, bp.cargar_temas())
    total = cb.resumen(filas)
    assert total[cb.OMISION] == 0 and total[cb.LEER_PDF] == 0
    assert total["coinciden"] + total[cb.DENTRO] == total["visor"]
    humedal = [f for f in filas if f["termino"] == "humedal"]
    assert sum(f["buscador"] for f in humedal) == sum(f["visor"] for f in humedal)
