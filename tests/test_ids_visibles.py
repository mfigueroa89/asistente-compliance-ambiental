"""Pruebas de scripts/ids_visibles.py y de la columna prefijo_id del manifiesto."""

from pathlib import Path

import pytest

import ids_visibles as iv
import leer_manifiesto

RAIZ = Path(__file__).resolve().parent.parent
PREFIJOS = {"arq.pdf": "ARQ", "que.pdf": "QUE"}


def test_id_visible_y_sin_prefijo():
    assert iv.id_visible("arq.pdf", "OBL-024", PREFIJOS) == "ARQ-024"
    assert iv.id_visible("otra.pdf", "OBL-024", PREFIJOS) == "OBL-024"  # RCA sin prefijo: se ve el ID interno


@pytest.mark.parametrize("texto", ["ARQ-024", "arq-24", "ARQ 024", "arq024", " ARQ_024 "])
def test_resolver_acepta_variantes(texto):
    assert iv.resolver(texto, PREFIJOS) == [("arq.pdf", "OBL-024")]


def test_resolver_id_interno_y_desconocido():
    assert iv.resolver("OBL-024", PREFIJOS) == [(None, "OBL-024")]
    assert iv.resolver("ZZZ-024", PREFIJOS) == []
    assert iv.resolver("humedal", PREFIJOS) == []


def test_validar_prefijos():
    filas = [{"archivo": "a.pdf", "prefijo_id": "ARQ", "linea": 2}, {"archivo": "a.pdf", "prefijo_id": "ARQ", "linea": 3},
             {"archivo": "b.pdf", "prefijo_id": "ARQ", "linea": 4}, {"archivo": "c.pdf", "prefijo_id": "arq1", "linea": 5},
             {"archivo": "d.pdf", "prefijo_id": "OBL", "linea": 6}, {"archivo": "a.pdf", "prefijo_id": "QUE", "linea": 7}]
    errores = iv.validar_prefijos(filas)
    assert len(errores) == 4
    assert "ya se usa" in errores[0] and "2 a 5 letras" in errores[1] and "2 a 5 letras" in errores[2]
    assert "un solo prefijo" in errores[3]


def test_manifiesto_con_prefijo_repetido_se_rechaza(tmp_path):
    ruta = tmp_path / "manifiesto.csv"
    ruta.write_text("archivo,unidad_fiscalizable,proyecto,prefijo_id\na.pdf,UF,P,ARQ\nb.pdf,UF,P,ARQ\n", encoding="utf-8")
    with pytest.raises(leer_manifiesto.ErrorManifiesto, match="ya se usa"):
        leer_manifiesto.leer_manifiesto(ruta)


def test_manifiesto_sin_columna_prefijo_sigue_sirviendo(tmp_path):
    ruta = tmp_path / "manifiesto.csv"
    ruta.write_text("archivo,unidad_fiscalizable,proyecto\na.pdf,UF,P\n", encoding="utf-8")
    assert iv.prefijos_de(leer_manifiesto.leer_manifiesto(ruta)["filas"]) == {}


def test_prefijos_del_manifiesto_de_ejemplo():
    prefijos = iv.prefijos_del_manifiesto(RAIZ / "ejemplos" / "manifiesto_ejemplo.csv")
    assert prefijos == {"rca_202513001415_queltehue_rm.pdf": "QUE", "rca_151_2013_arqueros_atacama.pdf": "ARQ",
                        "rca_021_2016_albemarle_salar_atacama.pdf": "ALB"}
