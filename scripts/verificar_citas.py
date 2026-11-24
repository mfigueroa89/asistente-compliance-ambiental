"""Comprueba por código que cada cita textual exista en la página indicada (versión simple).

Uso:
    python scripts/verificar_citas.py RESULTADO_JSON TEXTO_JSON [--salida salida] [--umbral 0.90] [--umbral-ocr 0.80]

RESULTADO_JSON es una ficha (salida/fichas/) u otro JSON con datos que tengan "pagina_pdf" y "cita_textual".
TEXTO_JSON es el texto de la RCA generado por leer_pdf.py (salida/texto/).
Resultado: salida/verificacion/<archivo>_citas.json y un resumen en pantalla. No modifica la ficha.

Estados posibles de cada cita:
    "confirmada"                    aparece tal cual en la página (sin contar tildes, mayúsculas ni espacios)
    "aproximada"                    aparece con pequeñas diferencias (similitud sobre el umbral); típico del OCR
    "encontrada en otra página"     no está en la página indicada, pero sí en otra (se indica cuál)
    "no encontrada en esa página"   no aparece ni en esa página ni en otra
    "leída en imagen"               el dato se leyó en la imagen de la página: no se puede comprobar con el texto
"""

import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

UMBRAL = 0.90
UMBRAL_OCR = 0.80
LARGO_MINIMO_BLOQUE = 4


def normalizar(texto):
    """Quita tildes, mayúsculas, comillas tipográficas, guiones de corte y espacios repetidos."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = texto.lower()
    texto = re.sub(r"[\"'`´«»]", "", texto)
    texto = re.sub(r"[‐‑‒–—―]", "-", texto)
    return re.sub(r"\s+", " ", texto).strip()


def mejor_similitud(cita, texto):
    """Similitud (0 a 1) entre la cita y el tramo de la página que más se le parece."""
    if not cita or not texto:
        return 0.0
    if cita in texto:
        return 1.0
    comparador = SequenceMatcher(None, cita, texto, autojunk=False)
    mejor = 0.0
    inicios = {bloque.b - bloque.a for bloque in comparador.get_matching_blocks() if bloque.size >= LARGO_MINIMO_BLOQUE}
    for inicio in inicios:
        ventana = texto[max(0, inicio): max(0, inicio) + len(cita)]
        mejor = max(mejor, SequenceMatcher(None, cita, ventana, autojunk=False).ratio())
    return mejor


def verificar_cita(cita, pagina, paginas, umbral=UMBRAL, umbral_ocr=UMBRAL_OCR, fuente=None):
    """Verifica una cita. paginas es la lista de páginas de leer_pdf.py (con "numero_pdf", "texto", "origen_texto")."""
    if fuente == "imagen":
        return {"estado": "leída en imagen", "similitud": None, "pagina_encontrada": None}
    cita_normal = normalizar(cita)
    por_numero = {p["numero_pdf"]: p for p in paginas}

    def umbral_de(p):
        return umbral_ocr if p.get("origen_texto") == "ocr_previo" else umbral

    indicada = por_numero.get(pagina)
    if indicada is not None:
        similitud = mejor_similitud(cita_normal, normalizar(indicada["texto"]))
        if similitud == 1.0:
            return {"estado": "confirmada", "similitud": 1.0, "pagina_encontrada": pagina}
        if similitud >= umbral_de(indicada):
            return {"estado": "aproximada", "similitud": round(similitud, 3), "pagina_encontrada": pagina}
    else:
        similitud = 0.0

    # Buscar en las demás páginas (primero exacto, luego aproximado).
    candidatos = []
    for otra in paginas:
        if otra["numero_pdf"] == pagina:
            continue
        texto_otra = normalizar(otra["texto"])
        if cita_normal and cita_normal in texto_otra:
            return {"estado": "encontrada en otra página", "similitud": 1.0, "pagina_encontrada": otra["numero_pdf"]}
        candidatos.append(otra)
    for otra in candidatos:
        similitud_otra = mejor_similitud(cita_normal, normalizar(otra["texto"]))
        if similitud_otra >= umbral_de(otra):
            return {"estado": "encontrada en otra página", "similitud": round(similitud_otra, 3), "pagina_encontrada": otra["numero_pdf"]}
    return {"estado": "no encontrada en esa página", "similitud": round(similitud, 3), "pagina_encontrada": None}


def recorrer_datos(objeto, ruta=""):
    """Entrega (ruta, dato) por cada diccionario que tenga "cita_textual" con valor."""
    if isinstance(objeto, dict):
        if objeto.get("cita_textual"):
            yield ruta, objeto
            return
        for clave, valor in objeto.items():
            yield from recorrer_datos(valor, f"{ruta}.{clave}" if ruta else clave)
    elif isinstance(objeto, list):
        for indice, valor in enumerate(objeto):
            yield from recorrer_datos(valor, f"{ruta}[{indice}]")


def verificar(resultado, texto, umbral=UMBRAL, umbral_ocr=UMBRAL_OCR):
    """Verifica todas las citas de un resultado (ficha u obligaciones) contra el texto de la RCA."""
    citas = []
    for ruta, dato in recorrer_datos(resultado):
        veredicto = verificar_cita(
            dato["cita_textual"], dato.get("pagina_pdf"), texto["paginas"], umbral, umbral_ocr, dato.get("fuente")
        )
        citas.append({"campo": ruta, "pagina_pdf": dato.get("pagina_pdf"), "cita_textual": dato["cita_textual"], **veredicto})
    resumen = {}
    for cita in citas:
        resumen[cita["estado"]] = resumen.get(cita["estado"], 0) + 1
    return {"archivo": texto["archivo"], "umbral": umbral, "umbral_ocr": umbral_ocr, "resumen": resumen, "citas": citas}


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Comprueba que cada cita exista en la página indicada.")
    parser.add_argument("resultado", help="Ficha u otro JSON con citas")
    parser.add_argument("texto", help="JSON de salida/texto/ de la misma RCA")
    parser.add_argument("--salida", default="salida")
    parser.add_argument("--umbral", type=float, default=UMBRAL)
    parser.add_argument("--umbral-ocr", type=float, default=UMBRAL_OCR)
    opciones = parser.parse_args(argumentos)
    with open(opciones.resultado, encoding="utf-8") as archivo:
        resultado = json.load(archivo)
    with open(opciones.texto, encoding="utf-8") as archivo:
        texto = json.load(archivo)
    informe = verificar(resultado, texto, opciones.umbral, opciones.umbral_ocr)
    destino = Path(opciones.salida) / "verificacion" / f"{Path(texto['archivo']).stem}_citas.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"== {informe['archivo']}: {informe['resumen']} -> {destino.as_posix()}")
    for cita in informe["citas"]:
        if cita["estado"] not in ("confirmada",):
            detalle = f" (está en p. {cita['pagina_encontrada']})" if cita["estado"] == "encontrada en otra página" else ""
            print(f"   {cita['estado']}{detalle}: {cita['campo']} p. {cita['pagina_pdf']} «{cita['cita_textual'][:70]}»")
    return 0


if __name__ == "__main__":
    sys.exit(main())
