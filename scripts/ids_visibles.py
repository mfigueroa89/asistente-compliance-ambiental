"""ID visible de las obligaciones (sin IA): ARQ-024 en vez de OBL-024.

Los IDs internos (OBL-001, OBL-002...) no cambian: están en salida/obligaciones/ y en todas las referencias.
El ID visible solo antepone el prefijo de la RCA, que se define en la columna opcional prefijo_id del manifiesto
(2 a 5 letras mayúsculas, uno por RCA, sin repetirse entre RCAs). Si una RCA no tiene prefijo, se muestra el ID interno.

Uso (para probar una conversión):
    python scripts/ids_visibles.py ARQ-024 [--manifiesto manifiesto.csv]
"""

import argparse
import re
import sys
from pathlib import Path

FORMATO_PREFIJO = re.compile(r"^[A-Z]{2,5}$")
PATRON_ID = re.compile(r"^\s*([A-Za-z]{2,5})[\s\-_]*0*(\d{1,4})\s*$")
PREFIJO_INTERNO = "OBL"


def prefijos_de(filas_manifiesto):
    """{archivo: prefijo} desde las filas de leer_manifiesto (solo las que traen prefijo_id)."""
    prefijos = {}
    for fila in filas_manifiesto:
        if fila.get("prefijo_id"):
            prefijos.setdefault(fila["archivo"], fila["prefijo_id"])
    return prefijos


def prefijos_del_manifiesto(ruta):
    """{archivo: prefijo} leyendo el manifiesto; {} si no existe o no se puede leer."""
    if ruta is None or not Path(ruta).exists():
        return {}
    import leer_manifiesto
    try:
        return prefijos_de(leer_manifiesto.leer_manifiesto(ruta)["filas"])
    except leer_manifiesto.ErrorManifiesto:
        return {}


def numero_de(id_interno):
    m = re.match(rf"^{PREFIJO_INTERNO}-(\d+)$", str(id_interno or ""))
    return m.group(1) if m else None


def id_visible(archivo, id_interno, prefijos):
    """"ARQ-024" para ("rca_151...pdf", "OBL-024"); el ID interno si la RCA no tiene prefijo."""
    numero = numero_de(id_interno)
    prefijo = (prefijos or {}).get(archivo)
    if not prefijo or numero is None:
        return id_interno
    return f"{prefijo}-{numero}"


def resolver(texto, prefijos, ancho=3):
    """Lo que escribió el usuario ("ARQ-024", "arq 24", "OBL-024") -> [(archivo o None, "OBL-024")].
    Con prefijo de RCA devuelve esa RCA; con "OBL" devuelve (None, id): vale para cualquier RCA. [] si no es un ID."""
    m = PATRON_ID.match(texto or "")
    if not m:
        return []
    prefijo, numero = m.group(1).upper(), m.group(2).zfill(ancho)
    interno = f"{PREFIJO_INTERNO}-{numero}"
    if prefijo == PREFIJO_INTERNO:
        return [(None, interno)]
    return [(archivo, interno) for archivo, p in sorted((prefijos or {}).items()) if p == prefijo]


def validar_prefijos(filas):
    """Errores de la columna prefijo_id: formato, distinto en dos filas de la misma RCA, repetido entre RCAs."""
    errores, por_archivo, por_prefijo = [], {}, {}
    for fila in filas:
        prefijo = fila.get("prefijo_id") or ""
        if not prefijo:
            continue
        donde = f"Línea {fila.get('linea')}" if fila.get("linea") else fila["archivo"]
        if not FORMATO_PREFIJO.match(prefijo) or prefijo == PREFIJO_INTERNO:
            errores.append(f"{donde}: prefijo_id \"{prefijo}\" debe tener de 2 a 5 letras mayúsculas sin tildes "
                           f"(por ejemplo ARQ) y no puede ser \"{PREFIJO_INTERNO}\".")
            continue
        anterior = por_archivo.setdefault(fila["archivo"], prefijo)
        if anterior != prefijo:
            errores.append(f"{donde}: \"{fila['archivo']}\" trae prefijo_id \"{prefijo}\" y antes \"{anterior}\"; "
                           f"una RCA lleva un solo prefijo.")
        otro = por_prefijo.setdefault(prefijo, fila["archivo"])
        if otro != fila["archivo"]:
            errores.append(f"{donde}: el prefijo_id \"{prefijo}\" ya se usa para \"{otro}\"; cada RCA lleva uno distinto.")
    return errores


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Convierte un ID visible (ARQ-024) al ID interno de su RCA.")
    parser.add_argument("id", help="ID visible o interno, por ejemplo ARQ-024 u OBL-024")
    parser.add_argument("--manifiesto", default="manifiesto.csv")
    opciones = parser.parse_args(argumentos)
    ruta = opciones.manifiesto
    if not Path(ruta).exists():
        ruta = Path(__file__).resolve().parent.parent / "ejemplos" / "manifiesto_ejemplo.csv"
    resultado = resolver(opciones.id, prefijos_del_manifiesto(ruta))
    if not resultado:
        print(f"«{opciones.id}» no corresponde a ningún prefijo del manifiesto ({ruta}).")
        return 1
    for archivo, interno in resultado:
        print(f"{opciones.id} -> {interno} en {archivo or 'cualquier RCA (ID interno)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
