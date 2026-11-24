"""Contrasta el buscador exacto (buscar_palabras.py) con una búsqueda como la del visor de PDF (sin IA).

Uso:
    python scripts/contrastar_busqueda.py --pdfs ejemplos/rcas_publicas [--salida salida] [--temas config/temas.yaml]

Para cada RCA, página y término de config/temas.yaml compara:
    - BUSCADOR: buscar_palabras.py (sin mayúsculas ni tildes, plural simple, solo palabras completas);
    - VISOR: lo que hace Cmd+F / Ctrl+F en un visor de PDF: busca el término tal como se escribe, sin distinguir
      mayúsculas, como trozo de texto (también dentro de otras palabras). Se prueba la grafía con y sin tildes.
Ambos leen la capa de texto del PDF (la misma que usa el visor). El buscador se aplica además al texto de
salida/texto/ para comprobar que leer_pdf.py no cambió los resultados.

Cada diferencia se clasifica:
    "visor: dentro de otra palabra"   p. ej. "flora" en "afloramiento" o "vega" en "navegar" (el buscador la descarta)
    "buscador: plural o variante"     p. ej. "comunidades indígenas" al buscar "comunidad indígena" (el visor no la iguala)
    "texto de leer_pdf distinto"      el buscador da otro número sobre salida/texto/ (palabra cortada con guion, etc.)
    "POSIBLE OMISIÓN"                 el visor encuentra el término como palabra completa y el buscador no: hay que revisarlo

Límites: las páginas escaneadas sin texto no se pueden buscar por ninguno de los dos; en páginas con OCR previo, ambos
leen el mismo OCR, así que un término mal leído por el OCR no lo encuentra ninguno.
Resultado: salida/verificacion/contraste_busqueda.csv y un resumen en pantalla. Termina con código 1 si hay
posibles omisiones.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

import buscar_palabras as bp

DENTRO = "visor: dentro de otra palabra"
VARIANTE = "buscador: plural o variante"
LEER_PDF = "texto de leer_pdf distinto"
OMISION = "POSIBLE OMISIÓN"
COLUMNAS = ["archivo", "pagina_pdf", "tema", "termino", "buscador", "visor", "coinciden",
            "solo_buscador", "solo_visor", "buscador_en_salida_texto", "clasificacion"]


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def buscar_como_visor(texto, termino):
    """Tramos (inicio, fin) donde el término aparece como trozo de texto, sin distinguir mayúsculas,
    escrito con o sin tildes (así lo encuentra el visor; las tildes del texto no se ignoran)."""
    bajo = texto.lower()
    tramos = set()
    for grafia in {termino.lower(), sin_tildes(termino).lower()}:
        for m in re.finditer(re.escape(grafia), bajo):
            tramos.add((m.start(), m.end()))
    return sorted(tramos)


def palabra_que_contiene(texto, inicio, fin):
    antes = re.search(r"\S*$", texto[:inicio]).group(0)
    despues = re.match(r"\S*", texto[fin:]).group(0)
    return antes + texto[inicio:fin] + despues


def se_solapan(a, b):
    return a[0] < b[1] and b[0] < a[1]


def contrastar_pagina(texto_pdf, texto_salida, termino):
    """Compara buscador y visor en una página. texto_pdf: capa de texto del PDF; texto_salida: la de salida/texto/."""
    texto = " ".join((texto_pdf or "").split())
    buscador = [(a, b) for a, b, _ in bp.buscar(texto, termino)]
    visor = buscar_como_visor(texto, termino)
    solo_buscador = [texto[a:b] for a, b in buscador if not any(se_solapan((a, b), v) for v in visor)]
    solo_visor, omisiones = [], []
    for v in visor:
        if any(se_solapan(v, x) for x in buscador):
            continue
        palabra = palabra_que_contiene(texto, *v)
        (omisiones if bp.buscar(palabra.strip(".,;:()[]“”\"'«»"), termino) else solo_visor).append(palabra)
    en_salida = len(bp.buscar(texto_salida or "", termino))
    clases = []
    if solo_visor:
        clases.append(DENTRO)
    if solo_buscador:
        clases.append(VARIANTE)
    if en_salida != len(buscador):
        clases.append(LEER_PDF)
    if omisiones:
        clases.append(OMISION)
    return {"buscador": len(buscador), "visor": len(visor), "coinciden": len(buscador) - len(solo_buscador),
            "solo_buscador": solo_buscador, "solo_visor": solo_visor + omisiones,
            "buscador_en_salida_texto": en_salida, "clasificacion": clases}


def contrastar_rca(ruta_pdf, texto, temas):
    """Filas del contraste de una RCA (solo páginas y términos donde alguno de los dos encuentra algo)."""
    filas = []
    documento = pymupdf.open(ruta_pdf)
    try:
        for pagina in texto["paginas"]:
            texto_pdf = documento[pagina["numero_pdf"] - 1].get_text()
            for tema, terminos in temas.items():
                for termino in terminos:
                    r = contrastar_pagina(texto_pdf, pagina.get("texto"), termino)
                    if r["buscador"] or r["visor"] or r["buscador_en_salida_texto"]:
                        filas.append({"archivo": texto["archivo"], "pagina_pdf": pagina["numero_pdf"], "tema": tema,
                                      "termino": termino, **r})
    finally:
        documento.close()
    return filas


def resumen(filas):
    total = {"buscador": 0, "visor": 0, "coinciden": 0, DENTRO: 0, VARIANTE: 0, LEER_PDF: 0, OMISION: 0}
    for f in filas:
        total["buscador"] += f["buscador"]
        total["visor"] += f["visor"]
        total["coinciden"] += f["coinciden"]
        total[VARIANTE] += len(f["solo_buscador"])
        total[DENTRO] += len(f["solo_visor"]) if OMISION not in f["clasificacion"] else 0
        total[OMISION] += 1 if OMISION in f["clasificacion"] else 0
        total[LEER_PDF] += 1 if LEER_PDF in f["clasificacion"] else 0
    return total


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Contrasta el buscador con una búsqueda como la del visor de PDF.")
    parser.add_argument("--pdfs", default="rcas", help="Carpeta de los PDFs")
    parser.add_argument("--salida", default="salida")
    parser.add_argument("--temas", default=str(bp.TEMAS_POR_DEFECTO))
    opciones = parser.parse_args(argumentos)
    temas = bp.cargar_temas(opciones.temas)
    todas = []
    for ruta_texto in sorted((Path(opciones.salida) / "texto").glob("*.json")):
        texto = json.loads(ruta_texto.read_text(encoding="utf-8"))
        ruta_pdf = Path(opciones.pdfs) / texto["archivo"]
        if not ruta_pdf.exists():
            continue
        filas = contrastar_rca(ruta_pdf, texto, temas)
        todas += filas
        t = resumen(filas)
        print(f"== {texto['archivo']}: buscador {t['buscador']}, visor {t['visor']}, coinciden {t['coinciden']}; "
              f"visor dentro de otra palabra {t[DENTRO]}; buscador plural o variante {t[VARIANTE]}; "
              f"páginas con texto de leer_pdf distinto {t[LEER_PDF]}; POSIBLES OMISIONES {t[OMISION]}")
        sin_texto = [p["numero_pdf"] for p in texto["paginas"] if bp.pagina_sin_texto(p)]
        if sin_texto:
            print(f"   páginas sin texto (ninguno de los dos puede buscar): {', '.join(map(str, sin_texto))}")
        for f in filas:
            if OMISION in f["clasificacion"]:
                print(f"   POSIBLE OMISIÓN p. {f['pagina_pdf']} «{f['termino']}»: {f['solo_visor']}")
    if not todas:
        print("No hay RCAs con PDF y texto para contrastar.")
        return 1
    destino = Path(opciones.salida) / "verificacion" / "contraste_busqueda.csv"
    bp.guardar_csv([{**f, "solo_buscador": " | ".join(f["solo_buscador"]) or "—",
                     "solo_visor": " | ".join(f["solo_visor"]) or "—",
                     "clasificacion": "; ".join(f["clasificacion"]) or "igual"} for f in todas], COLUMNAS, destino)
    print(f"Resultado: {destino.as_posix()}")
    return 1 if resumen(todas)[OMISION] else 0


if __name__ == "__main__":
    sys.exit(main())
