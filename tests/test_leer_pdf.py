"""Pruebas de scripts/leer_pdf.py.

Usan primero las RCAs reales de ejemplos/rcas_publicas/. El caso de página escaneada
se prueba con un PDF sintético que estas pruebas generan en una carpeta temporal.
"""

import json
from pathlib import Path

import pymupdf
import pytest

import leer_pdf

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLOS = RAIZ / "ejemplos" / "rcas_publicas"
QUELTEHUE = EJEMPLOS / "rca_202513001415_queltehue_rm.pdf"
ARQUEROS = EJEMPLOS / "rca_151_2013_arqueros_atacama.pdf"
ALBEMARLE = EJEMPLOS / "rca_021_2016_albemarle_salar_atacama.pdf"


def requiere(ruta):
    return pytest.mark.skipif(not ruta.exists(), reason=f"Falta {ruta.name} en ejemplos/rcas_publicas/")


requiere_queltehue = requiere(QUELTEHUE)

TEXTO_LARGO = (
    "El titular deberá implementar un plan de seguimiento de las variables ambientales "
    "y reportar sus resultados a la Superintendencia del Medio Ambiente."
)


# ----------------------------------------------------- PDF sintético

@pytest.fixture
def pdf_sintetico(tmp_path):
    """Crea un PDF de 5 páginas:
    1. texto normal, con una palabra cortada con guion al final de línea
    2. solo una imagen (simula una página escaneada)
    3. en blanco
    4. poco texto (una portadilla "ANEXO 1")
    5. texto con un marcador sin rellenar "<NUM_RES>"
    """
    # Imagen de un "documento escaneado": se dibuja texto en una página y se convierte a foto.
    borrador = pymupdf.open()
    hoja = borrador.new_page()
    hoja.insert_text((72, 100), "Pagina escaneada de una resolucion", fontsize=20)
    foto = hoja.get_pixmap(dpi=72)
    borrador.close()

    documento = pymupdf.open()
    p1 = documento.new_page()
    p1.insert_text((72, 72), "Medida de mitigación: el titular deberá cumplir la obliga-")
    p1.insert_text((72, 86), "ción de informar a la autoridad dentro de 30 días hábiles.")
    p1.insert_text((72, 120), TEXTO_LARGO)

    p2 = documento.new_page()
    p2.insert_image(p2.rect, pixmap=foto)

    documento.new_page()  # 3: en blanco

    p4 = documento.new_page()
    p4.insert_text((250, 400), "ANEXO 1")

    p5 = documento.new_page()
    p5.insert_text((72, 72), "Califica Ambientalmente el proyecto <NUM_RES> Santiago <FECHA_RESOLUCION>")
    p5.insert_text((72, 100), TEXTO_LARGO)

    ruta = tmp_path / "sintetico.pdf"
    documento.save(ruta)
    documento.close()
    return ruta


def test_clasifica_paginas_del_pdf_sintetico(pdf_sintetico, tmp_path):
    datos = leer_pdf.leer_pdf(pdf_sintetico, carpeta_imagenes=tmp_path / "imagenes")
    estados = [p["estado"] for p in datos["paginas"]]
    assert estados == ["texto", "escaneada", "en_blanco", "poco_texto", "texto"]
    assert datos["paginas_escaneadas"] == [2]
    assert datos["paginas_en_blanco"] == [3]
    assert datos["paginas_poco_texto"] == [4]
    # La palabra cortada con guion entre dos líneas queda unida.
    assert "obligación de informar" in datos["paginas"][0]["texto"]


def test_genera_imagen_solo_para_paginas_de_lectura_visual(pdf_sintetico, tmp_path):
    carpeta = tmp_path / "imagenes"
    datos = leer_pdf.leer_pdf(pdf_sintetico, carpeta_imagenes=carpeta)
    assert datos["paginas_lectura_visual"] == [2, 5]
    assert (carpeta / "pagina_2.png").exists()
    assert (carpeta / "pagina_5.png").exists()
    assert not (carpeta / "pagina_3.png").exists()  # en blanco: no se genera imagen
    assert datos["paginas"][1]["imagen"].endswith("pagina_2.png")


def test_detecta_marcadores_sin_rellenar(pdf_sintetico):
    pagina = leer_pdf.leer_pdf(pdf_sintetico)["paginas"][4]
    assert pagina["marcadores_sin_rellenar"] == ["<FECHA_RESOLUCION>", "<NUM_RES>"]
    assert pagina["requiere_lectura_visual"] is True


def test_une_palabras_cortadas_con_guion():
    assert leer_pdf.normalizar_bloque("cumplir la obliga-\nción de informar") == "cumplir la obligación de informar"
    # Un guion que no corta una palabra se conserva.
    assert leer_pdf.normalizar_bloque("D.S. N° 90-\n2000") == "D.S. N° 90- 2000"
    assert leer_pdf.normalizar_bloque("texto   con\n  espacios") == "texto con espacios"


def test_cuenta_caracteres_dudosos_sin_corregirlos(tmp_path, monkeypatch):
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), TEXTO_LARGO)
    ruta = tmp_path / "dudoso.pdf"
    documento.save(ruta)
    # Las fuentes estándar no pueden dibujar "�", así que se simula que el PDF lo trae
    # (como en algunas RCAs reales) reemplazando lo que devuelve la extracción de texto.
    texto_con_dudosos = "REP�BLICA DE CHILE, COMISI�N DE EVALUACIÓN. " + TEXTO_LARGO
    monkeypatch.setattr(leer_pdf, "extraer_texto", lambda pagina: texto_con_dudosos)
    datos = leer_pdf.leer_pdf(ruta)
    assert datos["n_caracteres_dudosos"] == 2
    assert datos["paginas"][0]["caracteres_dudosos"] == 2
    # El texto se conserva tal cual: no se "corrige" a ciegas.
    assert datos["paginas"][0]["texto"] == texto_con_dudosos


def test_numero_impreso(tmp_path):
    documento = pymupdf.open()
    for numero in (1, 2):
        pagina = documento.new_page()
        pagina.insert_text((72, 100), TEXTO_LARGO)
        pagina.insert_text((280, pagina.rect.height - 20), f"Página {numero + 4} de 10")
    # Pie al 90 % del alto, como en algunas RCAs reales ("101 de 178").
    alto = documento.new_page()
    alto.insert_text((72, 100), TEXTO_LARGO)
    alto.insert_text((280, alto.rect.height * 0.91), "7 de 10")
    sin_numero = documento.new_page()
    sin_numero.insert_text((72, 100), TEXTO_LARGO)
    ruta = tmp_path / "numerado.pdf"
    documento.save(ruta)
    numeros = [p["numero_impreso"] for p in leer_pdf.leer_pdf(ruta)["paginas"]]
    assert numeros == [5, 6, 7, None]


def test_numeros_sueltos_sin_secuencia_se_descartan():
    # Números en el borde que no siguen una secuencia (por ejemplo, celdas de una tabla).
    paginas = [{"numero_pdf": i, "numero_impreso": n} for i, n in enumerate([None, 40, None, 7, 913, None], 1)]
    leer_pdf.filtrar_numeros_impresos(paginas)
    assert [p["numero_impreso"] for p in paginas] == [None] * 6
    # Una secuencia coherente se conserva, y el valor que no calza se descarta.
    paginas = [{"numero_pdf": i, "numero_impreso": n} for i, n in enumerate([3, 4, 5, 99, 7], 1)]
    leer_pdf.filtrar_numeros_impresos(paginas)
    assert [p["numero_impreso"] for p in paginas] == [3, 4, 5, None, 7]


# ------------------------------------------------- archivos con problemas

def test_pdf_danado_da_error_claro(tmp_path):
    ruta = tmp_path / "danado.pdf"
    ruta.write_bytes(b"%PDF-1.7\nesto no es un PDF valido")
    with pytest.raises(leer_pdf.ErrorLectura, match="dañado|no es un PDF"):
        leer_pdf.leer_pdf(ruta)


def test_archivo_vacio_da_error_claro(tmp_path):
    ruta = tmp_path / "vacio.pdf"
    ruta.write_bytes(b"")
    with pytest.raises(leer_pdf.ErrorLectura, match="vacío"):
        leer_pdf.leer_pdf(ruta)


def test_pagina_web_disfrazada_de_pdf_se_rechaza(tmp_path):
    # Caso real: infofirma.sea.gob.cl entrega una página HTML, no un PDF.
    ruta = tmp_path / "pagina_web.pdf"
    ruta.write_text("<html><body><p>Califica Ambientalmente</p></body></html>", encoding="utf-8")
    with pytest.raises(leer_pdf.ErrorLectura, match="no es un PDF"):
        leer_pdf.leer_pdf(ruta)


def test_un_pdf_malo_no_detiene_a_los_demas(pdf_sintetico, tmp_path):
    malo = tmp_path / "vacio.pdf"
    malo.write_bytes(b"")
    salida = tmp_path / "salida"
    codigo = leer_pdf.main([str(malo), str(pdf_sintetico), "--salida", str(salida)])
    assert codigo == 1  # avisa que hubo un error...
    assert (salida / "texto" / "sintetico.json").exists()  # ...pero procesó el otro
    error = json.loads((salida / "errores" / "vacio.json").read_text(encoding="utf-8"))
    assert "vacío" in error["error"]


# ------------------------------------------------------- RCA real

@requiere_queltehue
def test_rca_queltehue():
    datos = leer_pdf.leer_pdf(QUELTEHUE)
    assert datos["n_paginas"] == 98
    assert datos["n_paginas_escaneadas"] == 0
    assert datos["paginas_en_blanco"] == []
    assert datos["sha256"] == "5723cf4ba1b6843f57170e92c7e0752dc455225b913a6517d5258ad86b8b768a"
    # El número y la fecha de la resolución solo se ven en la imagen de la página 1.
    pagina1 = datos["paginas"][0]
    assert "<NUM_RES>" in pagina1["marcadores_sin_rellenar"]
    assert pagina1["requiere_lectura_visual"] is True
    assert "Parque Fotovoltaico Queltehue" in pagina1["texto"]
    assert datos["paginas_lectura_visual"] == [1, 97]
    # Esta RCA no trae numeración impresa: no se deben inventar números.
    assert all(p["numero_impreso"] is None for p in datos["paginas"])


@requiere_queltehue
def test_rca_queltehue_genera_json(tmp_path):
    destino, datos = leer_pdf.procesar(QUELTEHUE, tmp_path)
    leido = json.loads(Path(destino).read_text(encoding="utf-8"))
    assert leido["archivo"] == QUELTEHUE.name
    assert len(leido["paginas"]) == 98
    assert (tmp_path / "imagenes" / QUELTEHUE.stem / "pagina_1.png").exists()



@requiere(ARQUEROS)
def test_rca_arqueros():
    datos = leer_pdf.leer_pdf(ARQUEROS)
    assert datos["n_paginas"] == 228
    assert datos["sha256"] == "a2d169f43f3cad80ae7a1e3e66a8a3602cb9f4594fd267eb2687487427803494"
    # Texto digital, con tres páginas que son solo imagen.
    assert datos["paginas_ocr_previo"] == []
    assert datos["paginas_escaneadas"] == [60, 166, 167]
    assert "Resolución Exenta Nº 151" in datos["paginas"][0]["texto"]


@requiere(ALBEMARLE)
def test_rca_albemarle_ocr_previo():
    datos = leer_pdf.leer_pdf(ALBEMARLE)
    assert datos["n_paginas"] == 72
    assert datos["sha256"] == "8f67f985b2568f17df554ad3bc775f5d8665ea3a8a0b71f5fa46666db56249b3"
    # Escaneo con OCR previo en todas sus páginas: se detecta y se avisa.
    assert datos["paginas_ocr_previo"] == list(range(1, 73))
    assert "OCR previo" in datos["avisos"][0]
    # La página 52 no tiene texto útil: es escaneada y se pide leerla como imagen.
    assert datos["paginas_escaneadas"] == [52]
    assert datos["paginas_lectura_visual"] == [52]
    # El texto del OCR se conserva tal cual, con sus errores (no se corrige).
    assert "Servido de Evaluación Ambiental" in datos["paginas"][0]["texto"]


@requiere_queltehue
def test_texto_digital_no_se_marca_como_ocr():
    datos = leer_pdf.leer_pdf(QUELTEHUE)
    assert datos["paginas_ocr_previo"] == []
    assert {p["origen_texto"] for p in datos["paginas"]} == {"digital"}


def test_detecta_ocr_sintetico(tmp_path):
    """Página con una imagen de fondo y texto invisible encima, como deja un OCR."""
    borrador = pymupdf.open()
    hoja = borrador.new_page()
    hoja.insert_text((72, 100), "Resolucion escaneada", fontsize=20)
    foto = hoja.get_pixmap(dpi=72)
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_image(pagina.rect, pixmap=foto)
    pagina.insert_text((72, 100), TEXTO_LARGO, render_mode=3)  # 3 = texto invisible
    digital = documento.new_page()
    digital.insert_text((72, 100), TEXTO_LARGO)
    ruta = tmp_path / "ocr.pdf"
    documento.save(ruta)
    datos = leer_pdf.leer_pdf(ruta)
    assert [p["origen_texto"] for p in datos["paginas"]] == ["ocr_previo", "digital"]
    assert datos["paginas_ocr_previo"] == [1]
