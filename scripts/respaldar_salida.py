"""Respaldo con fecha de salida/ (sin IA). Copia lo que no se puede regenerar con código.

Usos:
    python scripts/respaldar_salida.py [--salida salida] [--motivo "antes de revisar Arqueros"]
        Crea salida/respaldos/salida_AAAAMMDD-HHMMSS_<motivo>/ con:
          obligaciones/, fichas/, consultas/ (incluye relaciones_aprobadas/), verificacion/, revision/ y el Excel.
        No copia texto/, imagenes/ ni secciones/: se regeneran desde los PDF con leer_pdf.py y localizar_secciones.py.
        Deja respaldo.json con la fecha, el motivo y la huella SHA-256 de cada archivo copiado.

    python scripts/respaldar_salida.py --listar [--salida salida]
        Lista los respaldos existentes (fecha, motivo y cantidad de archivos). Nunca borra respaldos.

    python scripts/respaldar_salida.py --hook
        Modo automático, para el hook de Claude Code (.claude/settings.json). Lee de la entrada estándar el
        archivo que Claude va a editar; si está en una carpeta protegida de salida/ y no hay un respaldo de los
        últimos 30 minutos, crea uno. Nunca bloquea la edición: ante cualquier problema, avisa y termina bien.

Solo usa la biblioteca estándar de Python (funciona con cualquier python3, también sin el entorno .venv).
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETAS = ["obligaciones", "fichas", "consultas", "verificacion", "revision"]
ARCHIVOS = ["compliance_ambiental.xlsx"]
OMITIDAS = ["texto", "imagenes", "secciones"]
PROTEGIDAS = ["obligaciones", "fichas", "consultas/relaciones_aprobadas", "verificacion", "revision"]
MINUTOS_HOOK = 30
PREFIJO = "salida_"


def nombre_seguro(texto):
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")[:60]


def huella(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def a_copiar(salida):
    """Archivos de salida/ que se respaldan: [(ruta_absoluta, ruta_relativa)]."""
    salida = Path(salida)
    lista = []
    for carpeta in CARPETAS:
        base = salida / carpeta
        if base.is_dir():
            for ruta in sorted(base.rglob("*")):
                if ruta.is_file() and not ruta.name.startswith(("~$", ".")):
                    lista.append((ruta, ruta.relative_to(salida)))
    for nombre in ARCHIVOS:
        if (salida / nombre).is_file():
            lista.append((salida / nombre, Path(nombre)))
    return lista


def respaldar(salida, motivo="", ahora=None):
    """Crea el respaldo y devuelve su carpeta. Lanza FileNotFoundError si no existe salida/."""
    salida = Path(salida)
    if not salida.is_dir():
        raise FileNotFoundError(f"No existe la carpeta {salida}: no hay nada que respaldar.")
    ahora = (ahora or datetime.now()).replace(microsecond=0)
    base = f"{PREFIJO}{ahora.strftime('%Y%m%d-%H%M%S')}" + (f"_{nombre_seguro(motivo)}" if nombre_seguro(motivo) else "")
    destino, numero = salida / "respaldos" / base, 2
    while destino.exists():  # dos respaldos en el mismo segundo no se pisan
        destino = salida / "respaldos" / f"{base}_{numero}"
        numero += 1
    destino.mkdir(parents=True)
    archivos = []
    for origen, relativa in a_copiar(salida):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino / relativa)
        archivos.append({"ruta": relativa.as_posix(), "bytes": origen.stat().st_size, "sha256": huella(destino / relativa)})
    informe = {
        "fecha_hora": ahora.isoformat(sep=" "), "motivo": motivo or "No consta", "origen": salida.resolve().as_posix(),
        "carpetas_respaldadas": CARPETAS, "archivos_sueltos": ARCHIVOS,
        "omitidas": OMITIDAS, "nota_omitidas": "Se regeneran desde los PDF con leer_pdf.py y localizar_secciones.py.",
        "cantidad_archivos": len(archivos), "archivos": archivos,
    }
    (destino / "respaldo.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def listar(salida):
    """[{carpeta, fecha_hora, motivo, cantidad_archivos}] de los respaldos, el más reciente primero."""
    carpeta = Path(salida) / "respaldos"
    resultado = []
    for respaldo in sorted(carpeta.iterdir() if carpeta.is_dir() else [], reverse=True):
        if not respaldo.is_dir():
            continue
        informe = respaldo / "respaldo.json"
        if informe.exists():
            datos = json.loads(informe.read_text(encoding="utf-8"))
            resultado.append({"carpeta": respaldo.name, "fecha_hora": datos.get("fecha_hora"),
                              "motivo": datos.get("motivo"), "cantidad_archivos": datos.get("cantidad_archivos")})
        else:
            resultado.append({"carpeta": respaldo.name, "fecha_hora": "No consta", "cantidad_archivos": None,
                              "motivo": "respaldo manual anterior a respaldar_salida.py (sin respaldo.json)"})
    # Primero los que tienen fecha (el más reciente arriba); al final los manuales antiguos, sin fecha registrada.
    resultado.sort(key=lambda r: (r["cantidad_archivos"] is not None, r["fecha_hora"], r["carpeta"]), reverse=True)
    return resultado


def ultimo_respaldo(salida):
    """Fecha y hora del respaldo automático o manual más reciente hecho con este script, o None."""
    fechas = []
    for respaldo in (Path(salida) / "respaldos").glob(f"{PREFIJO}*"):
        m = re.match(rf"{PREFIJO}(\d{{8}}-\d{{6}})", respaldo.name)
        if m and (respaldo / "respaldo.json").exists():
            fechas.append(datetime.strptime(m.group(1), "%Y%m%d-%H%M%S"))
    return max(fechas) if fechas else None


def carpeta_protegida(ruta_archivo, salida):
    """La carpeta protegida de salida/ que contiene el archivo, o None."""
    try:
        relativa = Path(ruta_archivo).resolve().relative_to(Path(salida).resolve())
    except ValueError:
        return None
    texto = relativa.as_posix()
    for protegida in PROTEGIDAS:
        if texto == protegida or texto.startswith(protegida + "/"):
            return protegida
    return None


def modo_hook(entrada, salida, ahora=None, minutos=MINUTOS_HOOK):
    """Decide y, si corresponde, respalda. Devuelve un mensaje (o None si no correspondía respaldar)."""
    try:
        datos = json.loads(entrada or "{}")
    except json.JSONDecodeError:
        return None
    entrada_herramienta = datos.get("tool_input") or {}
    ruta = entrada_herramienta.get("file_path") or entrada_herramienta.get("notebook_path")
    protegida = carpeta_protegida(ruta, salida) if ruta else None
    if protegida is None:
        return None
    ahora = ahora or datetime.now()
    ultimo = ultimo_respaldo(salida)
    if ultimo is not None and ahora - ultimo < timedelta(minutes=minutos):
        return None
    destino = respaldar(salida, f"automatico antes de editar {protegida}", ahora)
    return f"Respaldo automático de salida/ antes de editar {protegida}: {destino.as_posix()}"


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Respaldo con fecha de salida/ (lo que no se regenera con código).")
    parser.add_argument("--salida", default=None, help="Carpeta de salida (por defecto: salida; en --hook, la del proyecto)")
    parser.add_argument("--motivo", default="", help="Motivo breve, va en el nombre del respaldo")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--listar", action="store_true", help="Lista los respaldos existentes")
    grupo.add_argument("--hook", action="store_true", help="Modo automático para el hook de Claude Code")
    opciones = parser.parse_args(argumentos)

    if opciones.hook:
        try:
            mensaje = modo_hook(sys.stdin.read(), opciones.salida or RAIZ / "salida")
            if mensaje:
                print(mensaje)
        except Exception as error:  # el hook nunca debe impedir la edición
            print(f"AVISO: no se pudo hacer el respaldo automático ({error}). Haga uno a mano.", file=sys.stderr)
        return 0

    salida = opciones.salida or "salida"
    if opciones.listar:
        respaldos = listar(salida)
        print(f"== {len(respaldos)} respaldos en {Path(salida, 'respaldos').as_posix()} (el más reciente primero)")
        for r in respaldos:
            cantidad = f"{r['cantidad_archivos']} archivos" if r["cantidad_archivos"] is not None else "sin detalle"
            print(f"   {r['carpeta']}: {r['fecha_hora']}; {cantidad}; motivo: {r['motivo']}")
        return 0
    try:
        destino = respaldar(salida, opciones.motivo)
    except FileNotFoundError as error:
        print(f"ERROR: {error}")
        return 1
    informe = json.loads((destino / "respaldo.json").read_text(encoding="utf-8"))
    print(f"== Respaldo creado: {destino.as_posix()} ({informe['cantidad_archivos']} archivos; "
          f"no incluye {', '.join(OMITIDAS)}, que se regeneran desde los PDF)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
