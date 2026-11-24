import csv
import json

import muestra_auditoria as ma


def archivo_obligaciones(carpeta, nombre, cantidad):
    obligaciones = [{
        "id_obligacion": f"OBL-{n:03d}", "pagina_pdf": n, "tipo": "otra", "descripcion": f"Obligación {n} de {nombre}",
        "plazo_o_frecuencia": "No consta", "autoridad_destinataria": "SMA", "cita_textual": f"cita {n}",
    } for n in range(cantidad, 0, -1)]  # desordenadas a propósito
    ruta = carpeta / f"{nombre}.json"
    ruta.write_text(json.dumps({"obligaciones": obligaciones}), encoding="utf-8")
    return ruta


def rutas(tmp_path):
    return [archivo_obligaciones(tmp_path, "rca_b", 15), archivo_obligaciones(tmp_path, "rca_a", 12)]


def test_misma_semilla_misma_muestra_y_ordenada(tmp_path):
    filas = ma.cargar_filas(rutas(tmp_path))
    primera = ma.elegir_muestra(filas, semilla=20261123, cantidad=20)
    segunda = ma.elegir_muestra(ma.cargar_filas(rutas(tmp_path)), semilla=20261123, cantidad=20)
    claves = lambda muestra: [(rca, o["id_obligacion"]) for _, rca, o in muestra]
    assert claves(primera) == claves(segunda)
    assert len(primera) == 20 and len(set(claves(primera))) == 20
    assert claves(primera) == sorted(claves(primera), key=lambda c: (c[0] != "rca_b", c[1]))
    otra = ma.elegir_muestra(filas, semilla=1, cantidad=20)
    assert claves(otra) != claves(primera)


def test_cantidad_mayor_que_el_total_devuelve_todas(tmp_path):
    filas = ma.cargar_filas(rutas(tmp_path))
    assert len(ma.elegir_muestra(filas, cantidad=100)) == 27


def test_main_guarda_csv_con_columnas_y_aviso(tmp_path, capsys):
    assert ma.main([str(r) for r in rutas(tmp_path)] + ["--salida", str(tmp_path / "salida"), "--cantidad", "5"]) == 0
    ruta = tmp_path / "salida" / "verificacion" / "muestra_auditoria_20261123.csv"
    with ruta.open(encoding="utf-8-sig") as archivo:
        filas = list(csv.DictReader(archivo))
    assert len(filas) == 5
    assert list(filas[0]) == ma.COLUMNAS
    assert "Requiere revisión de un abogado" in capsys.readouterr().out
