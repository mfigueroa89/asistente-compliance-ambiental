"""Búsqueda exacta de temas y términos (sin IA) en las obligaciones y en el texto completo de las RCAs.

Este script NO modifica las obligaciones ni las fichas: solo lee y escribe informes.

Usos:
    python scripts/buscar_palabras.py consultar "humedales" [--archivo X.pdf ...] [--manifiesto manifiesto.csv]
        Separa el resultado en tres categorías:
          1. coincidencia literal: el término (o un sinónimo del tema) está en una cita de la obligación,
             es decir, en texto del PDF. La descripción no cuenta, porque la redactó el asistente.
          2. relación temática (revisar): el tema figura en temas_relacionados de la obligación
             (interpretación del asistente, con justificación) y no hay coincidencia literal.
          3. mención sin obligación: el término aparece en el texto de la RCA fuera de toda cita de obligación.
        Todo resultado informa su alcance: RCAs y obligaciones buscadas y páginas que no se pudieron revisar.
        Opciones:
          --uf "nombre"            solo las RCAs de esa unidad fiscalizable del manifiesto (sin distinguir
                                   mayúsculas ni tildes; basta una parte del nombre si no es ambigua).
          --relaciones X.json      solo para términos libres (fuera de config/temas.yaml): relaciones temáticas
                                   propuestas por Claude para esta consulta. Cada una se comprueba por código
                                   (las palabras_pdf deben estar en el texto de su página); las que no pasan se
                                   rechazan con su motivo. Se guardan solo en el resultado de la consulta.
        Resultado: salida/consultas/consulta_<termino>_<AAAAMMDD-HHMMSS>.json y .csv (el CSV se abre en Excel).
        Cada consulta queda guardada aparte. Este script no toca el Excel: la consulta entra en la hoja Consulta
        solo si el usuario lo pide (exportar_excel.py --agregar-consulta <JSON de la consulta>).
        Manifiesto: si no se indica otro, se usa manifiesto.csv; si no existe, ejemplos/manifiesto_ejemplo.csv
        (y la consulta lo avisa). Si no existe ninguno, o si no existe el manifiesto indicado, no se guarda nada.

    python scripts/buscar_palabras.py obligacion ARQ-024 [--manifiesto manifiesto.csv]
        Muestra una obligación completa por su ID visible (prefijo de la RCA, columna prefijo_id del manifiesto)
        o por su ID interno (OBL-024, en todas las RCAs donde exista). Solo lee.

    python scripts/buscar_palabras.py revisar [--archivo X.pdf ...]
        Por RCA: temas literales de cada obligación y todas las apariciones de los temas en el texto.
        Resultado: salida/temas/<archivo>.json

    python scripts/buscar_palabras.py descripcion-sin-cita [--archivo X.pdf ...]
        Lista las obligaciones cuya descripción contiene un término de algún tema que no está en sus citas.
        Resultado: salida/verificacion/terminos_descripcion_sin_cita.csv

Lee: salida/texto/, salida/obligaciones/, salida/fichas/ (N° de resolución) y el manifiesto (UF y proyecto).
Reglas de búsqueda: sin distinguir mayúsculas ni tildes, plural simple, solo palabras completas.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

import yaml

import ids_visibles
import verificar_citas

RAIZ = Path(__file__).resolve().parent.parent
TEMAS_POR_DEFECTO = RAIZ / "config" / "temas.yaml"
SIN_UF = "SIN UF ASIGNADA"
MANIFIESTO_POR_DEFECTO = "manifiesto.csv"
# Respaldo cuando no existe manifiesto.csv: primero el de la carpeta de trabajo, después el del asistente.
MANIFIESTOS_EJEMPLO = [Path("ejemplos") / "manifiesto_ejemplo.csv", RAIZ / "ejemplos" / "manifiesto_ejemplo.csv"]
CONTEXTO = 200
UMBRAL_CITA = 0.85  # para ubicar en la página una cita con pequeñas diferencias de OCR
NO_APLICA = "—"
AVISO = "Herramienta de apoyo. Requiere revisión de un abogado."

LITERAL = "coincidencia literal"
RELACION = "relación temática (revisar)"
MENCION = "mención sin obligación"

PALABRAS_VACIAS = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "a", "al", "con", "por", "para"}
GUIONES = "‐‑‒–—―"

COLUMNAS_CONSULTA = [
    "categoria", "unidad_fiscalizable", "proyecto", "archivo", "numero_resolucion", "id_visible", "id_obligacion", "tipo",
    "descripcion", "plazo_o_frecuencia", "responsable", "pagina_pdf", "pagina_impresa", "cita_textual",
    "termino_encontrado", "donde_aparece", "tema", "justificacion", "duplicado_de", "contexto",
    "seccion_localizador", "obligaciones_en_la_pagina",
]
COLUMNAS_DESCRIPCION = [
    "archivo", "id_obligacion", "pagina_pdf", "tema", "termino", "encontrado_en_descripcion",
    "paginas_de_las_citas_donde_aparece", "descripcion", "cita_textual", "citas_adicionales",
]


class ErrorTemas(Exception):
    """config/temas.yaml no existe o tiene un formato que no se puede usar."""


# ------------------------------------------------------------------ texto y términos

def normalizar_con_mapa(texto):
    """Quita tildes y mayúsculas y colapsa espacios. Devuelve (texto_normal, mapa), donde mapa[i]
    es la posición en el texto original del carácter i del texto normal (para recuperar el contexto)."""
    salida, mapa, espacio_previo = [], [], True
    for posicion, caracter in enumerate(texto or ""):
        if caracter.isspace():
            if not espacio_previo:
                salida.append(" ")
                mapa.append(posicion)
            espacio_previo = True
            continue
        if caracter in GUIONES:
            caracter = "-"
        base = "".join(c for c in unicodedata.normalize("NFKD", caracter) if not unicodedata.combining(c)).lower()
        for c in base:
            salida.append(c)
            mapa.append(posicion)
        if base:
            espacio_previo = False
    while salida and salida[-1] == " ":
        salida.pop()
        mapa.pop()
    return "".join(salida), mapa


def normalizar(texto):
    return normalizar_con_mapa(texto)[0]


def variante_de_palabra(palabra):
    """Expresión que acepta la palabra en singular o plural simple (humedal/humedales, vega/vegas)."""
    if palabra in PALABRAS_VACIAS or not palabra[-1].isalpha():
        return re.escape(palabra)
    if palabra.endswith("es") and len(palabra) > 5:          # humedales -> humedal(es)
        return re.escape(palabra[:-2]) + "(?:es)?"
    if palabra.endswith("s") and len(palabra) > 4:            # vegas -> vega(s)
        return re.escape(palabra[:-1]) + "s?"
    if palabra.endswith("z"):                                  # luz -> luz / luces
        return re.escape(palabra[:-1]) + "(?:z|ces)"
    if palabra[-1] in "aeiou":                                 # vega -> vega(s)
        return re.escape(palabra) + "s?"
    return re.escape(palabra) + "(?:es)?"                      # humedal -> humedal(es)


def patron_de(termino):
    """Expresión regular de un término sobre texto normalizado: palabras completas, plural simple,
    y cualquier cantidad de espacios o un guion entre palabras (cortes de línea del PDF)."""
    palabras = normalizar(termino).replace("-", " ").split()
    if not palabras:
        raise ErrorTemas(f"Término vacío: «{termino}».")
    cuerpo = r"[\s\-]+".join(variante_de_palabra(p) for p in palabras)
    return re.compile(r"(?<![a-z0-9])" + cuerpo + r"(?![a-z0-9])")


def buscar(texto, termino):
    """Apariciones de un término en un texto: lista de (inicio, fin, texto_original_encontrado)."""
    normal, mapa = normalizar_con_mapa(texto)
    resultado = []
    for m in patron_de(termino).finditer(normal):
        inicio, fin = mapa[m.start()], mapa[m.end() - 1] + 1
        resultado.append((inicio, fin, texto[inicio:fin]))
    return resultado


def contexto_de(texto, inicio, fin, largo=CONTEXTO):
    antes = texto[max(0, inicio - largo):inicio]
    despues = texto[fin:fin + largo]
    return re.sub(r"\s+", " ", f"{'…' if inicio > largo else ''}{antes}[{texto[inicio:fin]}]{despues}{'…' if fin + largo < len(texto) else ''}").strip()


# ------------------------------------------------------------------ temas.yaml

def cargar_temas(ruta=TEMAS_POR_DEFECTO):
    """Lee config/temas.yaml. Devuelve {tema: [términos]}. Lanza ErrorTemas con un mensaje claro."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorTemas(f"No existe el archivo de temas: {ruta}. Debe estar en config/temas.yaml.")
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        linea = getattr(getattr(error, "problem_mark", None), "line", None)
        donde = f" (cerca de la línea {linea + 1})" if linea is not None else ""
        raise ErrorTemas(f"{ruta.name} tiene un error de formato{donde}. Revise que cada tema termine en dos puntos "
                         f"y que cada término vaya en su línea, con «  - » delante.") from error
    except UnicodeDecodeError as error:
        raise ErrorTemas(f"{ruta.name} no está guardado en UTF-8. Vuelva a guardarlo con codificación UTF-8.") from error
    if not isinstance(datos, dict) or not datos:
        raise ErrorTemas(f"{ruta.name} no tiene temas. Formato esperado:\nhumedales:\n  - humedal\n  - bofedal")
    temas, errores = {}, []
    for tema, terminos in datos.items():
        if not isinstance(tema, str) or not tema.strip():
            errores.append(f"Hay un tema sin nombre ({tema!r}).")
            continue
        if not isinstance(terminos, list) or not terminos:
            errores.append(f"El tema «{tema}» no tiene una lista de términos.")
            continue
        limpios = []
        for termino in terminos:
            if not isinstance(termino, (str, int)) or not str(termino).strip():
                errores.append(f"El tema «{tema}» tiene un término vacío o que no es texto ({termino!r}).")
            else:
                limpios.append(str(termino).strip())
        temas[tema.strip()] = limpios
    if errores:
        raise ErrorTemas(f"{ruta.name} tiene errores:\n- " + "\n- ".join(errores))
    return temas


def resolver_consulta(consulta, temas):
    """Decide si la consulta es un tema (con todos sus sinónimos) o un término suelto.
    Devuelve {"tema": nombre o None, "terminos": [...], "aviso": texto o None,
    "tema_del_termino": el tema al que pertenece un término suelto, o None}."""
    normal = normalizar(consulta).replace("_", " ")
    for tema, terminos in temas.items():
        if patron_de(tema.replace("_", " ")).fullmatch(normal) or patron_de(normal).fullmatch(normalizar(tema).replace("_", " ")):
            return {"tema": tema, "terminos": terminos, "aviso": None, "tema_del_termino": None}
    aviso, del_tema = None, None
    for tema, terminos in temas.items():
        if any(patron_de(t).fullmatch(normal) for t in terminos):
            aviso = (f"«{consulta}» es uno de los términos del tema «{tema}». Se buscó solo ese término; "
                     f"para incluir todos sus sinónimos, consulte «{tema}».")
            del_tema = tema
            break
    return {"tema": None, "terminos": [consulta.strip()], "aviso": aviso, "tema_del_termino": del_tema}


# ------------------------------------------------------------------ obligaciones

def citas_de(obligacion):
    """Citas del PDF de una obligación: [(donde, pagina_pdf, cita)], la principal primero."""
    citas = []
    if obligacion.get("cita_textual"):
        citas.append((f"cita principal (p. {obligacion.get('pagina_pdf')})", obligacion.get("pagina_pdf"), obligacion["cita_textual"]))
    for numero, adicional in enumerate(obligacion.get("citas_adicionales") or [], start=1):
        if adicional.get("cita_textual"):
            citas.append((f"cita adicional {numero} (p. {adicional.get('pagina_pdf')})", adicional.get("pagina_pdf"), adicional["cita_textual"]))
    return citas


def terminos_en_citas(obligacion, terminos):
    """[(termino, texto_encontrado, donde)] de los términos que aparecen en las citas de la obligación."""
    hallados = []
    for donde, _, cita in citas_de(obligacion):
        for termino in terminos:
            for _, _, encontrado in buscar(cita, termino):
                hallados.append((termino, encontrado, donde))
    return hallados


def temas_literales(obligacion, temas):
    """{tema: [(termino, encontrado, donde)]} de los temas cuyos términos están en las citas."""
    resultado = {}
    for tema, terminos in temas.items():
        hallados = terminos_en_citas(obligacion, terminos)
        if hallados:
            resultado[tema] = hallados
    return resultado


def terminos_en_descripcion_sin_cita(obligacion, temas):
    """[(tema, termino, encontrado)] de términos que están en la descripción y no en ninguna cita."""
    resultado = []
    for tema, terminos in temas.items():
        for termino in terminos:
            en_descripcion = buscar(obligacion.get("descripcion", ""), termino)
            if en_descripcion and not terminos_en_citas(obligacion, [termino]):
                resultado.append((tema, termino, ", ".join(sorted({e for _, _, e in en_descripcion}))))
    return resultado


def relacion_tematica(obligacion, tema):
    """El elemento de temas_relacionados de ese tema, o None."""
    for relacion in obligacion.get("temas_relacionados") or []:
        if isinstance(relacion, dict) and relacion.get("tema") == tema:
            return relacion
    return None


def grupos_de_duplicados(obligaciones):
    """{ID: ID representante} uniendo las cadenas de posible_duplicado (igual que la hoja Obligaciones)."""
    padre = {o["id_obligacion"]: o["id_obligacion"] for o in obligaciones}

    def raiz(ident):
        while padre[ident] != ident:
            padre[ident] = padre[padre[ident]]
            ident = padre[ident]
        return ident

    for obligacion in obligaciones:
        for otro in obligacion.get("posible_duplicado") or []:
            if otro in padre:
                a, b = sorted((raiz(obligacion["id_obligacion"]), raiz(otro)))
                padre[b] = a
    return {ident: raiz(ident) for ident in padre}


# ------------------------------------------------------------------ ubicar citas en la página

def tramos_de_cita(cita, texto_pagina):
    """Tramos (inicio, fin) del texto de la página que ocupa la cita. Primero exacto (sin tildes,
    mayúsculas ni espacios); si no, el tramo más parecido sobre UMBRAL_CITA (diferencias de OCR)."""
    pagina_normal, mapa = normalizar_con_mapa(texto_pagina)
    cita_normal = normalizar(cita)
    if not cita_normal or not pagina_normal:
        return []
    tramos, desde = [], 0
    while True:
        i = pagina_normal.find(cita_normal, desde)
        if i < 0:
            break
        tramos.append((mapa[i], mapa[i + len(cita_normal) - 1] + 1))
        desde = i + 1
    if tramos:
        return tramos
    comparador = SequenceMatcher(None, cita_normal, pagina_normal, autojunk=False)
    mejor, mejor_inicio = 0.0, None
    for bloque in comparador.get_matching_blocks():
        if bloque.size < 4:
            continue
        inicio = max(0, bloque.b - bloque.a)
        ventana = pagina_normal[inicio:inicio + len(cita_normal)]
        similitud = SequenceMatcher(None, cita_normal, ventana, autojunk=False).ratio()
        if similitud > mejor:
            mejor, mejor_inicio = similitud, inicio
    if mejor >= UMBRAL_CITA and mejor_inicio is not None:
        fin = min(len(mapa) - 1, mejor_inicio + len(cita_normal) - 1)
        return [(mapa[mejor_inicio], mapa[fin] + 1)]
    return []


def mapa_de_citas(obligaciones, paginas):
    """{pagina_pdf: [(inicio, fin, id_obligacion)]} con los tramos que ocupan las citas de las obligaciones."""
    textos = {p["numero_pdf"]: p.get("texto") or "" for p in paginas}
    resultado = {}
    for obligacion in obligaciones:
        for _, pagina, cita in citas_de(obligacion):
            for inicio, fin in tramos_de_cita(cita, textos.get(pagina, "")):
                resultado.setdefault(pagina, []).append((inicio, fin, obligacion["id_obligacion"]))
    return resultado


# ------------------------------------------------------------------ texto completo

def pagina_sin_texto(pagina):
    """Página cuyo texto no permite buscar: escaneada (sin texto digital ni OCR previo)."""
    if pagina.get("origen_texto") == "ocr_previo":
        return False
    return pagina.get("estado") == "escaneada" or pagina.get("origen_texto") == "sin_texto"


def buscar_en_rca(texto, obligaciones, terminos_por_tema):
    """Todas las apariciones en el texto completo. terminos_por_tema: {tema o None: [términos]}.
    Cada hallazgo indica qué obligaciones lo citan (recogido_en) y cuáles citan esa página."""
    citas = mapa_de_citas(obligaciones, texto["paginas"])
    por_pagina = {}
    for obligacion in obligaciones:
        for _, pagina, _ in citas_de(obligacion):
            por_pagina.setdefault(pagina, [])
            if obligacion["id_obligacion"] not in por_pagina[pagina]:
                por_pagina[pagina].append(obligacion["id_obligacion"])
    hallazgos = []
    for pagina in texto["paginas"]:
        contenido = pagina.get("texto") or ""
        vistos = set()
        for tema, terminos in terminos_por_tema.items():
            for termino in terminos:
                for inicio, fin, encontrado in buscar(contenido, termino):
                    if (inicio, fin, tema) in vistos:
                        continue
                    vistos.add((inicio, fin, tema))
                    recogido = sorted({ident for a, b, ident in citas.get(pagina["numero_pdf"], []) if a <= inicio and fin <= b})
                    hallazgos.append({
                        "termino": termino, "encontrado": encontrado, "tema": tema,
                        "pagina_pdf": pagina["numero_pdf"], "pagina_impresa": pagina.get("numero_impreso"),
                        "origen_texto": pagina.get("origen_texto"),
                        "contexto": contexto_de(contenido, inicio, fin),
                        "recogido_en": recogido,
                        "obligaciones_en_la_pagina": por_pagina.get(pagina["numero_pdf"], []),
                    })
    return hallazgos


def resumen_por_termino(hallazgos):
    resumen = {}
    for h in hallazgos:
        r = resumen.setdefault(h["termino"], {"tema": h["tema"], "apariciones": 0, "paginas": []})
        r["apariciones"] += 1
        if h["pagina_pdf"] not in r["paginas"]:
            r["paginas"].append(h["pagina_pdf"])
    return resumen


# ------------------------------------------------------------------ carga de una RCA

def cargar_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def cargar_rca(archivo, carpeta_salida):
    """Reúne texto, obligaciones y ficha de una RCA. Devuelve un diccionario o lanza FileNotFoundError."""
    base = Path(archivo).stem
    salida = Path(carpeta_salida)
    ruta_texto = salida / "texto" / f"{base}.json"
    ruta_obligaciones = salida / "obligaciones" / f"{base}.json"
    if not ruta_texto.exists():
        raise FileNotFoundError(f"Falta el texto de {archivo} ({ruta_texto.as_posix()}). Ejecute antes leer_pdf.py.")
    if not ruta_obligaciones.exists():
        raise FileNotFoundError(f"Faltan las obligaciones de {archivo} ({ruta_obligaciones.as_posix()}).")
    texto = cargar_json(ruta_texto)
    obligaciones = cargar_json(ruta_obligaciones)
    ruta_ficha = salida / "fichas" / f"{base}.json"
    ficha = cargar_json(ruta_ficha) if ruta_ficha.exists() else None
    avisos = []
    if texto.get("sha256") and obligaciones.get("sha256") and texto["sha256"] != obligaciones["sha256"]:
        avisos.append(f"{archivo}: las obligaciones no corresponden al mismo PDF que el texto (SHA-256 distinto).")
    numero = "No consta"
    if ficha:
        dato = (ficha.get("campos") or {}).get("numero_resolucion") or {}
        numero = dato.get("valor") or "No consta"
    return {"archivo": texto.get("archivo", f"{base}.pdf"), "texto": texto, "datos_obligaciones": obligaciones,
            "obligaciones": obligaciones.get("obligaciones", []), "numero_resolucion": numero, "avisos": avisos}


def alcance_de_rca(rca, tema=None):
    """Qué se buscó en una RCA y qué no se pudo revisar."""
    paginas = rca["texto"]["paginas"]
    control = rca["datos_obligaciones"].get("control") or {}
    revisadas = rca["datos_obligaciones"].get("temas_relacionados_revisados") or {}
    sin_texto = [p["numero_pdf"] for p in paginas if pagina_sin_texto(p)]
    en_imagen = sorted(set(control.get("paginas_revisadas_en_imagen") or []) & set(sin_texto))
    alcance = {
        "archivo": rca["archivo"],
        "obligaciones_buscadas": len(rca["obligaciones"]),
        "paginas_totales": len(paginas),
        "paginas_sin_texto": sin_texto,
        "paginas_sin_texto_con_obligaciones_leidas_en_imagen": en_imagen,
        "paginas_no_leidas": [{"pagina": p.get("pagina"), "seccion": p.get("seccion"), "motivo": p.get("motivo")}
                              for p in control.get("paginas_no_leidas") or []],
        "paginas_ocr_previo": [p["numero_pdf"] for p in paginas if p.get("origen_texto") == "ocr_previo"],
    }
    if tema is not None:
        alcance["relacion_tematica_revisada"] = tema in (revisadas.get("temas") or [])
    return alcance


def texto_de_alcance(alcances, tema, uf=None, propuestas=None):
    """Líneas en español que explican el alcance de una consulta.
    propuestas: None si no se entregaron relaciones para un término libre; si no, {"aceptadas": n, "rechazadas": n}."""
    total = sum(a["obligaciones_buscadas"] for a in alcances)
    lineas = [f"Alcance: {len(alcances)} RCA(s) y {total} obligaciones buscadas"
              + (f", solo de la unidad fiscalizable «{uf}»." if uf else ".")]
    for a in alcances:
        partes = [f"{a['archivo']}: {a['obligaciones_buscadas']} obligaciones, {a['paginas_totales']} páginas"]
        if a["paginas_sin_texto"]:
            detalle = f"páginas sin texto, no revisadas en el texto completo: {lista_paginas(a['paginas_sin_texto'])}"
            if a["paginas_sin_texto_con_obligaciones_leidas_en_imagen"]:
                detalle += (f" (en las pp. {lista_paginas(a['paginas_sin_texto_con_obligaciones_leidas_en_imagen'])} "
                            f"sí se buscó en las citas de sus obligaciones, transcritas de la imagen)")
            partes.append(detalle)
        for p in a["paginas_no_leidas"]:
            partes.append(f"p. {p['pagina']} no leída ({p['seccion']}): {p['motivo']}")
        if a["paginas_ocr_previo"]:
            partes.append(f"{len(a['paginas_ocr_previo'])} páginas con texto de OCR previo: un término mal leído por el OCR "
                          f"no se encuentra")
        if tema is not None:
            partes.append("relación temática ya revisada para este tema" if a.get("relacion_tematica_revisada")
                          else "relación temática AÚN NO REVISADA en esta RCA (la categoría 2 puede estar incompleta)")
        elif propuestas is None:
            partes.append("término fuera de config/temas.yaml: no hay relación temática anotada")
        else:
            partes.append("término fuera de config/temas.yaml: la relación temática es la propuesta por Claude en esta "
                          "consulta, comprobada por código y a revisar")
        lineas.append("- " + "; ".join(partes) + ".")
    if propuestas is not None:
        lineas.append(f"Relaciones propuestas para el término libre: {propuestas['aceptadas']} aceptadas (comprobadas por "
                      f"código, a revisar) y {propuestas['rechazadas']} rechazadas.")
    return lineas


def lista_paginas(paginas):
    return ", ".join(str(p) for p in paginas)


# ------------------------------------------------------------------ manifiesto

def unidades_por_archivo(ruta_manifiesto):
    """{archivo: [(unidad_fiscalizable, proyecto)]} desde el manifiesto, y avisos."""
    if ruta_manifiesto is None or not Path(ruta_manifiesto).exists():
        return {}, [f"No se encontró el manifiesto ({ruta_manifiesto}); las RCAs quedan como \"{SIN_UF}\"."]
    import leer_manifiesto
    manifiesto = leer_manifiesto.leer_manifiesto(ruta_manifiesto)
    unidades = {}
    for fila in manifiesto["filas"]:
        unidades.setdefault(fila["archivo"], []).append((fila["unidad_fiscalizable"] or SIN_UF, fila["proyecto"] or "No consta"))
    return unidades, []


class ErrorConsulta(Exception):
    """La consulta no se puede hacer tal como se pidió (sin manifiesto, UF inexistente o ambigua, relaciones mal formadas)."""


def resolver_manifiesto(ruta, ejemplos=None):
    """Manifiesto que usa la consulta: (ruta, avisos).
    Si no existe manifiesto.csv (el de por defecto), usa el manifiesto de ejemplo y lo avisa.
    Si no hay ninguno, o si no existe un manifiesto indicado expresamente, lanza ErrorConsulta:
    una consulta sin manifiesto dejaría todas las RCAs como "SIN UF ASIGNADA"."""
    ruta = Path(ruta or MANIFIESTO_POR_DEFECTO)
    if ruta.exists():
        return ruta, []
    if ruta != Path(MANIFIESTO_POR_DEFECTO):
        raise ErrorConsulta(f"No existe el manifiesto indicado ({ruta.as_posix()}). No se guardó la consulta.")
    for ejemplo in (MANIFIESTOS_EJEMPLO if ejemplos is None else ejemplos):
        if Path(ejemplo).exists():
            return Path(ejemplo), [f"No existe {MANIFIESTO_POR_DEFECTO}: se usó el manifiesto de ejemplo "
                                   f"({Path(ejemplo).as_posix()}) para las unidades fiscalizables y los proyectos."]
    raise ErrorConsulta(f"No existe {MANIFIESTO_POR_DEFECTO} ni el manifiesto de ejemplo "
                        f"(ejemplos/manifiesto_ejemplo.csv). No se guardó la consulta: cree el manifiesto "
                        f"o indique uno con --manifiesto.")


def seleccionar_uf(uf, unidades, archivos_disponibles):
    """Elige la unidad fiscalizable pedida. Devuelve (nombre_exacto_de_la_uf, [archivos de esa UF]).
    Compara sin mayúsculas ni tildes; si no hay una igual, acepta una parte del nombre que apunte a una sola UF.
    Un PDF procesado sin fila en el manifiesto pertenece a "SIN UF ASIGNADA"."""
    por_uf = {}
    for archivo, filas in unidades.items():
        for unidad, _ in filas:
            por_uf.setdefault(unidad, []).append(archivo)
    for archivo in archivos_disponibles:
        if archivo not in unidades:
            por_uf.setdefault(SIN_UF, []).append(archivo)
    buscada = normalizar(uf)
    iguales = [u for u in por_uf if normalizar(u) == buscada]
    candidatas = iguales or [u for u in por_uf if buscada and buscada in normalizar(u)]
    if len(candidatas) == 1:
        return candidatas[0], sorted(dict.fromkeys(por_uf[candidatas[0]]))
    lista = "\n- ".join(sorted(por_uf)) or "(el manifiesto no tiene unidades)"
    if not candidatas:
        raise ErrorConsulta(f"No hay ninguna unidad fiscalizable «{uf}» en el manifiesto. Unidades disponibles:\n- {lista}")
    raise ErrorConsulta(f"«{uf}» calza con varias unidades fiscalizables; escriba el nombre más completo:\n- "
                        + "\n- ".join(sorted(candidatas)))


# ------------------------------------------------------------------ relaciones propuestas (término libre)

CAMPOS_PROPUESTA = {"archivo", "id_obligacion", "justificacion", "palabras_pdf", "pagina_pdf"}
ESTADOS_ACEPTADOS = ("confirmada", "aproximada")


def cargar_relaciones(ruta):
    """Lee el JSON de relaciones propuestas: una lista, o {"relaciones": [...]}."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorConsulta(f"No existe el archivo de relaciones propuestas: {ruta}.")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ErrorConsulta(f"{ruta.name} no es un JSON válido (línea {error.lineno}).") from error
    if isinstance(datos, dict):
        datos = datos.get("relaciones")
    if not isinstance(datos, list):
        raise ErrorConsulta(f"{ruta.name} debe contener una lista de relaciones (o {{\"relaciones\": [...]}}).")
    return datos


def verificar_relaciones(propuestas, rcas, terminos):
    """Comprueba por código cada relación propuesta para un término libre.
    Devuelve (aceptadas, rechazadas): aceptadas es {(archivo, id_obligacion): relación con estado "revisar"};
    rechazadas es una lista de {"relacion", "motivo"}. No modifica ninguna obligación."""
    por_archivo = {rca["archivo"]: rca for rca in rcas}
    aceptadas, rechazadas = {}, []

    def rechazar(propuesta, motivo):
        rechazadas.append({"relacion": propuesta, "motivo": motivo})

    for propuesta in propuestas:
        if not isinstance(propuesta, dict) or not CAMPOS_PROPUESTA <= set(propuesta):
            rechazar(propuesta, f"faltan campos; cada relación necesita {sorted(CAMPOS_PROPUESTA)}")
            continue
        rca = por_archivo.get(propuesta["archivo"])
        if rca is None:
            rechazar(propuesta, f"la RCA {propuesta['archivo']} no está en el alcance de esta consulta")
            continue
        obligacion = next((o for o in rca["obligaciones"] if o["id_obligacion"] == propuesta["id_obligacion"]), None)
        if obligacion is None:
            rechazar(propuesta, f"no existe la obligación {propuesta['id_obligacion']} en {propuesta['archivo']}")
            continue
        clave = (propuesta["archivo"], propuesta["id_obligacion"])
        if terminos_en_citas(obligacion, terminos):
            rechazar(propuesta, "el término ya está en una cita de la obligación: es coincidencia literal, no relación")
            continue
        if clave in aceptadas:
            rechazar(propuesta, "relación repetida para la misma obligación")
            continue
        justificacion = str(propuesta["justificacion"] or "")
        if "«" not in justificacion or len(justificacion.split()) < 5:
            rechazar(propuesta, "la justificación debe ser una frase que cite entre « » las palabras del PDF")
            continue
        palabras = str(propuesta["palabras_pdf"] or "").strip()
        paginas = {p["numero_pdf"]: p for p in rca["texto"]["paginas"]}
        pagina = paginas.get(propuesta["pagina_pdf"])
        if not palabras or pagina is None:
            rechazar(propuesta, "faltan palabras_pdf o la página no existe en el PDF")
            continue
        if pagina_sin_texto(pagina):
            rechazar(propuesta, f"la p. {propuesta['pagina_pdf']} no tiene texto: las palabras no se pueden comprobar por código")
            continue
        veredicto = verificar_citas.verificar_cita(palabras, propuesta["pagina_pdf"], rca["texto"]["paginas"])
        if veredicto["estado"] not in ESTADOS_ACEPTADOS:
            donde = f" (están en la p. {veredicto['pagina_encontrada']})" if veredicto.get("pagina_encontrada") else ""
            rechazar(propuesta, f"las palabras «{palabras}» no están en el texto de la p. {propuesta['pagina_pdf']}{donde}")
            continue
        aceptadas[clave] = {**propuesta, "palabras_pdf": palabras, "estado": "revisar",
                            "comprobacion": veredicto["estado"]}
    return aceptadas, rechazadas


# ------------------------------------------------------------------ consulta

def consultar(consulta, rcas, temas, unidades=None, uf=None, propuestas=None, prefijos=None):
    """Consulta un tema o término sobre RCAs ya cargadas (cargar_rca). No modifica nada.
    uf: nombre exacto de una unidad fiscalizable (ver seleccionar_uf); deja solo sus filas.
    propuestas: relaciones temáticas propuestas para un término libre (ver verificar_relaciones).
    prefijos: {archivo: prefijo} del manifiesto, para el ID visible (ARQ-024); sin prefijo se muestra el ID interno."""
    unidades = unidades or {}
    prefijos = prefijos or {}
    resuelta = resolver_consulta(consulta, temas)
    tema, terminos = resuelta["tema"], resuelta["terminos"]
    if propuestas is not None and tema is not None:
        raise ErrorConsulta(f"«{consulta}» es un tema de config/temas.yaml: su relación temática ya está anotada en las "
                            f"obligaciones (temas_relacionados). Las relaciones propuestas son solo para términos libres.")
    aceptadas, rechazadas = verificar_relaciones(propuestas, rcas, terminos) if propuestas is not None else ({}, [])
    filas, alcances, avisos = [], [], []
    if resuelta["aviso"]:
        avisos.append(resuelta["aviso"])
    conteo = {LITERAL: 0, RELACION: 0, MENCION: 0}
    for rca in rcas:
        avisos += rca["avisos"]
        alcances.append(alcance_de_rca(rca, tema))
        duplicados = grupos_de_duplicados(rca["obligaciones"])
        uf_proyectos = unidades.get(rca["archivo"]) or [(SIN_UF, "No consta (sin fila en el manifiesto)")]
        if uf is not None:
            uf_proyectos = [(u, p) for u, p in uf_proyectos if u == uf]
        literales = set()
        propias = []
        for obligacion in rca["obligaciones"]:
            hallados = terminos_en_citas(obligacion, terminos)
            ident = obligacion["id_obligacion"]
            representante = duplicados.get(ident, ident)
            comun = {
                "archivo": rca["archivo"], "numero_resolucion": rca["numero_resolucion"], "id_obligacion": ident,
                "id_visible": ids_visibles.id_visible(rca["archivo"], ident, prefijos),
                "tipo": obligacion.get("tipo"), "descripcion": obligacion.get("descripcion"),
                "plazo_o_frecuencia": obligacion.get("plazo_o_frecuencia"), "responsable": obligacion.get("responsable"),
                "pagina_pdf": obligacion.get("pagina_pdf"), "pagina_impresa": obligacion.get("pagina_impresa"),
                "cita_textual": obligacion.get("cita_textual"),
                "duplicado_de": NO_APLICA if representante == ident else ids_visibles.id_visible(rca["archivo"], representante, prefijos),
                "seccion_localizador": obligacion.get("seccion_localizador"), "contexto": NO_APLICA,
                "obligaciones_en_la_pagina": NO_APLICA,
            }
            if hallados:
                literales.add(ident)
                propias.append({**comun, "categoria": LITERAL,
                                "termino_encontrado": "; ".join(dict.fromkeys(e for _, e, _ in hallados)),
                                "donde_aparece": "; ".join(dict.fromkeys(d for _, _, d in hallados)),
                                "tema": tema or NO_APLICA, "justificacion": NO_APLICA})
            elif tema is not None:
                relacion = relacion_tematica(obligacion, tema)
                if relacion:
                    propias.append({**comun, "categoria": RELACION, "termino_encontrado": NO_APLICA,
                                    "donde_aparece": NO_APLICA, "tema": tema,
                                    "justificacion": ("(dudosa) " if relacion.get("dudosa") else "")
                                    + (relacion.get("justificacion") or "No consta")
                                    + (f" (p. {relacion['pagina_pdf']})" if relacion.get("pagina_pdf") else "")})
            elif (rca["archivo"], ident) in aceptadas:
                relacion = aceptadas[(rca["archivo"], ident)]
                propias.append({**comun, "categoria": RELACION, "termino_encontrado": NO_APLICA,
                                "donde_aparece": NO_APLICA, "tema": NO_APLICA,
                                "justificacion": "(propuesta en esta consulta) " + ("(dudosa) " if relacion.get("dudosa") else "")
                                + relacion["justificacion"] + f" (p. {relacion['pagina_pdf']})"
                                + (f" [{relacion['nota']}]" if relacion.get("nota") else "")})
        terminos_por_tema = {tema: terminos}
        for hallazgo in buscar_en_rca(rca["texto"], rca["obligaciones"], terminos_por_tema):
            if hallazgo["recogido_en"]:
                continue  # ya está dentro de la cita de una obligación (coincidencia literal)
            propias.append({
                "categoria": MENCION, "archivo": rca["archivo"], "numero_resolucion": rca["numero_resolucion"],
                "id_obligacion": NO_APLICA, "id_visible": NO_APLICA, "tipo": NO_APLICA, "descripcion": NO_APLICA,
                "plazo_o_frecuencia": NO_APLICA, "responsable": NO_APLICA,
                "pagina_pdf": hallazgo["pagina_pdf"], "pagina_impresa": hallazgo["pagina_impresa"] or NO_APLICA,
                "cita_textual": NO_APLICA, "termino_encontrado": hallazgo["encontrado"],
                "donde_aparece": "texto de la RCA" + (" (OCR previo)" if hallazgo["origen_texto"] == "ocr_previo" else ""),
                "tema": tema or NO_APLICA, "justificacion": NO_APLICA, "duplicado_de": NO_APLICA,
                "contexto": hallazgo["contexto"], "seccion_localizador": NO_APLICA,
                "obligaciones_en_la_pagina": ", ".join(ids_visibles.id_visible(rca["archivo"], i, prefijos)
                                                       for i in hallazgo["obligaciones_en_la_pagina"]) or "ninguna",
            })
        for fila in propias:
            conteo[fila["categoria"]] += 1
            for unidad, proyecto in uf_proyectos:
                filas.append({**fila, "unidad_fiscalizable": unidad, "proyecto": proyecto})
    orden = {LITERAL: 0, RELACION: 1, MENCION: 2}
    filas.sort(key=lambda f: (orden[f["categoria"]], f["unidad_fiscalizable"], f["archivo"], f["pagina_pdf"] or 0, f["id_obligacion"]))
    filas = [{c: valor_celda(f.get(c)) for c in COLUMNAS_CONSULTA} for f in filas]
    sin_resultados = not any(conteo.values())
    ahora = datetime.now().replace(microsecond=0)
    resumen_propuestas = None if propuestas is None else {"aceptadas": len(aceptadas), "rechazadas": len(rechazadas)}
    resultado = {
        "consulta": consulta, "tema": tema, "terminos": terminos, "tema_del_termino": resuelta["tema_del_termino"],
        "fecha": ahora.date().isoformat(),
        "fecha_hora": ahora.isoformat(sep=" "), "aviso": AVISO,
        "filtro": {"unidad_fiscalizable": uf, "archivos_pedidos": None, "archivos": [rca["archivo"] for rca in rcas]},
        "conteo": conteo, "sin_resultados": sin_resultados,
        "mensaje": (f"No hay resultados para «{consulta}» en el alcance indicado." if sin_resultados else None),
        "alcance": alcances, "alcance_texto": texto_de_alcance(alcances, tema, uf, resumen_propuestas),
        "avisos": avisos, "filas": filas,
    }
    if propuestas is not None:
        resultado["relaciones_propuestas"] = {"aceptadas": list(aceptadas.values()), "rechazadas": rechazadas}
    return resultado


def valor_celda(valor):
    if valor is None or valor == "":
        return NO_APLICA
    return valor


def nombre_seguro(texto):
    return re.sub(r"[^a-z0-9]+", "_", normalizar(texto)).strip("_") or "consulta"


SEPARADOR_CSV = ";"  # Excel en español (Chile) separa columnas con punto y coma


def guardar_csv(filas, columnas, ruta):
    """CSV en UTF-8 con BOM (para que Excel lea bien las tildes) y separado por punto y coma."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, delimiter=SEPARADOR_CSV)
        escritor.writeheader()
        escritor.writerows(filas)


# ------------------------------------------------------------------ línea de comandos

def archivos_a_buscar(carpeta_salida, archivos):
    if archivos:
        return archivos
    carpeta = Path(carpeta_salida) / "obligaciones"
    return sorted(f"{p.stem}.pdf" for p in carpeta.glob("*.json"))


def cargar_varias(archivos, carpeta_salida):
    rcas, errores = [], []
    for archivo in archivos:
        try:
            rcas.append(cargar_rca(archivo, carpeta_salida))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            errores.append(str(error))
    return rcas, errores


def archivos_de_la_consulta(opciones, unidades):
    """Archivos a consultar según --archivo y --uf, y avisos. Lanza ErrorConsulta si la UF no existe."""
    procesados = archivos_a_buscar(opciones.salida, None)
    archivos, avisos, uf = list(opciones.archivo or procesados), [], None
    if opciones.uf:
        uf, de_la_uf = seleccionar_uf(opciones.uf, unidades, procesados)
        if opciones.archivo:
            archivos = [a for a in archivos if a in de_la_uf]
            if not archivos:
                raise ErrorConsulta(f"Ninguno de los archivos pedidos pertenece a la unidad fiscalizable «{uf}».")
        else:
            archivos = de_la_uf
    candidatos = archivos if (opciones.uf or opciones.archivo) else sorted(set(procesados) | set(unidades))
    sin_obligaciones = [a for a in candidatos if a not in procesados]
    for archivo in sin_obligaciones:
        avisos.append(f"{archivo} está en el manifiesto pero no tiene obligaciones extraídas: no se incluye en la consulta "
                      f"(procesarla corresponde al flujo completo, skill procesar-carpeta).")
    return [a for a in archivos if a in procesados], uf, avisos


def comando_consultar(opciones, temas):
    try:
        manifiesto, avisos_manifiesto = resolver_manifiesto(opciones.manifiesto)
    except ErrorConsulta as error:
        print(f"ERROR: {error}")
        return 2
    unidades, avisos = unidades_por_archivo(manifiesto)
    avisos = avisos_manifiesto + avisos
    try:
        archivos, uf, avisos_archivos = archivos_de_la_consulta(opciones, unidades)
        propuestas = cargar_relaciones(opciones.relaciones) if opciones.relaciones else None
    except ErrorConsulta as error:
        print(f"ERROR: {error}")
        return 2
    rcas, errores = cargar_varias(archivos, opciones.salida)
    for error in errores:
        print(f"ERROR: {error}")
    for aviso in avisos_archivos:
        print(f"AVISO: {aviso}")
    if not rcas:
        print("No hay RCAs procesadas para consultar en el alcance pedido.")
        return 1
    try:
        resultado = consultar(opciones.consulta, rcas, temas, unidades, uf=uf, propuestas=propuestas,
                              prefijos=ids_visibles.prefijos_del_manifiesto(manifiesto))
    except ErrorConsulta as error:
        print(f"ERROR: {error}")
        return 2
    resultado["avisos"] = avisos + avisos_archivos + errores + resultado["avisos"]
    resultado["filtro"]["archivos_pedidos"] = opciones.archivo or None
    resultado["filtro"]["manifiesto"] = manifiesto.as_posix()
    # La consulta no toca el Excel: entra en la hoja Consulta solo si el usuario lo pide
    # (exportar_excel.py --agregar-consulta), que cambia esta marca a true.
    resultado["en_excel"] = False
    marca = resultado["fecha_hora"].replace("-", "").replace(":", "").replace(" ", "-")
    base = Path(opciones.salida) / "consultas" / f"consulta_{nombre_seguro(opciones.consulta)}_{marca}"
    base.parent.mkdir(parents=True, exist_ok=True)
    numero = 2
    while base.with_suffix(".json").exists():  # dos consultas en el mismo segundo no se pisan
        base = base.with_name(f"consulta_{nombre_seguro(opciones.consulta)}_{marca}_{numero}")
        numero += 1
    base.with_suffix(".json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    guardar_csv(resultado["filas"], COLUMNAS_CONSULTA, base.with_suffix(".csv"))

    que = f"tema «{resultado['tema']}» ({', '.join(resultado['terminos'])})" if resultado["tema"] else f"término «{opciones.consulta}»"
    print(f"== Consulta: {que}. {AVISO}")
    for linea in resultado["alcance_texto"]:
        print(linea)
    for aviso in resultado["avisos"]:
        print(f"AVISO: {aviso}")
    for rechazada in (resultado.get("relaciones_propuestas") or {}).get("rechazadas", []):
        relacion = rechazada["relacion"]
        quien = f"{relacion.get('archivo')} {relacion.get('id_obligacion')}" if isinstance(relacion, dict) else repr(relacion)
        print(f"RELACIÓN RECHAZADA: {quien}: {rechazada['motivo']}")
    if resultado["sin_resultados"]:
        print(resultado["mensaje"])
    for categoria in (LITERAL, RELACION, MENCION):
        print(f"\n-- {categoria}: {resultado['conteo'][categoria]}")
        vistas, por_pagina = set(), {}
        for fila in resultado["filas"]:
            clave = (fila["archivo"], fila["id_obligacion"], fila["pagina_pdf"], fila["contexto"])
            if fila["categoria"] != categoria or clave in vistas:
                continue
            vistas.add(clave)
            if categoria == MENCION:
                por_pagina.setdefault(fila["archivo"], {}).setdefault(fila["pagina_pdf"], []).append(fila["termino_encontrado"])
            else:
                extra = fila["termino_encontrado"] if categoria == LITERAL else fila["justificacion"]
                print(f"   {fila['id_visible']} ({fila['archivo']}) (p. {fila['pagina_pdf']}): {fila['descripcion'][:90]} [{extra}]")
        for archivo, paginas in por_pagina.items():
            detalle = "; ".join(f"p. {p}: {', '.join(t)}" for p, t in paginas.items())
            print(f"   {archivo} ({len(paginas)} páginas; contexto de cada una en el CSV): {detalle}")
    print(f"\nResultado: {base.with_suffix('.csv').as_posix()} y {base.with_suffix('.json').as_posix()}")
    return 0


def comando_revisar(opciones, temas):
    rcas, errores = cargar_varias(archivos_a_buscar(opciones.salida, opciones.archivo), opciones.salida)
    for error in errores:
        print(f"ERROR: {error}")
    for rca in rcas:
        etiquetas = []
        for obligacion in rca["obligaciones"]:
            literales = temas_literales(obligacion, temas)
            etiquetas.append({"id_obligacion": obligacion["id_obligacion"], "temas_literales": [
                {"tema": tema, "termino": t, "encontrado": e, "donde": d}
                for tema, hallados in literales.items() for t, e, d in hallados]})
        hallazgos = buscar_en_rca(rca["texto"], rca["obligaciones"], temas)
        informe = {"archivo": rca["archivo"], "sha256": rca["texto"].get("sha256"), "fecha": date.today().isoformat(),
                   "aviso": AVISO, "alcance": alcance_de_rca(rca), "avisos": rca["avisos"],
                   "obligaciones": etiquetas, "resumen_por_termino": resumen_por_termino(hallazgos), "hallazgos": hallazgos}
        destino = Path(opciones.salida) / "temas" / f"{Path(rca['archivo']).stem}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
        con_tema = sum(1 for e in etiquetas if e["temas_literales"])
        print(f"== {rca['archivo']}: {con_tema} de {len(etiquetas)} obligaciones con tema literal; "
              f"{len(hallazgos)} apariciones en el texto -> {destino.as_posix()}")
    return 1 if errores and not rcas else 0


def comando_descripcion_sin_cita(opciones, temas):
    rcas, errores = cargar_varias(archivos_a_buscar(opciones.salida, opciones.archivo), opciones.salida)
    for error in errores:
        print(f"ERROR: {error}")
    filas = []
    for rca in rcas:
        textos = {pg["numero_pdf"]: pg.get("texto") or "" for pg in rca["texto"]["paginas"]}
        for obligacion in rca["obligaciones"]:
            paginas_citas = sorted({pagina for _, pagina, _ in citas_de(obligacion) if pagina is not None})
            for tema, termino, encontrado in terminos_en_descripcion_sin_cita(obligacion, temas):
                en_paginas = [str(pg) for pg in paginas_citas if buscar(textos.get(pg, ""), termino)]
                filas.append({
                    "paginas_de_las_citas_donde_aparece": ", ".join(en_paginas) or "ninguna (no está en el texto de esas páginas)",
                    "archivo": rca["archivo"], "id_obligacion": obligacion["id_obligacion"],
                    "pagina_pdf": obligacion.get("pagina_pdf"), "tema": tema, "termino": termino,
                    "encontrado_en_descripcion": encontrado, "descripcion": obligacion.get("descripcion"),
                    "cita_textual": obligacion.get("cita_textual"),
                    "citas_adicionales": " | ".join(f"p. {c.get('pagina_pdf')}: {c.get('cita_textual')}"
                                                    for c in obligacion.get("citas_adicionales") or []) or NO_APLICA,
                })
    destino = Path(opciones.salida) / "verificacion" / "terminos_descripcion_sin_cita.csv"
    guardar_csv(filas, COLUMNAS_DESCRIPCION, destino)
    print(f"== {len(filas)} casos (término en la descripción y no en las citas) en "
          f"{len({(f['archivo'], f['id_obligacion']) for f in filas})} obligaciones -> {destino.as_posix()}")
    for f in filas:
        print(f"   {f['archivo']} {f['id_obligacion']} p. {f['pagina_pdf']} [{f['tema']}] «{f['encontrado_en_descripcion']}» "
              f"-> en el texto de la p.: {f['paginas_de_las_citas_donde_aparece']}")
    return 0


CAMPOS_FICHA_OBLIGACION = ["tipo", "componente_ambiental", "fase", "descripcion", "plazo_o_frecuencia", "hito_o_gatillo",
                           "responsable", "autoridad_destinataria", "medio_de_verificacion", "parametro_o_indicador",
                           "ubicacion_en_documento", "pagina_pdf", "pagina_impresa", "cita_textual", "confianza", "fuente",
                           "posible_duplicado", "notas"]


def buscar_obligacion(texto_id, rcas, prefijos):
    """[(rca, obligación)] para un ID visible (ARQ-024) o interno (OBL-024, en todas las RCAs)."""
    encontradas = []
    for archivo, interno in ids_visibles.resolver(texto_id, prefijos):
        for rca in rcas:
            if archivo in (None, rca["archivo"]):
                encontradas += [(rca, o) for o in rca["obligaciones"] if o["id_obligacion"] == interno]
    return encontradas


def comando_obligacion(opciones, temas):
    """Muestra una obligación completa por su ID visible o interno. Solo lee."""
    try:
        manifiesto, avisos = resolver_manifiesto(opciones.manifiesto)
    except ErrorConsulta as error:
        manifiesto, avisos = None, [str(error)]
    prefijos = ids_visibles.prefijos_del_manifiesto(manifiesto)
    rcas, errores = cargar_varias(archivos_a_buscar(opciones.salida, None), opciones.salida)
    for aviso in avisos + errores:
        print(f"AVISO: {aviso}")
    encontradas = buscar_obligacion(opciones.id, rcas, prefijos)
    if not encontradas:
        print(f"No hay ninguna obligación «{opciones.id}» en las RCAs procesadas. Prefijos del manifiesto: "
              + (", ".join(f"{p} ({a})" for a, p in sorted(prefijos.items())) or "ninguno"))
        return 1
    for rca, o in encontradas:
        print(f"== {ids_visibles.id_visible(rca['archivo'], o['id_obligacion'], prefijos)} "
              f"(ID interno {o['id_obligacion']}, {rca['archivo']}). {AVISO}")
        for campo in CAMPOS_FICHA_OBLIGACION:
            valor = o.get(campo)
            if campo == "posible_duplicado":
                valor = ", ".join(ids_visibles.id_visible(rca["archivo"], i, prefijos) for i in valor or []) or NO_APLICA
            print(f"   {campo}: {valor if valor not in (None, '', []) else NO_APLICA}")
        for c in o.get("citas_adicionales") or []:
            print(f"   cita adicional (p. {c.get('pagina_pdf')}): {c.get('cita_textual')}")
        for r in o.get("temas_relacionados") or []:
            print(f"   relación temática [revisar]{' (dudosa)' if r.get('dudosa') else ''}: {r.get('tema')}: "
                  f"{r.get('justificacion')} (p. {r.get('pagina_pdf')})")
    return 0


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Búsqueda exacta de temas y términos en obligaciones y texto de RCAs.")
    parser.add_argument("--salida", default="salida", help="Carpeta de salida (por defecto: salida)")
    parser.add_argument("--temas", default=str(TEMAS_POR_DEFECTO), help="Archivo de temas (por defecto: config/temas.yaml)")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_consultar = sub.add_parser("consultar", help="Consulta un tema o término en las obligaciones")
    p_consultar.add_argument("consulta", help="Tema de config/temas.yaml o cualquier palabra o frase")
    p_consultar.add_argument("--manifiesto", default=MANIFIESTO_POR_DEFECTO,
                             help="Por defecto manifiesto.csv; si no existe, ejemplos/manifiesto_ejemplo.csv (con aviso)")
    p_consultar.add_argument("--uf", help="Solo las RCAs de esta unidad fiscalizable del manifiesto")
    p_consultar.add_argument("--relaciones", help="JSON con relaciones propuestas para un término libre (se comprueban por código)")
    for p in (p_consultar, sub.add_parser("revisar", help="Temas literales y apariciones por RCA"),
              sub.add_parser("descripcion-sin-cita", help="Términos en la descripción que no están en las citas")):
        p.add_argument("--archivo", action="append", help="Limitar a este PDF (se puede repetir)")
    p_obligacion = sub.add_parser("obligacion", help="Muestra una obligación por su ID visible (ARQ-024) o interno")
    p_obligacion.add_argument("id", help="ID visible (ARQ-024) o interno (OBL-024)")
    p_obligacion.add_argument("--manifiesto", default=MANIFIESTO_POR_DEFECTO)
    opciones = parser.parse_args(argumentos)
    try:
        temas = cargar_temas(opciones.temas)
    except ErrorTemas as error:
        print(f"ERROR: {error}")
        return 2
    comandos = {"consultar": comando_consultar, "revisar": comando_revisar, "descripcion-sin-cita": comando_descripcion_sin_cita,
                "obligacion": comando_obligacion}
    return comandos[opciones.comando](opciones, temas)


if __name__ == "__main__":
    sys.exit(main())
