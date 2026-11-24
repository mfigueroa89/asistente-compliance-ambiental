"""Revisa PDFs en busca de datos personales antes de publicarlos (regla 6 de CLAUDE.md).

Uso:
    python scripts/revisar_datos_personales.py RUTA_PDF [RUTA_PDF ...]

Busca, por código y sin IA, en el texto de cada página:
    - RUT (formato 12.345.678-9 o 12345678-9)
    - correos electrónicos, separando los institucionales (.gob.cl, .gov.cl, municipalidades) del resto
    - teléfonos chilenos
    - domicilios con calle o pasaje y número

No decide si algo es aceptable: lista los hallazgos con su página para que el abogado los revise.
Las páginas sin texto (escaneadas sin OCR) no se pueden revisar y se listan aparte.
Las páginas con OCR previo sí se revisan, pero el OCR puede ocultar o deformar datos.
"""

import argparse
import re
import sys
from pathlib import Path

import leer_pdf

PATRONES = {
    "rut": re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}\s?-\s?[\dkK]\b"),
    "correo": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "telefono": re.compile(r"(?:\+?56[\s-]?)?(?:\(?\d{1,2}\)?[\s-]?)?\b\d{4}[\s-]?\d{4}\b"),
    "domicilio": re.compile(
        r"\b(?:calle|pasaje|psje\.?|avenida|av\.)\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ ]{2,40}?\s+(?:N°|Nº|#|número)\s?\d+",
        re.IGNORECASE,
    ),
}
DOMINIOS_INSTITUCIONALES = re.compile(r"\.(?:gob|gov)\.cl$|\.gob$|municipalidad|\.mun", re.IGNORECASE)


def es_correo_institucional(correo):
    return bool(DOMINIOS_INSTITUCIONALES.search(correo.split("@", 1)[1]))


def revisar(ruta):
    """Devuelve un diccionario con los hallazgos por tipo, cada uno con página y texto encontrado."""
    datos = leer_pdf.leer_pdf(ruta)
    hallazgos = {"rut": [], "correo_institucional": [], "correo_otro": [], "telefono": [], "domicilio": []}
    for pagina in datos["paginas"]:
        texto = pagina["texto"]
        numero = pagina["numero_pdf"]
        for tipo, patron in PATRONES.items():
            for coincidencia in patron.finditer(texto):
                valor = coincidencia.group(0).strip()
                if tipo == "correo":
                    tipo_final = "correo_institucional" if es_correo_institucional(valor) else "correo_otro"
                elif tipo == "telefono" and re.fullmatch(r"(19|20)\d{2}[\s-]?\d{4}", valor):
                    continue  # pares de años, como "2009-2010", no son teléfonos
                else:
                    tipo_final = tipo
                hallazgos[tipo_final].append({"pagina": numero, "valor": valor})
    return {
        "archivo": datos["archivo"],
        "n_paginas": datos["n_paginas"],
        "paginas_no_revisables": datos["paginas_escaneadas"],
        "paginas_ocr_previo": datos["paginas_ocr_previo"],
        "hallazgos": hallazgos,
    }


def imprimir(resultado):
    print(f"== {resultado['archivo']} ({resultado['n_paginas']} páginas)")
    for tipo, lista in resultado["hallazgos"].items():
        if not lista:
            print(f"   {tipo}: ninguno")
            continue
        print(f"   {tipo}: {len(lista)}")
        for item in lista:
            print(f"      p{item['pagina']}: {item['valor']}")
    if resultado["paginas_no_revisables"]:
        print(f"   páginas sin texto, NO revisadas: {resultado['paginas_no_revisables']}")
    if resultado["paginas_ocr_previo"]:
        print(f"   páginas con OCR previo (revisión menos confiable): {len(resultado['paginas_ocr_previo'])}")


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Busca datos personales en PDFs antes de publicarlos.")
    parser.add_argument("pdfs", nargs="+", help="Ruta de uno o más PDFs")
    opciones = parser.parse_args(argumentos)
    errores = 0
    for ruta in opciones.pdfs:
        try:
            imprimir(revisar(Path(ruta)))
        except leer_pdf.ErrorLectura as error:
            errores += 1
            print(f"ERROR  {Path(ruta).name}: {error}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
