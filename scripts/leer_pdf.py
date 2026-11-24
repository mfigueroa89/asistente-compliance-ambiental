"""Lee una o más RCAs en PDF y guarda su texto, página por página, en JSON.

Uso:
    python scripts/leer_pdf.py RUTA_PDF [RUTA_PDF ...] [--salida salida] [--ocr tesseract]

Resultado por cada PDF:
    salida/texto/<archivo>.json            texto y datos de cada página
    salida/imagenes/<archivo>/pagina_N.png  imagen de las páginas que Claude debe leer visualmente
    salida/errores/<archivo>.json           solo si el PDF no se pudo leer

Clasificación de cada página (campo "estado"):
    "texto"       página con texto normal
    "escaneada"   casi sin texto pero con contenido visual (imagen o dibujo): hay que leerla como imagen
    "poco_texto"  menos de 50 caracteres útiles y sin contenido visual (por ejemplo, una portadilla)
    "en_blanco"   sin texto ni contenido visual

Además, una página "requiere lectura visual" si está escaneada, si su texto tiene
marcadores sin rellenar (por ejemplo "<NUM_RES>", que en las RCAs firmadas
electrónicamente esconden el número y la fecha) o si tiene un sello de firma visible.

Origen del texto de cada página (campo "origen_texto"):
    "digital"     texto escrito directamente en el PDF (confiable)
    "ocr_previo"  página escaneada a la que alguien ya le aplicó OCR: el texto es invisible y está
                  sobre una imagen de la página. Su calidad es variable (por ejemplo "Servido" en vez
                  de "Servicio"): las citas deben confirmarse contra la imagen.
    "sin_texto"   la página no tiene texto

El script no corrige el texto: los caracteres mal codificados ("�") se cuentan y se dejan tal cual.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pymupdf

# Los mensajes técnicos de MuPDF no se imprimen en pantalla: se guardan como avisos en el JSON.
pymupdf.TOOLS.mupdf_display_errors(False)

VERSION = "0.2.0"
MINIMO_CARACTERES_UTILES = 50
DPI_IMAGENES = 150
MARGEN_PIE_ENCABEZADO = 0.12  # 12 % superior e inferior de la página (en RCAs reales el pie llega al 90 %)
CARACTER_DUDOSO = "�"  # "�"

PATRON_MARCADOR = re.compile(r"<[A-Z][A-Z_]{2,}>")
PATRONES_NUMERO_IMPRESO = [
    re.compile(r"^p(?:á|a)g(?:ina|\.)?\s*(\d{1,4})(?:\s*(?:de|/)\s*\d{1,4})?$", re.IGNORECASE),
    re.compile(r"^(\d{1,4})\s*(?:de|/)\s*\d{1,4}$", re.IGNORECASE),
    re.compile(r"^-?\s*(\d{1,4})\s*-?$"),
]


class ErrorLectura(Exception):
    """Error al abrir o leer un PDF, con un mensaje claro en español."""


# ---------------------------------------------------------------- texto

def normalizar_bloque(texto):
    """Normaliza un bloque (párrafo) de texto extraído del PDF.

    - Une palabras cortadas con guion al final de línea ("obliga-\\nción" -> "obligación").
    - Junta las líneas del párrafo con un espacio.
    - Colapsa espacios repetidos.
    """
    texto = re.sub(r"(\w)-[ \t]*\n[ \t]*([a-záéíóúüñ])", r"\1\2", texto)
    texto = re.sub(r"\s*\n\s*", " ", texto)
    texto = re.sub(r"[ \t ]+", " ", texto)
    return texto.strip()


def extraer_texto(pagina):
    """Devuelve el texto de la página normalizado, con un párrafo por bloque."""
    bloques = pagina.get_text("blocks", sort=True)
    parrafos = []
    for bloque in bloques:
        if bloque[6] != 0:  # 0 = bloque de texto, 1 = imagen
            continue
        parrafo = normalizar_bloque(bloque[4])
        if parrafo:
            parrafos.append(parrafo)
    return "\n\n".join(parrafos)


def contar_caracteres_utiles(texto):
    return len(re.sub(r"\s", "", texto))


def detectar_numero_impreso(pagina):
    """Busca el número de página impreso en el encabezado o pie. Si no es claro, devuelve None."""
    alto = pagina.rect.height
    limite_superior = alto * MARGEN_PIE_ENCABEZADO
    limite_inferior = alto * (1 - MARGEN_PIE_ENCABEZADO)
    candidatos = []
    for bloque in pagina.get_text("blocks"):
        if bloque[6] != 0:
            continue
        y0, y1 = bloque[1], bloque[3]
        if y1 <= limite_superior or y0 >= limite_inferior:
            for linea in bloque[4].splitlines():
                linea = linea.strip()
                for patron in PATRONES_NUMERO_IMPRESO:
                    coincidencia = patron.match(linea)
                    if coincidencia:
                        candidatos.append(int(coincidencia.group(1)))
                        break
    # Solo se acepta si hay un único número distinto: si hay varios, no se adivina.
    distintos = set(candidatos)
    return distintos.pop() if len(distintos) == 1 else None


def filtrar_numeros_impresos(paginas):
    """Conserva solo los números impresos que siguen una secuencia coherente.

    Un número suelto en el borde de la página puede ser parte de una tabla y no la numeración.
    Por eso se calcula la diferencia (número impreso - número del PDF) de cada página detectada:
    si una misma diferencia explica al menos el 60 % de las detecciones (y al menos 3 páginas,
    o todas si el documento es corto), se conservan las que la siguen y el resto queda en None.
    Si no hay un patrón claro, todas quedan en None: no se adivina.
    """
    detectadas = [p for p in paginas if p["numero_impreso"] is not None]
    if not detectadas:
        return
    conteo = {}
    for p in detectadas:
        diferencia = p["numero_impreso"] - p["numero_pdf"]
        conteo[diferencia] = conteo.get(diferencia, 0) + 1
    diferencia, veces = max(conteo.items(), key=lambda par: par[1])
    minimo = min(3, len(paginas))
    patron_claro = veces >= minimo and veces / len(detectadas) >= 0.6
    for p in detectadas:
        if not patron_claro or p["numero_impreso"] - p["numero_pdf"] != diferencia:
            p["numero_impreso"] = None


# ------------------------------------------------------- contenido visual

def tiene_contenido_visual(pagina):
    """True si la página tiene imágenes o dibujos (lo que tendría una página escaneada o un plano)."""
    if pagina.get_image_info():
        return True
    return len(pagina.get_drawings()) > 0


TEXTO_INVISIBLE = 3  # modo de dibujo de texto "invisible" del estándar PDF (típico del OCR)
COBERTURA_IMAGEN_OCR = 0.8  # la imagen de fondo debe cubrir al menos el 80 % de la página
PROPORCION_INVISIBLE_OCR = 0.9  # al menos el 90 % de los caracteres deben ser invisibles


def detectar_origen_texto(pagina):
    """Indica si el texto de la página es "digital", "ocr_previo" o "sin_texto".

    Una página escaneada con OCR previo tiene una imagen que cubre casi toda la página
    y, encima, el texto reconocido en modo invisible.
    """
    visibles = invisibles = 0
    for tramo in pagina.get_texttrace():
        cantidad = len(tramo["chars"])
        if tramo["type"] == TEXTO_INVISIBLE:
            invisibles += cantidad
        else:
            visibles += cantidad
    total = visibles + invisibles
    if total == 0:
        return "sin_texto"
    area = pagina.rect.get_area() or 1
    cobertura = sum(pymupdf.Rect(imagen["bbox"]).intersect(pagina.rect).get_area() for imagen in pagina.get_image_info()) / area
    if invisibles / total >= PROPORCION_INVISIBLE_OCR and cobertura >= COBERTURA_IMAGEN_OCR:
        return "ocr_previo"
    return "digital"


def tiene_firma_visible(pagina):
    """True si la página tiene un campo de firma electrónica con tamaño visible."""
    for campo in pagina.widgets() or []:
        if campo.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and not campo.rect.is_empty:
            return True
    return False


def clasificar_pagina(n_utiles, contenido_visual):
    if n_utiles >= MINIMO_CARACTERES_UTILES:
        return "texto"
    if contenido_visual:
        return "escaneada"
    if n_utiles == 0:
        return "en_blanco"
    return "poco_texto"


# ------------------------------------------------------------- lectura

def calcular_sha256(ruta):
    huella = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for trozo in iter(lambda: archivo.read(1 << 20), b""):
            huella.update(trozo)
    return huella.hexdigest()


def abrir_pdf(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorLectura(f"No existe el archivo: {ruta}")
    if ruta.stat().st_size == 0:
        raise ErrorLectura(f"El archivo está vacío (0 bytes): {ruta.name}")
    try:
        documento = pymupdf.open(ruta)
    except Exception as error:
        raise ErrorLectura(f"No se pudo abrir {ruta.name}: el PDF está dañado o no es un PDF ({error}).")
    if not documento.is_pdf:
        documento.close()
        raise ErrorLectura(f"{ruta.name} no es un PDF.")
    if documento.needs_pass:
        documento.close()
        raise ErrorLectura(f"{ruta.name} está protegido con contraseña y no se puede leer.")
    if documento.page_count == 0:
        documento.close()
        raise ErrorLectura(f"{ruta.name} no tiene páginas.")
    return documento


def aplicar_ocr_tesseract(pagina):
    """Intenta leer una página escaneada con Tesseract (si está instalado). Devuelve (texto, aviso)."""
    try:
        textpage = pagina.get_textpage_ocr(language="spa", dpi=300, full=True)
        return normalizar_bloque(pagina.get_text(textpage=textpage)), None
    except Exception as error:
        return None, f"Tesseract no pudo leer la página {pagina.number + 1}: {error}"


def leer_pdf(ruta, carpeta_imagenes=None, ocr=None):
    """Lee un PDF y devuelve un diccionario con sus metadatos y el detalle de cada página.

    Si se indica carpeta_imagenes, guarda ahí la imagen de las páginas que requieren lectura visual.
    """
    ruta = Path(ruta)
    pymupdf.TOOLS.reset_mupdf_warnings()
    documento = abrir_pdf(ruta)
    avisos = []
    paginas = []
    try:
        for indice in range(documento.page_count):
            pagina = documento[indice]
            numero = indice + 1
            try:
                texto = extraer_texto(pagina)
            except Exception as error:
                texto = ""
                avisos.append(f"No se pudo extraer texto de la página {numero}: {error}")
            n_utiles = contar_caracteres_utiles(texto)
            visual = tiene_contenido_visual(pagina) if n_utiles < MINIMO_CARACTERES_UTILES else None
            estado = clasificar_pagina(n_utiles, visual)
            marcadores = sorted(set(PATRON_MARCADOR.findall(texto)))
            firma = tiene_firma_visible(pagina)

            motivos = []
            if estado == "escaneada":
                motivos.append("página escaneada")
            if marcadores:
                motivos.append("marcadores sin rellenar en el texto: " + ", ".join(marcadores))
            if firma:
                motivos.append("sello de firma electrónica visible")

            datos = {
                "numero_pdf": numero,
                "numero_impreso": detectar_numero_impreso(pagina),
                "texto": texto,
                "n_caracteres": len(texto),
                "n_caracteres_utiles": n_utiles,
                "estado": estado,
                "escaneada": estado == "escaneada",
                "origen_texto": detectar_origen_texto(pagina),
                "caracteres_dudosos": texto.count(CARACTER_DUDOSO),
                "marcadores_sin_rellenar": marcadores,
                "requiere_lectura_visual": bool(motivos),
                "motivos_lectura_visual": motivos,
                "imagen": None,
            }

            if motivos and carpeta_imagenes is not None:
                carpeta = Path(carpeta_imagenes)
                carpeta.mkdir(parents=True, exist_ok=True)
                destino = carpeta / f"pagina_{numero}.png"
                pagina.get_pixmap(dpi=DPI_IMAGENES).save(destino)
                datos["imagen"] = destino.as_posix()

            if estado == "escaneada" and ocr == "tesseract":
                texto_ocr, aviso = aplicar_ocr_tesseract(pagina)
                datos["texto_ocr"] = texto_ocr
                if aviso:
                    avisos.append(aviso)

            paginas.append(datos)
    finally:
        documento.close()

    filtrar_numeros_impresos(paginas)

    advertencias_mupdf = sorted(set(filter(None, pymupdf.TOOLS.mupdf_warnings().splitlines())))
    avisos.extend(f"MuPDF: {texto}" for texto in advertencias_mupdf)

    def numeros(condicion):
        return [p["numero_pdf"] for p in paginas if condicion(p)]

    paginas_ocr = numeros(lambda p: p["origen_texto"] == "ocr_previo")
    if paginas_ocr:
        avisos.insert(
            0,
            f"{len(paginas_ocr)} de {len(paginas)} páginas tienen texto de OCR previo (calidad variable): "
            "las citas de esas páginas deben confirmarse contra la imagen.",
        )

    return {
        "archivo": ruta.name,
        "sha256": calcular_sha256(ruta),
        "n_paginas": len(paginas),
        "n_paginas_escaneadas": len(numeros(lambda p: p["escaneada"])),
        "paginas_escaneadas": numeros(lambda p: p["escaneada"]),
        "paginas_en_blanco": numeros(lambda p: p["estado"] == "en_blanco"),
        "paginas_poco_texto": numeros(lambda p: p["estado"] == "poco_texto"),
        "paginas_lectura_visual": numeros(lambda p: p["requiere_lectura_visual"]),
        "paginas_ocr_previo": paginas_ocr,
        "n_caracteres_dudosos": sum(p["caracteres_dudosos"] for p in paginas),
        "fecha_procesamiento": datetime.now().isoformat(timespec="seconds"),
        "version_script": VERSION,
        "ocr": ocr,
        "avisos": avisos,
        "paginas": paginas,
    }


# ------------------------------------------------------------ guardado

def guardar_json(datos, destino):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    return destino


def procesar(ruta, carpeta_salida, ocr=None):
    """Lee un PDF y guarda su JSON. Si falla, guarda el error y lo devuelve como texto."""
    ruta = Path(ruta)
    salida = Path(carpeta_salida)
    nombre = ruta.stem
    try:
        datos = leer_pdf(ruta, carpeta_imagenes=salida / "imagenes" / nombre, ocr=ocr)
    except ErrorLectura as error:
        guardar_json(
            {"archivo": ruta.name, "error": str(error), "fecha": datetime.now().isoformat(timespec="seconds")},
            salida / "errores" / f"{nombre}.json",
        )
        return None, str(error)
    destino = guardar_json(datos, salida / "texto" / f"{nombre}.json")
    return destino, datos


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Extrae el texto de RCAs en PDF, página por página.")
    parser.add_argument("pdfs", nargs="+", help="Ruta de uno o más PDFs")
    parser.add_argument("--salida", default="salida", help="Carpeta de salida (por defecto: salida)")
    parser.add_argument("--ocr", choices=["tesseract"], help="Usar Tesseract en páginas escaneadas (debe estar instalado)")
    opciones = parser.parse_args(argumentos)

    fallidos = 0
    for ruta in opciones.pdfs:
        destino, resultado = procesar(ruta, opciones.salida, opciones.ocr)
        if destino is None:
            fallidos += 1
            print(f"ERROR  {Path(ruta).name}: {resultado}", file=sys.stderr)
            continue
        print(
            f"OK     {resultado['archivo']}: {resultado['n_paginas']} páginas, "
            f"{resultado['n_paginas_escaneadas']} escaneadas, "
            f"{len(resultado['paginas_en_blanco'])} en blanco, "
            f"{len(resultado['paginas_lectura_visual'])} para lectura visual, "
            f"{len(resultado['paginas_ocr_previo'])} con OCR previo, "
            f"{resultado['n_caracteres_dudosos']} caracteres dudosos -> {destino.as_posix()}"
        )
        for aviso in resultado["avisos"]:
            print(f"       aviso: {aviso}")
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
