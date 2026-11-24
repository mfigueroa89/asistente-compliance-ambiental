"""Registro de la revisión humana de las obligaciones (sin IA). No modifica salida/obligaciones/.

El registro es salida/revision/revision_humana.csv. Lo administra este script: no se edita a mano.
Cada línea es una revisión (estado confirmada, corregida o descartada, con fecha, quién y comentario).
Si una obligación se revisa dos veces, vale la última; el historial completo se conserva.
Una obligación sin revisión está "pendiente".

Usos:
    python scripts/registrar_revision.py planilla --ids "ARQ-024 ALB-002..027" [--nombre auditoria]
    python scripts/registrar_revision.py planilla --muestra salida/verificacion/muestra_auditoria_20261123.csv
        Crea salida/revision/planillas/planilla_<nombre>_<AAAAMMDD-HHMMSS>.csv para llenar en Excel o Numbers:
        una fila por obligación con su ID visible, página, descripción y cita, y las columnas vacías
        resultado (confirmada, corregida o descartada), comentario, revisado_por y fecha_revision.

    python scripts/registrar_revision.py importar <planilla.csv> [--por Ignacio] [--fecha AAAA-MM-DD] [--aplicar]
        Revisa la planilla llenada. Sin --aplicar solo muestra el resumen (no registra nada).
        Con --aplicar, si no hay errores, respalda salida/ y agrega las revisiones al registro.
        Si hay un solo error (valor no permitido, ID inexistente o repetido), no registra nada.

    python scripts/registrar_revision.py resumen
        Cuántas obligaciones están revisadas y confirmadas, por RCA.

Los ID se escriben como se ven en el Excel (ARQ-024) o como el ID interno con el archivo (OBL-024).
"""

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

import ids_visibles
import respaldar_salida

ESTADOS = ["confirmada", "corregida", "descartada"]
PENDIENTE = "pendiente"
COLUMNAS_REGISTRO = ["fecha_registro", "archivo", "id_obligacion", "id_visible", "estado", "fecha_revision",
                     "revisado_por", "comentario", "origen"]
COLUMNAS_PLANILLA = ["id_visible", "archivo", "id_obligacion", "pagina_pdf", "tipo", "descripcion", "cita_textual",
                     "resultado", "comentario", "revisado_por", "fecha_revision"]
SEPARADOR = ";"
RANGO = re.compile(r"^([A-Za-z]{2,5})-?(\d{1,4})\.\.(?:[A-Za-z]{2,5}-?)?(\d{1,4})$")


class ErrorRevision(Exception):
    """La planilla o los ID pedidos no se pueden usar; el mensaje explica qué corregir."""


def ruta_registro(salida):
    return Path(salida) / "revision" / "revision_humana.csv"


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)).strip().lower()


# ------------------------------------------------------------------ obligaciones

def cargar_obligaciones(salida):
    """{archivo: {id_obligacion: obligación}} de salida/obligaciones/."""
    todas = {}
    for ruta in sorted((Path(salida) / "obligaciones").glob("*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        archivo = datos.get("archivo") or f"{ruta.stem}.pdf"
        todas[archivo] = {o["id_obligacion"]: o for o in datos.get("obligaciones", [])}
    return todas


def ubicar(texto, archivo, obligaciones, prefijos):
    """(archivo, id_interno) de un ID escrito por el usuario. Lanza ErrorRevision si no existe o es ambiguo."""
    candidatos = ids_visibles.resolver(texto, prefijos)
    if not candidatos:
        raise ErrorRevision(f"«{texto}» no es un ID reconocible (ejemplos: ARQ-024, OBL-024).")
    if archivo:
        candidatos = [(a or archivo, i) for a, i in candidatos if a in (None, archivo)]
    elif candidatos[0][0] is None:
        candidatos = [(a, candidatos[0][1]) for a in obligaciones if candidatos[0][1] in obligaciones[a]]
        if len(candidatos) > 1:
            raise ErrorRevision(f"«{texto}» existe en varias RCAs; use el ID visible (con prefijo) o indique el archivo.")
    candidatos = [(a, i) for a, i in candidatos if i in obligaciones.get(a, {})]
    if not candidatos:
        raise ErrorRevision(f"«{texto}» no existe en las obligaciones extraídas" + (f" de {archivo}." if archivo else "."))
    return candidatos[0]


def expandir(lista):
    """"ARQ-024 ALB-002..027" -> ["ARQ-024", "ALB-002", ..., "ALB-027"]."""
    resultado = []
    for token in re.split(r"[\s,;]+", lista or ""):
        if not token:
            continue
        m = RANGO.match(token)
        if m:
            prefijo, desde, hasta = m.group(1).upper(), int(m.group(2)), int(m.group(3))
            if hasta < desde:
                raise ErrorRevision(f"Rango al revés: {token}.")
            resultado += [f"{prefijo}-{n:03d}" for n in range(desde, hasta + 1)]
        else:
            resultado.append(token)
    return resultado


# ------------------------------------------------------------------ CSV

def leer_csv(ruta):
    """Filas de un CSV (UTF-8, con o sin BOM; separador coma o punto y coma), con encabezados en minúscula."""
    texto = Path(ruta).read_bytes().decode("utf-8-sig")
    primera = texto.splitlines()[0] if texto.strip() else ""
    separador = ";" if primera.count(";") >= primera.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador)
    lector.fieldnames = [sin_tildes(c) for c in lector.fieldnames or []]
    return list(lector)


def escribir_csv(filas, columnas, ruta, agregar=False):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not (agregar and ruta.exists())
    with ruta.open("a" if not nuevo else "w", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, delimiter=SEPARADOR)
        if nuevo:
            escritor.writeheader()
        escritor.writerows(filas)


# ------------------------------------------------------------------ registro

def historial(salida):
    return leer_csv(ruta_registro(salida)) if ruta_registro(salida).exists() else []


def estado_actual(salida):
    """{(archivo, id_obligacion): última revisión registrada}."""
    actual = {}
    for fila in historial(salida):
        actual[(fila["archivo"], fila["id_obligacion"])] = fila
    return actual


def resumen(salida, obligaciones=None):
    """{archivo: {"total", "revisadas", "confirmada", "corregida", "descartada"}}."""
    obligaciones = obligaciones if obligaciones is not None else cargar_obligaciones(salida)
    actual = estado_actual(salida)
    tabla = {}
    for archivo, lista in obligaciones.items():
        conteo = {"total": len(lista), "revisadas": 0, **{e: 0 for e in ESTADOS}}
        for ident in lista:
            fila = actual.get((archivo, ident))
            if fila:
                conteo["revisadas"] += 1
                conteo[fila["estado"]] += 1
        tabla[archivo] = conteo
    return tabla


# ------------------------------------------------------------------ planilla

def crear_planilla(salida, ids, prefijos, nombre="revision", ahora=None):
    """ids: [(archivo o None, texto_id)]. Devuelve la ruta de la planilla creada."""
    obligaciones = cargar_obligaciones(salida)
    filas, vistos, errores = [], set(), []
    for archivo, texto in ids:
        try:
            archivo_real, interno = ubicar(texto, archivo, obligaciones, prefijos)
        except ErrorRevision as error:
            errores.append(str(error))
            continue
        if (archivo_real, interno) in vistos:
            continue
        vistos.add((archivo_real, interno))
        o = obligaciones[archivo_real][interno]
        filas.append({"id_visible": ids_visibles.id_visible(archivo_real, interno, prefijos), "archivo": archivo_real,
                      "id_obligacion": interno, "pagina_pdf": o.get("pagina_pdf"), "tipo": o.get("tipo"),
                      "descripcion": o.get("descripcion"), "cita_textual": o.get("cita_textual"),
                      "resultado": "", "comentario": "", "revisado_por": "", "fecha_revision": ""})
    if errores:
        raise ErrorRevision("No se creó la planilla:\n- " + "\n- ".join(errores))
    marca = (ahora or datetime.now()).strftime("%Y%m%d-%H%M%S")
    destino = Path(salida) / "revision" / "planillas" / f"planilla_{respaldar_salida.nombre_seguro(nombre) or 'revision'}_{marca}.csv"
    escribir_csv(filas, COLUMNAS_PLANILLA, destino)
    return destino


def ids_de_muestra(ruta):
    """[(archivo, ID)] de una muestra de auditoría (columnas RCA o archivo, e ID o id_obligacion)."""
    resultado = []
    for fila in leer_csv(ruta):
        rca = fila.get("rca") or fila.get("archivo") or ""
        ident = fila.get("id") or fila.get("id_obligacion") or fila.get("id_visible") or ""
        resultado.append((rca if rca.endswith(".pdf") else f"{rca}.pdf" if rca else None, ident))
    return resultado


# ------------------------------------------------------------------ importar

def revisar_planilla(ruta, salida, prefijos, por=None, fecha=None):
    """Devuelve (revisiones_validas, sin_llenar, errores). No registra nada."""
    obligaciones = cargar_obligaciones(salida)
    validas, sin_llenar, errores, vistos = [], 0, [], {}
    for numero, fila in enumerate(leer_csv(ruta), start=2):
        resultado = sin_tildes(fila.get("resultado"))
        if not resultado:
            sin_llenar += 1
            continue
        texto_id = fila.get("id_visible") or fila.get("id_obligacion") or fila.get("id") or ""
        try:
            archivo, interno = ubicar(texto_id, fila.get("archivo") or None, obligaciones, prefijos)
        except ErrorRevision as error:
            errores.append(f"Línea {numero}: {error}")
            continue
        if resultado not in ESTADOS:
            errores.append(f"Línea {numero} ({texto_id}): resultado «{fila.get('resultado')}» no permitido; "
                           f"use {', '.join(ESTADOS)}.")
            continue
        if (archivo, interno) in vistos:
            errores.append(f"Línea {numero} ({texto_id}): repite la obligación de la línea {vistos[(archivo, interno)]}.")
            continue
        vistos[(archivo, interno)] = numero
        quien = (fila.get("revisado_por") or por or "").strip()
        if not quien:
            errores.append(f"Línea {numero} ({texto_id}): falta revisado_por (o indíquelo con --por).")
            continue
        cuando = (fila.get("fecha_revision") or fecha or date.today().isoformat()).strip()
        try:
            date.fromisoformat(cuando)
        except ValueError:
            errores.append(f"Línea {numero} ({texto_id}): fecha_revision «{cuando}» debe ser AAAA-MM-DD.")
            continue
        if resultado == "corregida" and not (fila.get("comentario") or "").strip():
            errores.append(f"Línea {numero} ({texto_id}): una fila «corregida» necesita un comentario que diga qué se corrigió.")
            continue
        validas.append({"archivo": archivo, "id_obligacion": interno,
                        "id_visible": ids_visibles.id_visible(archivo, interno, prefijos), "estado": resultado,
                        "fecha_revision": cuando, "revisado_por": quien,
                        "comentario": (fila.get("comentario") or "").strip(), "origen": Path(ruta).name})
    return validas, sin_llenar, errores


def registrar(revisiones, salida, ahora=None):
    """Respalda salida/ y agrega las revisiones al registro. Devuelve la carpeta del respaldo."""
    respaldo = respaldar_salida.respaldar(salida, "antes de registrar revision humana", ahora)
    marca = (ahora or datetime.now()).replace(microsecond=0).isoformat(sep=" ")
    escribir_csv([{**r, "fecha_registro": marca} for r in revisiones], COLUMNAS_REGISTRO, ruta_registro(salida), agregar=True)
    return respaldo


# ------------------------------------------------------------------ línea de comandos

def manifiesto_por_defecto(ruta):
    if ruta and Path(ruta).exists():
        return ruta
    return Path(__file__).resolve().parent.parent / "ejemplos" / "manifiesto_ejemplo.csv"


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Registro de la revisión humana de las obligaciones.")
    parser.add_argument("--salida", default="salida")
    parser.add_argument("--manifiesto", default="manifiesto.csv", help="Para los prefijos de ID (si no existe, el de ejemplo)")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_planilla = sub.add_parser("planilla", help="Crea una planilla para llenar")
    p_planilla.add_argument("--ids", help="IDs separados por espacio; acepta rangos (ALB-002..027)")
    p_planilla.add_argument("--muestra", help="CSV de una muestra de auditoría (columnas RCA e ID)")
    p_planilla.add_argument("--nombre", default="revision")
    p_importar = sub.add_parser("importar", help="Revisa e importa una planilla llenada")
    p_importar.add_argument("planilla")
    p_importar.add_argument("--por", help="Quién revisó, si la planilla no lo dice")
    p_importar.add_argument("--fecha", help="Fecha de la revisión (AAAA-MM-DD), si la planilla no la dice")
    p_importar.add_argument("--aplicar", action="store_true", help="Registrar (sin esto, solo muestra el resumen)")
    sub.add_parser("resumen", help="Revisadas y confirmadas por RCA")
    opciones = parser.parse_args(argumentos)
    prefijos = ids_visibles.prefijos_del_manifiesto(manifiesto_por_defecto(opciones.manifiesto))

    try:
        if opciones.comando == "planilla":
            ids = [(None, i) for i in expandir(opciones.ids)] if opciones.ids else []
            if opciones.muestra:
                ids += ids_de_muestra(opciones.muestra)
            if not ids:
                raise ErrorRevision("Indique --ids o --muestra.")
            destino = crear_planilla(opciones.salida, ids, prefijos, opciones.nombre)
            print(f"== Planilla creada: {destino.as_posix()} ({len(leer_csv(destino))} obligaciones). Llene la columna "
                  f"resultado ({', '.join(ESTADOS)}), comentario (obligatorio si es corregida) y revisado_por.")
            return 0
        if opciones.comando == "importar":
            validas, sin_llenar, errores = revisar_planilla(opciones.planilla, opciones.salida, prefijos, opciones.por, opciones.fecha)
            conteo = {e: sum(1 for r in validas if r["estado"] == e) for e in ESTADOS}
            print(f"== {Path(opciones.planilla).name}: {len(validas)} revisiones válidas "
                  f"({', '.join(f'{n} {e}s' for e, n in conteo.items())}), {sin_llenar} filas sin llenar, {len(errores)} errores.")
            for error in errores:
                print(f"   ERROR: {error}")
            if errores:
                print("No se registró nada. Corrija la planilla y vuelva a importarla.")
                return 1
            if not opciones.aplicar:
                print("Simulación: no se registró nada. Para registrar, repita con --aplicar.")
                return 0
            respaldo = registrar(validas, opciones.salida)
            print(f"Registradas en {ruta_registro(opciones.salida).as_posix()} (respaldo previo: {respaldo.as_posix()}).")
            return 0
        tabla = resumen(opciones.salida)
        for archivo, c in tabla.items():
            print(f"   {archivo}: {c['revisadas']} de {c['total']} revisadas ({c['confirmada']} confirmadas, "
                  f"{c['corregida']} corregidas, {c['descartada']} descartadas); {c['total'] - c['revisadas']} pendientes")
        return 0
    except ErrorRevision as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
