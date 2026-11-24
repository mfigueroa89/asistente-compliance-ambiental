"""Pruebas de scripts/registrar_revision.py, con obligaciones sintéticas."""

import json
from datetime import datetime

import pytest

import registrar_revision as rr

PREFIJOS = {"a.pdf": "AAA", "b.pdf": "BBB"}
AHORA = datetime(2026, 11, 24, 11, 0, 0)


def salida_sintetica(tmp_path):
    salida = tmp_path / "salida"
    (salida / "obligaciones").mkdir(parents=True)
    for archivo, n in (("a", 5), ("b", 3)):
        obligaciones = [{"id_obligacion": f"OBL-{i:03d}", "pagina_pdf": i, "tipo": "otra", "descripcion": f"Obligación {i}",
                         "cita_textual": f"cita {i}"} for i in range(1, n + 1)]
        (salida / "obligaciones" / f"{archivo}.json").write_text(
            json.dumps({"archivo": f"{archivo}.pdf", "obligaciones": obligaciones}), encoding="utf-8")
    return salida


def planilla_llenada(tmp_path, salida, ids, resultados, **extra):
    ruta = rr.crear_planilla(salida, [(None, i) for i in ids], PREFIJOS, "prueba", AHORA)
    filas = rr.leer_csv(ruta)
    for fila, resultado in zip(filas, resultados):
        fila.update(resultado=resultado, **extra)
    destino = tmp_path / "llenada.csv"
    rr.escribir_csv(filas, rr.COLUMNAS_PLANILLA, destino)
    return destino


def test_expandir_rangos():
    assert rr.expandir("AAA-001 BBB-002..004, OBL-5") == ["AAA-001", "BBB-002", "BBB-003", "BBB-004", "OBL-5"]
    with pytest.raises(rr.ErrorRevision, match="al revés"):
        rr.expandir("AAA-005..002")


def test_planilla_con_id_visible_y_columnas_vacias(tmp_path):
    salida = salida_sintetica(tmp_path)
    ruta = rr.crear_planilla(salida, [(None, "AAA-002"), (None, "bbb 3"), (None, "AAA-002")], PREFIJOS, "auditoria", AHORA)
    assert ruta.name == "planilla_auditoria_20261124-110000.csv"
    filas = rr.leer_csv(ruta)
    assert [(f["id_visible"], f["archivo"], f["id_obligacion"]) for f in filas] == [
        ("AAA-002", "a.pdf", "OBL-002"), ("BBB-003", "b.pdf", "OBL-003")]  # sin repetir
    assert all(f["resultado"] == "" for f in filas)


def test_planilla_con_id_inexistente_o_ambiguo_no_se_crea(tmp_path):
    salida = salida_sintetica(tmp_path)
    with pytest.raises(rr.ErrorRevision, match="no existe"):
        rr.crear_planilla(salida, [(None, "BBB-009")], PREFIJOS)
    with pytest.raises(rr.ErrorRevision, match="varias RCAs"):
        rr.crear_planilla(salida, [(None, "OBL-001")], PREFIJOS)  # OBL-001 está en a.pdf y en b.pdf
    assert not (salida / "revision" / "planillas").exists()


def test_importar_simula_y_luego_registra_con_respaldo(tmp_path):
    salida = salida_sintetica(tmp_path)
    planilla = planilla_llenada(tmp_path, salida, ["AAA-001", "AAA-002", "BBB-001"], ["confirmada", "Confirmada", ""],
                                revisado_por="Ignacio", fecha_revision="2026-11-24")
    validas, sin_llenar, errores = rr.revisar_planilla(planilla, salida, PREFIJOS)
    assert (len(validas), sin_llenar, errores) == (2, 1, [])
    assert not rr.ruta_registro(salida).exists()  # revisar no registra
    respaldo = rr.registrar(validas, salida, AHORA)
    assert (respaldo / "respaldo.json").exists()
    tabla = rr.resumen(salida)
    assert tabla["a.pdf"] == {"total": 5, "revisadas": 2, "confirmada": 2, "corregida": 0, "descartada": 0}
    assert tabla["b.pdf"]["revisadas"] == 0


def test_un_error_y_no_se_registra_nada(tmp_path):
    salida = salida_sintetica(tmp_path)
    planilla = planilla_llenada(tmp_path, salida, ["AAA-001", "AAA-002", "AAA-003"], ["confirmada", "ok", "corregida"],
                                revisado_por="Ignacio")
    assert rr.main(["--salida", str(salida), "importar", str(planilla), "--aplicar"]) == 1
    _, _, errores = rr.revisar_planilla(planilla, salida, PREFIJOS)
    assert any("«ok» no permitido" in e for e in errores)
    assert any("corregida» necesita un comentario" in e for e in errores)
    assert not rr.ruta_registro(salida).exists()


def test_falta_quien_reviso(tmp_path):
    salida = salida_sintetica(tmp_path)
    planilla = planilla_llenada(tmp_path, salida, ["AAA-001"], ["confirmada"])
    _, _, errores = rr.revisar_planilla(planilla, salida, PREFIJOS)
    assert "falta revisado_por" in errores[0]
    assert rr.revisar_planilla(planilla, salida, PREFIJOS, por="Ignacio")[2] == []


def test_vale_la_ultima_revision_y_se_conserva_el_historial(tmp_path):
    salida = salida_sintetica(tmp_path)
    primera = planilla_llenada(tmp_path, salida, ["AAA-004"], ["corregida"], revisado_por="Ignacio", comentario="plazo")
    rr.registrar(rr.revisar_planilla(primera, salida, PREFIJOS)[0], salida, AHORA)
    segunda = planilla_llenada(tmp_path, salida, ["AAA-004"], ["confirmada"], revisado_por="Ignacio")
    rr.registrar(rr.revisar_planilla(segunda, salida, PREFIJOS)[0], salida, AHORA)
    assert len(rr.historial(salida)) == 2
    assert rr.estado_actual(salida)[("a.pdf", "OBL-004")]["estado"] == "confirmada"


def test_planilla_desde_la_muestra_de_auditoria(tmp_path):
    salida = salida_sintetica(tmp_path)
    muestra = tmp_path / "muestra.csv"
    muestra.write_text("RCA,ID,Página\na,OBL-003,3\nb,OBL-001,1\n", encoding="utf-8-sig")
    ruta = rr.crear_planilla(salida, rr.ids_de_muestra(muestra), PREFIJOS, "muestra", AHORA)
    assert [f["id_visible"] for f in rr.leer_csv(ruta)] == ["AAA-003", "BBB-001"]
