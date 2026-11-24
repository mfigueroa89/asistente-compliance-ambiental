"""Muestra en pantalla páginas de una RCA ya leída, o busca dónde aparece un término (sin IA).

Uso:
    python scripts/mostrar_paginas.py TEXTO_JSON --paginas 1-3,34,53-57
    python scripts/mostrar_paginas.py TEXTO_JSON --localizador ficha        (páginas para la ficha)
    python scripts/mostrar_paginas.py TEXTO_JSON --buscar "vida útil" --buscar "monto"

TEXTO_JSON es el archivo de salida/texto/ generado por leer_pdf.py. Con --localizador se usa
salida/secciones/<archivo>.json (generado por localizar_secciones.py).

Cada página se muestra con su número real del PDF, su número impreso y sus avisos
(OCR previo, escaneada, requiere lectura visual con la ruta de la imagen).
La búsqueda no distingue mayúsculas ni tildes y muestra un fragmento de contexto por aparición.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

CONTEXTO = 150
MAXIMO_APARICIONES = 30


def parsear_rango(texto, n_paginas):
    """"1-3,7,10-12" -> [1, 2, 3, 7, 10, 11, 12] (solo páginas que existen)."""
    paginas = set()
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            inicio, fin = parte.split("-", 1)
            paginas.update(range(int(inicio), int(fin) + 1))
        else:
            paginas.add(int(parte))
    return sorted(p for p in paginas if 1 <= p <= n_paginas)


def comprimir_rango(paginas):
    """[1, 2, 3, 7] -> "1-3, 7"."""
    tramos, inicio, anterior = [], None, None
    for pagina in sorted(paginas):
        if inicio is None:
            inicio = anterior = pagina
        elif pagina == anterior + 1:
            anterior = pagina
        else:
            tramos.append(f"{inicio}-{anterior}" if anterior != inicio else f"{inicio}")
            inicio = anterior = pagina
    if inicio is not None:
        tramos.append(f"{inicio}-{anterior}" if anterior != inicio else f"{inicio}")
    return ", ".join(tramos)


def encabezado(pagina):
    marcas = []
    if pagina.get("numero_impreso"):
        marcas.append(f"impresa {pagina['numero_impreso']}")
    if pagina.get("origen_texto") == "ocr_previo":
        marcas.append("OCR PREVIO: confirmar citas contra la imagen")
    if pagina.get("estado") in ("escaneada", "en_blanco", "poco_texto"):
        marcas.append(pagina["estado"].upper())
    if pagina.get("requiere_lectura_visual"):
        motivos = "; ".join(pagina.get("motivos_lectura_visual", []))
        marcas.append(f"LECTURA VISUAL ({motivos}): {pagina.get('imagen') or 'sin imagen generada'}")
    extra = f" [{' | '.join(marcas)}]" if marcas else ""
    return f"===== Página PDF {pagina['numero_pdf']}{extra} ====="


def mostrar(texto_rca, paginas):
    por_numero = {p["numero_pdf"]: p for p in texto_rca["paginas"]}
    salida = [f"### {texto_rca['archivo']}: páginas {comprimir_rango(paginas)} de {len(por_numero)}"]
    for numero in paginas:
        pagina = por_numero[numero]
        salida.append(encabezado(pagina))
        salida.append(pagina["texto"] or "(sin texto)")
    return "\n".join(salida)


def normalizar(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def buscar(texto_rca, terminos):
    """Devuelve, por término, la lista de apariciones con página y contexto (búsqueda exacta, sin IA)."""
    resultados = {}
    for termino in terminos:
        patron = re.compile(re.escape(normalizar(termino)))
        apariciones = []
        for pagina in texto_rca["paginas"]:
            original = pagina["texto"]
            # La normalización conserva el largo del texto en casi todos los casos; si no, se usa el texto normalizado.
            normal = normalizar(original)
            fuente = original if len(normal) == len(original) else normal
            for coincidencia in patron.finditer(normal):
                inicio, fin = coincidencia.start(), coincidencia.end()
                contexto = fuente[max(0, inicio - CONTEXTO): fin + CONTEXTO].replace("\n", " ")
                apariciones.append({"pagina": pagina["numero_pdf"], "contexto": contexto})
        resultados[termino] = apariciones
    return resultados


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Muestra páginas de una RCA o busca términos en ella.")
    parser.add_argument("texto", help="JSON de salida/texto/")
    parser.add_argument("--paginas", help='Rango, por ejemplo "1-3,34,53-57"')
    parser.add_argument("--localizador", choices=["ficha", "obligaciones"], help="Usar las páginas propuestas por localizar_secciones.py")
    parser.add_argument("--secciones", help="JSON de salida/secciones/ (por defecto se deduce del nombre)")
    parser.add_argument("--buscar", action="append", default=[], help="Término a buscar (se puede repetir)")
    opciones = parser.parse_args(argumentos)

    ruta = Path(opciones.texto)
    texto_rca = json.loads(ruta.read_text(encoding="utf-8"))
    n_paginas = len(texto_rca["paginas"])

    if opciones.buscar:
        for termino, apariciones in buscar(texto_rca, opciones.buscar).items():
            paginas = sorted({a["pagina"] for a in apariciones})
            print(f"### «{termino}»: {len(apariciones)} apariciones en páginas {comprimir_rango(paginas) or '(ninguna)'}")
            for aparicion in apariciones[:MAXIMO_APARICIONES]:
                print(f"   p{aparicion['pagina']}: ...{aparicion['contexto']}...")
            if len(apariciones) > MAXIMO_APARICIONES:
                print(f"   (se muestran {MAXIMO_APARICIONES} de {len(apariciones)})")
            sin_texto = [p["numero_pdf"] for p in texto_rca["paginas"] if p.get("estado") == "escaneada"]
            if sin_texto:
                print(f"   páginas escaneadas sin texto, NO revisadas: {sin_texto}")
        return 0

    if opciones.localizador:
        ruta_secciones = Path(opciones.secciones) if opciones.secciones else ruta.parent.parent / "secciones" / ruta.name
        mapa = json.loads(ruta_secciones.read_text(encoding="utf-8"))
        paginas = mapa[f"paginas_para_{opciones.localizador}"]
    elif opciones.paginas:
        paginas = parsear_rango(opciones.paginas, n_paginas)
    else:
        parser.error("Indique --paginas, --localizador o --buscar")
    print(mostrar(texto_rca, paginas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
