"""Lee y valida manifiesto.csv (sin IA).

Uso:
    python scripts/leer_manifiesto.py MANIFIESTO_CSV [--rcas CARPETA_DE_PDFS]

Qué revisa:
    - Codificación: el archivo debe estar en UTF-8 (con o sin BOM, como lo guarda Excel con
      "CSV UTF-8"). Si no lo está, o trae caracteres mal codificados (por ejemplo "Ã³" en vez
      de "ó", o el símbolo "�"), se detiene con un error que indica la fila y cómo corregirlo.
    - Separador: acepta coma o punto y coma (Excel en español suele usar punto y coma) y avisa
      cuál detectó.
    - Columnas obligatorias: archivo, unidad_fiscalizable, proyecto.
    - Relación muchos a muchos: un mismo PDF puede aparecer en varias filas (una RCA en varias
      unidades fiscalizables) y una unidad puede tener varias RCAs. Lo que no puede repetirse es
      el mismo par (archivo, unidad_fiscalizable).
    - Una fila sin unidad fiscalizable queda como "SIN UF ASIGNADA" (con aviso).
    - Columnas opcionales enlace_eseia (ficha del expediente en el e-SEIA, una por RCA) y nota_uf (nota sobre la
      unidad fiscalizable, por ejemplo la fecha en que se buscó en SNIFA). Un manifiesto sin ellas sigue sirviendo.
      Avisa si un enlace no empieza con http:// o https://, o si una misma RCA trae enlaces distintos (se usa el primero).
    - Columna opcional prefijo_id (2 a 5 letras mayúsculas, por ejemplo ARQ): el ID visible de las obligaciones de esa RCA
      (ARQ-024 en vez de OBL-024). Uno por RCA y distinto entre RCAs; si no, se detiene con un error claro.
    - Con --rcas: avisa si una fila nombra un PDF que no está en la carpeta; un PDF de la
      carpeta sin fila en el manifiesto se incluye bajo "SIN UF ASIGNADA", con aviso.
"""

import argparse
import csv
import io
import re
import sys
from pathlib import Path

COLUMNAS = ["archivo", "unidad_fiscalizable", "id_uf_snifa", "enlace_uf_snifa", "proyecto", "titular", "region", "notas",
            "enlace_eseia", "nota_uf", "prefijo_id"]
OBLIGATORIAS = ["archivo", "unidad_fiscalizable", "proyecto"]
SIN_UF = "SIN UF ASIGNADA"
SEPARADORES = {",": "coma", ";": "punto y coma"}

COMO_GUARDAR = (
    "Cómo corregirlo: abra el archivo en Excel y use Archivo > Guardar como > "
    "\"CSV UTF-8 (delimitado por comas)\"; o en Numbers, Exportar a > CSV con codificación Unicode (UTF-8)."
)

# Restos típicos de texto UTF-8 leído como Latin-1/Windows-1252 ("Ã³" en vez de "ó", "Â°" en vez de "°")
# y el carácter de reemplazo "�", que indica bytes perdidos.
MAL_CODIFICADO = re.compile(r"Ã[\u0080-¿‚-™Œ-Ÿ]|Â[\u0080-¿]|�")


class ErrorManifiesto(Exception):
    """Error del manifiesto que impide seguir; el mensaje explica qué corregir."""


def decodificar(contenido):
    """Bytes -> texto UTF-8 (acepta BOM). Si no es UTF-8 válido, error con número de línea."""
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        linea = contenido[: error.start].count(b"\n") + 1
        raise ErrorManifiesto(
            f"manifiesto.csv no está guardado en UTF-8: hay un carácter que no se puede leer en la línea {linea}. "
            + COMO_GUARDAR
        ) from None


def revisar_caracteres(texto):
    """Busca caracteres mal codificados; devuelve la primera aparición como error claro."""
    for numero, linea in enumerate(texto.splitlines(), start=1):
        encontrado = MAL_CODIFICADO.search(linea)
        if encontrado:
            fragmento = linea[max(0, encontrado.start() - 15): encontrado.end() + 15]
            raise ErrorManifiesto(
                f"manifiesto.csv tiene caracteres mal codificados en la línea {numero}: «{fragmento}» "
                f"(probablemente una tilde o una ñ que se guardó con otra codificación). " + COMO_GUARDAR
            )


def detectar_separador(texto):
    """Coma o punto y coma, según cuál separa el encabezado en las columnas esperadas."""
    encabezado = texto.splitlines()[0] if texto.strip() else ""
    mejor, columnas_reconocidas = ",", -1
    for separador in SEPARADORES:
        nombres = {c.strip().lower() for c in encabezado.split(separador)}
        reconocidas = len(nombres & set(COLUMNAS))
        if reconocidas > columnas_reconocidas:
            mejor, columnas_reconocidas = separador, reconocidas
    return mejor


def enlaces_eseia(filas):
    """{archivo: primer enlace_eseia no vacío}; una RCA puede tener varias filas (varias unidades)."""
    enlaces = {}
    for fila in filas:
        if fila.get("enlace_eseia"):
            enlaces.setdefault(fila["archivo"], fila["enlace_eseia"])
    return enlaces


def revisar_enlaces(filas):
    """Avisos sobre enlace_eseia: que sea un enlace web y que no haya dos distintos para la misma RCA."""
    avisos, vistos = [], {}
    for fila in filas:
        enlace = fila.get("enlace_eseia", "")
        if not enlace:
            continue
        if not enlace.lower().startswith(("http://", "https://")):
            avisos.append(f"Línea {fila['linea']}: enlace_eseia \"{enlace}\" no empieza con http:// o https://; "
                          f"se muestra como texto, sin hipervínculo.")
        anterior = vistos.setdefault(fila["archivo"], (enlace, fila["linea"]))
        if anterior[0] != enlace:
            avisos.append(f"Línea {fila['linea']}: \"{fila['archivo']}\" trae un enlace_eseia distinto al de la línea "
                          f"{anterior[1]}; se usa el de la línea {anterior[1]}.")
    return avisos


def leer_manifiesto(ruta, carpeta_rcas=None):
    """Lee y valida el manifiesto.

    Devuelve {"filas": [...], "separador": "coma"|"punto y coma", "avisos": [...]}.
    Cada fila trae las columnas de COLUMNAS (texto, "" si vacía) y "linea" (línea del CSV).
    Lanza ErrorManifiesto si el archivo no se puede usar.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorManifiesto(f"No existe el manifiesto: {ruta}")
    texto = decodificar(ruta.read_bytes())
    revisar_caracteres(texto)
    if not texto.strip():
        raise ErrorManifiesto("manifiesto.csv está vacío.")

    separador = detectar_separador(texto)
    lector = csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador)
    lector.fieldnames = [(nombre or "").strip().lower() for nombre in (lector.fieldnames or [])]
    faltantes = [c for c in OBLIGATORIAS if c not in lector.fieldnames]
    if faltantes:
        raise ErrorManifiesto(
            f"Faltan columnas obligatorias en manifiesto.csv: {', '.join(faltantes)}. "
            f"El encabezado debe tener al menos: {', '.join(OBLIGATORIAS)} (separador detectado: {SEPARADORES[separador]})."
        )

    avisos = [f"Separador detectado: {SEPARADORES[separador]}."]
    desconocidas = [c for c in lector.fieldnames if c and c not in COLUMNAS]
    if desconocidas:
        avisos.append(f"Columnas no reconocidas (se ignoran): {', '.join(desconocidas)}.")

    filas, errores, vistos = [], [], {}
    for numero, cruda in enumerate(lector, start=2):
        valores = {c: (cruda.get(c) or "").strip() for c in COLUMNAS}
        if not any(valores.values()):
            continue  # fila en blanco
        if None in cruda:
            errores.append(f"Línea {numero}: tiene más columnas que el encabezado (¿un separador de más dentro de un texto?).")
        for columna in ("archivo", "proyecto"):
            if not valores[columna]:
                errores.append(f"Línea {numero}: falta el valor de la columna obligatoria \"{columna}\".")
        if not valores["unidad_fiscalizable"]:
            valores["unidad_fiscalizable"] = SIN_UF
            avisos.append(f"Línea {numero}: sin unidad fiscalizable; queda como \"{SIN_UF}\".")
        if valores["archivo"] and not valores["archivo"].lower().endswith(".pdf"):
            avisos.append(f"Línea {numero}: \"{valores['archivo']}\" no termina en .pdf.")
        clave = (valores["archivo"].lower(), valores["unidad_fiscalizable"].lower())
        if valores["archivo"] and clave in vistos:
            errores.append(
                f"Línea {numero}: repite el par archivo \"{valores['archivo']}\" y unidad fiscalizable "
                f"\"{valores['unidad_fiscalizable']}\" de la línea {vistos[clave]}."
            )
        vistos.setdefault(clave, numero)
        filas.append({**valores, "linea": numero})

    import ids_visibles
    errores += ids_visibles.validar_prefijos(filas)
    if errores:
        raise ErrorManifiesto("manifiesto.csv tiene errores:\n- " + "\n- ".join(errores))
    if not filas:
        raise ErrorManifiesto("manifiesto.csv no tiene filas con datos.")
    avisos += revisar_enlaces(filas)

    if carpeta_rcas is not None:
        carpeta = Path(carpeta_rcas)
        en_carpeta = {p.name for p in carpeta.glob("*.pdf")} | {p.name for p in carpeta.glob("*.PDF")}
        nombrados = {f["archivo"] for f in filas}
        for faltante in sorted(nombrados - en_carpeta):
            avisos.append(f"El manifiesto nombra \"{faltante}\", pero no está en {carpeta.as_posix()}/; queda marcado \"sin PDF en la carpeta\".")
        for sobrante in sorted(en_carpeta - nombrados):
            avisos.append(f"\"{sobrante}\" está en {carpeta.as_posix()}/ pero no tiene fila en el manifiesto; "
                          f"se incluye bajo \"{SIN_UF}\".")
            filas.append({**{c: "" for c in COLUMNAS}, "archivo": sobrante, "unidad_fiscalizable": SIN_UF,
                          "proyecto": "No consta (sin fila en el manifiesto)", "linea": None})
    return {"filas": filas, "separador": SEPARADORES[separador], "avisos": avisos}


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Lee y valida manifiesto.csv.")
    parser.add_argument("manifiesto", help="Ruta de manifiesto.csv")
    parser.add_argument("--rcas", help="Carpeta de los PDFs, para comprobar que coincidan con el manifiesto")
    opciones = parser.parse_args(argumentos)
    try:
        resultado = leer_manifiesto(opciones.manifiesto, opciones.rcas)
    except ErrorManifiesto as error:
        print(f"ERROR: {error}")
        return 1
    filas = resultado["filas"]
    print(f"== {opciones.manifiesto}: {len(filas)} filas, {len({f['archivo'] for f in filas})} PDFs, "
          f"{len({f['unidad_fiscalizable'] for f in filas})} unidades fiscalizables")
    for aviso in resultado["avisos"]:
        print(f"   aviso: {aviso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
