"""Pruebas de scripts/respaldar_salida.py, con una carpeta salida/ sintética."""

import io
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import respaldar_salida as rs

RAIZ = Path(__file__).resolve().parent.parent
AHORA = datetime(2026, 11, 24, 10, 15, 0)


def salida_sintetica(tmp_path):
    salida = tmp_path / "salida"
    archivos = {
        "obligaciones/a.json": "{}", "fichas/a.json": "{}", "consultas/consulta_x.json": "{}",
        "consultas/relaciones_aprobadas/pajonal.json": "{}", "verificacion/muestra.csv": "a;b",
        "compliance_ambiental.xlsx": "excel", "~$compliance_ambiental.xlsx": "bloqueo de Excel",
        "texto/a.json": "texto grande", "imagenes/a/pagina_1.png": "png", "secciones/a.json": "{}",
        "respaldos/viejo/obligaciones/a.json": "{}",
    }
    for relativa, contenido in archivos.items():
        (salida / relativa).parent.mkdir(parents=True, exist_ok=True)
        (salida / relativa).write_text(contenido, encoding="utf-8")
    return salida


def test_copia_lo_que_no_se_regenera_y_omite_lo_demas(tmp_path):
    salida = salida_sintetica(tmp_path)
    destino = rs.respaldar(salida, "antes de revisar Arqueros", AHORA)
    assert destino.name == "salida_20261124-101500_antes_de_revisar_arqueros"
    copiados = sorted(p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file())
    assert copiados == ["compliance_ambiental.xlsx", "consultas/consulta_x.json",
                        "consultas/relaciones_aprobadas/pajonal.json", "fichas/a.json", "obligaciones/a.json",
                        "respaldo.json", "verificacion/muestra.csv"]  # ni texto, imágenes, secciones ni respaldos


def test_respaldo_json_calza_con_lo_copiado(tmp_path):
    destino = rs.respaldar(salida_sintetica(tmp_path), "prueba", AHORA)
    informe = json.loads((destino / "respaldo.json").read_text(encoding="utf-8"))
    assert informe["motivo"] == "prueba" and informe["fecha_hora"] == "2026-11-24 10:15:00"
    assert informe["cantidad_archivos"] == len(informe["archivos"]) == 6
    for archivo in informe["archivos"]:
        assert rs.huella(destino / archivo["ruta"]) == archivo["sha256"]


def test_dos_respaldos_en_el_mismo_segundo_no_se_pisan(tmp_path):
    salida = salida_sintetica(tmp_path)
    primero, segundo = rs.respaldar(salida, "", AHORA), rs.respaldar(salida, "", AHORA)
    assert primero != segundo and segundo.name == "salida_20261124-101500_2"


def test_listar_incluye_respaldos_manuales_antiguos(tmp_path):
    salida = salida_sintetica(tmp_path)
    rs.respaldar(salida, "prueba", AHORA)
    lista = rs.listar(salida)
    assert lista[0]["carpeta"].startswith("salida_20261124") and lista[0]["cantidad_archivos"] == 6
    assert any(r["carpeta"] == "viejo" and "sin respaldo.json" in r["motivo"] for r in lista)


def entrada_hook(ruta):
    return json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(ruta)}})


def test_hook_respalda_solo_carpetas_protegidas(tmp_path):
    salida = salida_sintetica(tmp_path)
    assert rs.modo_hook(entrada_hook(salida / "texto" / "a.json"), salida, AHORA) is None
    assert rs.modo_hook(entrada_hook(tmp_path / "scripts" / "x.py"), salida, AHORA) is None
    assert rs.modo_hook(entrada_hook(salida / "consultas" / "consulta_x.json"), salida, AHORA) is None
    mensaje = rs.modo_hook(entrada_hook(salida / "obligaciones" / "a.json"), salida, AHORA)
    assert "antes de editar obligaciones" in mensaje
    assert rs.ultimo_respaldo(salida) == AHORA


def test_hook_no_repite_dentro_de_30_minutos(tmp_path):
    salida = salida_sintetica(tmp_path)
    ruta = salida / "consultas" / "relaciones_aprobadas" / "pajonal.json"
    assert rs.modo_hook(entrada_hook(ruta), salida, AHORA)
    assert rs.modo_hook(entrada_hook(ruta), salida, AHORA + timedelta(minutes=29)) is None
    assert rs.modo_hook(entrada_hook(ruta), salida, AHORA + timedelta(minutes=31))


def test_hook_nunca_bloquea(tmp_path, monkeypatch, capsys):
    # Entrada dañada o salida inexistente: termina con 0 (la edición sigue) y no crea nada.
    monkeypatch.setattr(sys, "stdin", io.StringIO("no es json"))
    assert rs.main(["--hook", "--salida", str(tmp_path / "no_existe")]) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(entrada_hook(tmp_path / "no_existe" / "fichas" / "a.json")))
    assert rs.main(["--hook", "--salida", str(tmp_path / "no_existe")]) == 0
    assert "AVISO" in capsys.readouterr().err


def test_linea_de_comandos_con_python_del_sistema(tmp_path):
    # Solo biblioteca estándar: el hook puede usar el python3 del sistema, sin el entorno .venv.
    salida = salida_sintetica(tmp_path)
    resultado = subprocess.run([sys.executable, "-I", str(RAIZ / "scripts" / "respaldar_salida.py"),
                                "--salida", str(salida), "--motivo", "prueba"],
                               capture_output=True, text=True, encoding="utf-8")
    assert resultado.returncode == 0 and "Respaldo creado" in resultado.stdout
    assert rs.main(["--salida", str(tmp_path / "no_existe")]) == 1


def test_configuracion_del_hook_del_proyecto():
    ajustes = json.loads((RAIZ / ".claude" / "settings.json").read_text(encoding="utf-8"))
    [regla] = ajustes["hooks"]["PreToolUse"]
    assert set(regla["matcher"].split("|")) >= {"Edit", "Write"}
    comando = regla["hooks"][0]["command"]
    assert "respaldar_salida.py" in comando and "--hook" in comando and "/Users/" not in comando
