"""Pruebas de scripts/leer_manifiesto.py."""

from pathlib import Path

import pytest

import leer_manifiesto as lm

RAIZ = Path(__file__).resolve().parent.parent
ENCABEZADO = "archivo,unidad_fiscalizable,proyecto\n"


def escribir(tmp_path, texto, codificacion="utf-8", nombre="manifiesto.csv"):
    ruta = tmp_path / nombre
    ruta.write_bytes(texto.encode(codificacion))
    return ruta


def test_manifiesto_de_ejemplo_es_valido():
    resultado = lm.leer_manifiesto(RAIZ / "ejemplos" / "manifiesto_ejemplo.csv", RAIZ / "ejemplos" / "rcas_publicas")
    assert len(resultado["filas"]) == 3
    assert resultado["separador"] == "coma"
    uf = {f["archivo"]: f["unidad_fiscalizable"] for f in resultado["filas"]}
    assert uf["rca_202513001415_queltehue_rm.pdf"] == lm.SIN_UF
    # Ningún PDF de la carpeta queda sin fila. Los PDF no están en el repositorio (se descargan del e-SEIA): si faltan,
    # el único aviso de archivos es que el manifiesto los nombra y no están en la carpeta.
    assert not any("no tiene fila" in a for a in resultado["avisos"])
    faltan = [a for a in resultado["avisos"] if "pdf" in a.lower() and "no está" in a]
    presentes = [p.name for p in (RAIZ / "ejemplos" / "rcas_publicas").glob("*.pdf")]
    assert len(faltan) == 3 - len(set(uf) & set(presentes))


def test_utf8_con_y_sin_bom(tmp_path):
    texto = ENCABEZADO + "a.pdf,Unidad Ñuñoa,Proyecto Río\n"
    for codificacion in ("utf-8", "utf-8-sig"):
        filas = lm.leer_manifiesto(escribir(tmp_path, texto, codificacion))["filas"]
        assert filas[0]["unidad_fiscalizable"] == "Unidad Ñuñoa"
        assert filas[0]["proyecto"] == "Proyecto Río"


def test_latin1_da_error_claro_con_linea(tmp_path):
    ruta = escribir(tmp_path, ENCABEZADO + "a.pdf,UF,Proyecto\nb.pdf,UF,Proyecto Río\n", "latin-1")
    with pytest.raises(lm.ErrorManifiesto) as error:
        lm.leer_manifiesto(ruta)
    assert "UTF-8" in str(error.value) and "línea 3" in str(error.value) and "Guardar como" in str(error.value)


@pytest.mark.parametrize("mal", ["Proyecto RÃ­o", "PlantaciÃ³n", "Proyecto R�o", "NÂº 5"])
def test_caracteres_mal_codificados_dan_error(tmp_path, mal):
    ruta = escribir(tmp_path, ENCABEZADO + f"a.pdf,UF,{mal}\n")
    with pytest.raises(lm.ErrorManifiesto) as error:
        lm.leer_manifiesto(ruta)
    assert "mal codificados" in str(error.value) and "línea 2" in str(error.value)


def test_punto_y_coma_se_detecta_y_se_avisa(tmp_path):
    ruta = escribir(tmp_path, "archivo;unidad_fiscalizable;proyecto;notas\na.pdf;UF 1;Proyecto, con coma;nota\n")
    resultado = lm.leer_manifiesto(ruta)
    assert resultado["separador"] == "punto y coma"
    assert resultado["filas"][0]["proyecto"] == "Proyecto, con coma"
    assert any("punto y coma" in a for a in resultado["avisos"])


def test_muchos_a_muchos(tmp_path):
    texto = ENCABEZADO + "a.pdf,UF 1,P\na.pdf,UF 2,P\nb.pdf,UF 1,Q\n"
    filas = lm.leer_manifiesto(escribir(tmp_path, texto))["filas"]
    assert [(f["archivo"], f["unidad_fiscalizable"]) for f in filas] == [("a.pdf", "UF 1"), ("a.pdf", "UF 2"), ("b.pdf", "UF 1")]


def test_par_repetido_y_obligatorias_vacias_dan_error(tmp_path):
    texto = ENCABEZADO + "a.pdf,UF 1,P\nA.pdf,uf 1,P\n,UF 3,R\nc.pdf,UF 4,\n"
    with pytest.raises(lm.ErrorManifiesto) as error:
        lm.leer_manifiesto(escribir(tmp_path, texto))
    mensaje = str(error.value)
    assert "Línea 3: repite el par" in mensaje and "línea 2" in mensaje
    assert "Línea 4" in mensaje and "\"archivo\"" in mensaje
    assert "Línea 5" in mensaje and "\"proyecto\"" in mensaje


def test_columna_obligatoria_faltante(tmp_path):
    with pytest.raises(lm.ErrorManifiesto) as error:
        lm.leer_manifiesto(escribir(tmp_path, "archivo,proyecto\na.pdf,P\n"))
    assert "unidad_fiscalizable" in str(error.value)


def test_sin_uf_y_pdfs_faltantes_o_sin_fila(tmp_path):
    carpeta = tmp_path / "rcas"
    carpeta.mkdir()
    (carpeta / "a.pdf").write_bytes(b"%PDF-1.4")
    (carpeta / "huerfano.pdf").write_bytes(b"%PDF-1.4")
    resultado = lm.leer_manifiesto(escribir(tmp_path, ENCABEZADO + "a.pdf,,P\nno_existe.pdf,UF,Q\n"), carpeta)
    assert resultado["filas"][0]["unidad_fiscalizable"] == lm.SIN_UF
    avisos = " ".join(resultado["avisos"])
    assert "no_existe.pdf" in avisos and "huerfano.pdf" in avisos and lm.SIN_UF in avisos
    huerfano = next(f for f in resultado["filas"] if f["archivo"] == "huerfano.pdf")
    assert huerfano["unidad_fiscalizable"] == lm.SIN_UF and huerfano["proyecto"].startswith("No consta")


def test_manifiesto_sin_columnas_opcionales_nuevas_sigue_sirviendo(tmp_path):
    filas = lm.leer_manifiesto(escribir(tmp_path, ENCABEZADO + "a.pdf,UF,P\n"))["filas"]
    assert filas[0]["enlace_eseia"] == "" and filas[0]["nota_uf"] == ""
    assert lm.enlaces_eseia(filas) == {}


def test_enlace_eseia_y_nota_uf(tmp_path):
    texto = ("archivo,unidad_fiscalizable,proyecto,enlace_eseia,nota_uf\n"
             "a.pdf,UF Uno,P,https://seia.sea.gob.cl/x?id=1,\n"
             "a.pdf,UF Dos,P,,\n"
             "b.pdf,,Q,seia.sea.gob.cl/sin_protocolo,No encontrada en SNIFA al 2026-11-23.\n"
             "a.pdf,UF Tres,P,https://seia.sea.gob.cl/x?id=2,\n")
    resultado = lm.leer_manifiesto(escribir(tmp_path, texto))
    assert lm.enlaces_eseia(resultado["filas"]) == {"a.pdf": "https://seia.sea.gob.cl/x?id=1",
                                                    "b.pdf": "seia.sea.gob.cl/sin_protocolo"}
    assert resultado["filas"][2]["nota_uf"] == "No encontrada en SNIFA al 2026-11-23."
    assert any("Línea 4" in a and "no empieza con http" in a for a in resultado["avisos"])
    assert any("Línea 5" in a and "distinto" in a and "línea 2" in a for a in resultado["avisos"])


def test_manifiesto_de_ejemplo_tiene_enlace_eseia_para_las_tres_rcas():
    resultado = lm.leer_manifiesto(RAIZ / "ejemplos" / "manifiesto_ejemplo.csv")
    enlaces = lm.enlaces_eseia(resultado["filas"])
    assert len(enlaces) == 3 and all(e.startswith("https://seia.sea.gob.cl/") for e in enlaces.values())
    assert not any("enlace_eseia" in a for a in resultado["avisos"])
