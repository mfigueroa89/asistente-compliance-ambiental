"""Ubica en qué páginas de una RCA están sus secciones principales (sin IA).

Uso:
    python scripts/localizar_secciones.py RUTA [RUTA ...] [--salida salida]

RUTA puede ser el JSON de salida/texto/ (generado por leer_pdf.py) o el PDF.
Resultado: salida/secciones/<archivo>.json y un resumen en pantalla.

Cómo ubica las secciones:
1. Considerandos de las RCAs modernas: "7°. Que, ... las siguientes medidas de mitigación ...".
   El texto que sigue al número indica de qué sección se trata. Antes de leerlo se reemplaza el
   texto entre comillas (rectas, curvas o « ») para que un nombre de proyecto largo no tape el tema.
   Si en la numeración falta un considerando (por ejemplo, hay 3 y 5 pero no 4), se busca un párrafo
   que empiece con "4." aunque no diga "Que" ("4. Respecto de las observaciones ciudadanas ...");
   esos considerandos recuperados quedan con confianza media.
2. Títulos numerados de las RCAs antiguas: "6. Medidas de Mitigación, Reparación y Compensación".
3. Títulos sin número ("Plan de Seguimiento"): solo se usan si no hay 1 ni 2 (confianza baja).
La parte resolutiva empieza en "RESUELVO" y llega hasta el final.

Cada sección va desde la página de su título hasta la página donde empieza el título siguiente.
En las RCAs con títulos numerados, un título sin tema reconocido cierra la sección solo si su número
es cercano (como máximo 3 más), y una celda de tabla como "23. LP-24. TB-1" no cuenta como título.
Si no ubica una sección, no adivina: lo avisa y propone las páginas donde solo se menciona.

Un tramo de una sola página lejos del bloque principal de su sección queda "aislado" (confianza baja)
y no se suma a las páginas que leen las skills. Los títulos se comparan también sin espacios internos,
porque el OCR a veces parte palabras ("m itigación").

Considerandos de trámite ("deberá remitir/informar a la Superintendencia", "son de responsabilidad
del Titular", "cambio de consideración") no se clasifican como sección temática: van a la sección
"otros_tramite", que la extracción de obligaciones también lee (pueden contener obligaciones de
reporte o aviso). Solo la cláusula estándar de seguimiento ("para el debido y adecuado seguimiento
de las condiciones, compromisos o medidas y permisos ...") queda fuera de toda sección.
Las páginas de índice (muchos títulos de secciones distintas juntos) se ignoran.
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import leer_pdf

VERSION = "0.4.1"
PAGINAS_IDENTIFICACION = 3
# Páginas de cada sección que necesita la ficha (la extracción de obligaciones lee las secciones completas).
PAGINAS_FICHA_POR_SECCION = {"efectos_articulo_11": 15, "permisos_sectoriales": 15, "participacion_ciudadana": 3, "parte_resolutiva": 5,
                             "otros_tramite": 0, "normativa_aplicable": 0}
PAGINAS_FICHA_OTRAS = 2  # de las secciones de obligaciones basta ver su inicio para saber si existen
# Desde la versión 0.4.0 la Etapa 4 también lee los permisos sectoriales (solo sus deberes explícitos)
# y la normativa aplicable (solo las formas concretas de cumplimiento o reporte que fija la RCA).
SECCIONES_DE_OBLIGACIONES = ["medidas", "compromisos_voluntarios", "plan_seguimiento", "contingencias", "condiciones_exigencias",
                             "otros_tramite", "permisos_sectoriales", "normativa_aplicable", "parte_resolutiva"]
LARGO_MAXIMO_TITULO = 160
CARACTERES_ANALIZADOS_CONSIDERANDO = 260
CARACTERES_LEIDOS_CONSIDERANDO = 900  # se leen más y, sin el texto entre comillas, se analizan 260
MAXIMO_MENCIONES_PROPUESTAS = 15
DISTANCIA_TRAMO_AISLADO = 10  # un tramo de 1 página a más de 10 páginas del bloque principal se considera aislado
# Desde la versión 0.4.1: un título numerado sin tema reconocido solo cierra una sección si su número es, como
# máximo, 3 más que el de la sección (la 7 la cierran la 8, la 9 o la 10; un "23." suelto, no).
SALTO_MAXIMO_TITULO = 3

# Secciones pedidas y secciones de apoyo para la ficha. Las frases se comparan sin tildes ni mayúsculas.
SECCIONES = {
    "medidas": {
        "nombre": "Medidas de mitigación, reparación y compensación",
        "frases": [
            r"medidas? (apropiadas )?de (mitigacion|reparacion|compensacion)",
            r"(las )?siguientes medidas\b",  # "puede concluirse que las siguientes medidas, propuestas por el titular"
        ],
    },
    "compromisos_voluntarios": {
        "nombre": "Compromisos ambientales voluntarios",
        "frases": [r"compromisos? (ambientales? )?voluntarios?"],  # también "compromiso voluntario"
    },
    "plan_seguimiento": {
        "nombre": "Plan de seguimiento",
        "frases": [
            r"plan(es)? de seguimiento",
            r"seguimiento de (las )?variables ambientales",
            r"programa de (seguimiento|monitoreo)",
            r"plan de monitoreo",
        ],
    },
    "contingencias": {
        "nombre": "Contingencias y emergencias",
        "frases": [
            r"(plan(es)? de )?prevencion de (contingencias|riesgos?)",
            r"plan(es)? de (contingencias?|emergencias?)",
            r"control de (accidentes?|emergencias?)",
            r"riesgos? y contingencias?",
        ],
    },
    "condiciones_exigencias": {
        "nombre": "Condiciones o exigencias",
        "frases": [
            r"condiciones? (o|y|u) exigencias?",
            r"exigencias? (especificas|adicionales)",
            r"deben cumplirse las siguientes condiciones",
        ],
    },
    # Secciones de apoyo para la ficha (sección 7 de la especificación).
    "efectos_articulo_11": {
        "nombre": "Efectos del artículo 11 de la Ley 19.300",
        "frases": [r"efectos,? caracteristicas (o|y) circunstancias", r"articulo 11"],
        "apoyo": True,
    },
    "permisos_sectoriales": {
        "nombre": "Permisos ambientales sectoriales",
        "frases": [r"permisos? ambientales? sectoriales?", r"permisos? de caracter ambiental"],  # D.S. 95/2001
        "apoyo": True,
    },
    "participacion_ciudadana": {
        "nombre": "Participación ciudadana",
        "frases": [r"participacion ciudadana", r"observaciones ciudadanas", r"observaciones (formuladas )?(por|de) la comunidad"],
        "apoyo": True,
    },
    "normativa_aplicable": {
        "nombre": "Normativa ambiental aplicable y su forma de cumplimiento",
        "frases": [r"cumplimiento de la normativa (de caracter )?ambiental", r"normativa (de caracter )?ambiental aplicable"],
        "apoyo": True,
    },
    # Considerandos de trámite: no son una sección temática, pero la Etapa 4 los lee (reportes y avisos).
    # Se reconocen solo en considerandos, con las frases de TRAMITE (no por títulos ni menciones).
    "otros_tramite": {
        "nombre": "Otros considerandos de trámite (reportes y avisos)",
        "frases": [],
        "opcional": True,
    },
}

# Frases de los considerandos de trámite (sin tildes ni mayúsculas).
TRAMITE = [
    r"debera (remitir|informar|comunicar)\b[^.]{0,120}superintendencia",
    r"son de responsabilidad del titular",
    r"cambio de consideracion",
]
# Cláusula estándar de seguimiento: no pertenece a ninguna sección (se lista aparte en el resultado).
TRAMITE_EXCLUIDO = [r"para el debido y adecuado seguimiento de las condiciones"]
# Comillas rectas, curvas, bajas y angulares (el OCR las confunde): el texto entre ellas se reemplaza.
PATRON_ENTRE_COMILLAS = re.compile(r"[\"“”„«»][^\"“”„«»\n]{3,300}[\"“”„«»]")

PATRON_RESUELVO = re.compile(r"\bR\s?E\s?S\s?U\s?E\s?L\s?V\s?[OE]\b")  # RESUELVO o RESUELVE
# "7°. Que," / "12° Que" / "7º.- Que" / "9. Que" (RCAs antiguas, sin el símbolo °).
PATRON_CONSIDERANDO = re.compile(r"(?<![\w.,/])(\d{1,2})\s?(?:[°º]\s?\.?|\.)\s?-?\s*Que\b")
# "6. Medidas ...", "10. Condiciones ...", "1 O. Condiciones" (OCR), "VII. Plan ...", "-7. Plan ..." (OCR).
PATRON_TITULO_NUMERADO = re.compile(r"^\W{0,3}(\d{1,2}|\d ?[oO]|[IVX]{1,5})\s?[.°)\-]\s*(?!\d)")
# Celda de tabla que el OCR deja como párrafo: un número seguido de códigos cortos de punto de muestreo
# ("23. LP-24. TB-1. TB-2 ..."). No es un título aunque empiece con "23.".
PATRON_CODIGO_TABLA = re.compile(r"^\W{0,3}\d{1,3}\s?\.\s*[A-ZÑ]{1,4}-\d{1,3}\b")


def normalizar(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).lower()


def quitar_comillas(texto):
    """Reemplaza el texto entre comillas por un marcador (solo para clasificar; el original no cambia)."""
    return PATRON_ENTRE_COMILLAS.sub('"..."', texto)


def clasificar_considerando(texto):
    """Clasifica el comienzo de un considerando. Devuelve (secciones, excluido)."""
    analizado = quitar_comillas(texto)[:CARACTERES_ANALIZADOS_CONSIDERANDO]
    normal = normalizar(analizado)
    if any(re.search(f, normal) for f in TRAMITE_EXCLUIDO):
        return [], True
    if any(re.search(f, normal) for f in TRAMITE):
        return ["otros_tramite"], False
    return clasificar_principal(analizado), False


def clasificar(texto):
    """Devuelve la lista de secciones cuyas frases aparecen en el texto (normalizado)."""
    normal = normalizar(texto)
    return [clave for clave, datos in SECCIONES.items() if any(re.search(f, normal) for f in datos["frases"])]


def clasificar_principal(texto):
    """Sección principal de un título o considerando: la del tema que aparece primero.

    Ejemplo: "7°. Que, ... las siguientes medidas de mitigación ... para hacerse cargo de los
    efectos del artículo 11" es de medidas, no de efectos del artículo 11.
    """
    normal = normalizar(texto)
    mejor, posicion = None, None
    for clave, datos in SECCIONES.items():
        for frase in datos["frases"]:
            coincidencia = re.search(frase, normal)
            if coincidencia and (posicion is None or coincidencia.start() < posicion):
                mejor, posicion = clave, coincidencia.start()
    return [mejor] if mejor else []


def clasificar_titulo(texto):
    """Como clasificar_principal, pero si no reconoce nada compara también sin espacios internos.

    El OCR a veces parte palabras ("Medidas de m itigación"). Se compara una versión del título sin
    espacios contra las mismas frases sin espacios. Solo se usa en títulos (párrafos cortos).
    """
    principal = clasificar_principal(texto)
    if principal:
        return principal
    compacto = normalizar(texto).replace(" ", "")
    mejor, posicion = None, None
    for clave, datos in SECCIONES.items():
        for frase in datos["frases"]:
            coincidencia = re.search(frase.replace(" ", ""), compacto)
            if coincidencia and (posicion is None or coincidencia.start() < posicion):
                mejor, posicion = clave, coincidencia.start()
    return [mejor] if mejor else []


def numero_titulo(texto):
    """Número de un título numerado ("6." -> 6, "1 O." -> 10, "VII." -> 7) o None."""
    coincidencia = PATRON_TITULO_NUMERADO.match(texto)
    if not coincidencia:
        return None
    valor = coincidencia.group(1).replace(" ", "")
    if re.fullmatch(r"\d[oO]", valor):  # OCR confunde 0 con O
        return int(valor[0] + "0")
    if valor.isdigit():
        return int(valor)
    romanos = {"I": 1, "V": 5, "X": 10}
    total = 0
    for indice, letra in enumerate(valor):
        siguiente = romanos[valor[indice + 1]] if indice + 1 < len(valor) else 0
        total += -romanos[letra] if romanos[letra] < siguiente else romanos[letra]
    return total


# ------------------------------------------------------------ hallazgos

def nuevo_considerando(texto, posicion, pagina, numero, metodo):
    fragmento = texto[posicion: posicion + CARACTERES_LEIDOS_CONSIDERANDO]
    secciones, excluido = clasificar_considerando(fragmento)
    return {
        "pagina": pagina,
        "posicion": posicion,
        "numero": numero,
        "titulo": re.sub(r"\s+", " ", fragmento[:CARACTERES_ANALIZADOS_CONSIDERANDO]).strip(),
        "secciones": secciones,
        "excluido": excluido,
        "metodo": metodo,
    }


def patron_numero_inicial(numero):
    """Párrafo o línea que empieza con el número: "4. ...", "4.- ...", "4° ...", "1 O. ..." (OCR de 10)."""
    digitos = re.escape(str(numero))
    if numero % 10 == 0:
        digitos = f"(?:{digitos}|{str(numero)[:-1]}\\s?[oO])"
    return re.compile(rf"(?m)^\W{{0,3}}{digitos}\s?[°º]?\s?(?:\.|\)|-)\s*-?\s*(?!\d)(?=\w)")


def recuperar_por_hueco(paginas, considerandos, titulos):
    """Considerandos sin "Que" que faltan en la numeración (confianza media).

    Si se detectaron los considerandos 3 y 5 pero no el 4, busca entre ambos (en orden de lectura) el
    primer párrafo que empiece con "4.". No recupera un número que ya se ubicó como título numerado.
    """
    if len(considerandos) < 2:
        return []
    por_numero = {}
    for c in considerandos:
        por_numero.setdefault(c["numero"], c)
    numeros = sorted(por_numero)
    texto_de = {p["numero_pdf"]: p["texto"] for p in paginas}
    recuperados = []
    for anterior, siguiente in zip(numeros, numeros[1:]):
        desde, hasta = por_numero[anterior], por_numero[siguiente]
        if (hasta["pagina"], hasta["posicion"]) <= (desde["pagina"], desde["posicion"]):
            continue  # numeración fuera de orden: no se adivina
        limite = (desde["pagina"], desde["posicion"])
        for faltante in range(anterior + 1, siguiente):
            if any(t["numero"] == faltante and desde["pagina"] <= t["pagina"] <= hasta["pagina"] for t in titulos):
                continue
            patron = patron_numero_inicial(faltante)
            for pagina in range(limite[0], hasta["pagina"] + 1):
                texto = texto_de.get(pagina, "")
                inicio = limite[1] + 1 if pagina == limite[0] else 0
                fin = hasta["posicion"] if pagina == hasta["pagina"] else len(texto)
                coincidencia = patron.search(texto, inicio, fin)
                if coincidencia:
                    nuevo = nuevo_considerando(texto, coincidencia.start(), pagina, faltante, "considerando_sin_que")
                    recuperados.append(nuevo)
                    limite = (pagina, coincidencia.start())
                    break
    return recuperados


def buscar_hallazgos(paginas):
    """Recorre el texto y devuelve considerandos, títulos numerados, títulos sin número y menciones."""
    considerandos, titulos, subtitulos, sin_numero, menciones = [], [], [], [], {}
    resuelvo = None
    for pagina in paginas:
        numero_pagina = pagina["numero_pdf"]
        texto = pagina["texto"]
        if resuelvo is None and PATRON_RESUELVO.search(texto):
            resuelvo = numero_pagina
        for coincidencia in PATRON_CONSIDERANDO.finditer(texto):
            considerandos.append(nuevo_considerando(texto, coincidencia.start(), numero_pagina, int(coincidencia.group(1)),
                                                    "considerando"))
        cursor = 0
        for parrafo in texto.split("\n\n"):
            posicion = texto.find(parrafo, cursor)
            cursor = max(cursor, posicion + len(parrafo))
            parrafo_limpio = re.sub(r"\s+", " ", parrafo).strip()
            if not parrafo_limpio:
                continue
            secciones = clasificar(parrafo_limpio)
            for clave in secciones:
                menciones.setdefault(clave, set()).add(numero_pagina)
            if len(parrafo_limpio) > LARGO_MAXIMO_TITULO:
                continue
            es_subtitulo = re.match(r"^\W{0,3}\d{1,2}\s?\.\s?\d", parrafo_limpio)  # "9.1. Medidas ..."
            es_oracion = re.search(r"[a-záéíóúñ]{4,}\.$", parrafo_limpio)  # "...deberá informar." (no "E.I.A.")
            if es_oracion and not es_subtitulo:
                continue  # una oración no es un título (salvo subtítulos "9.1. ...")
            if PATRON_CODIGO_TABLA.match(parrafo_limpio):
                continue  # celda de tabla con códigos de muestreo, no un título
            principal = clasificar_titulo(parrafo_limpio)
            numero = numero_titulo(parrafo_limpio)
            if numero is not None and not es_subtitulo:
                titulos.append({"pagina": numero_pagina, "posicion": posicion, "numero": numero, "titulo": parrafo_limpio,
                                "secciones": principal})
            elif es_subtitulo and principal:
                subtitulos.append({"pagina": numero_pagina, "numero": numero or 0, "titulo": parrafo_limpio, "secciones": principal})
            elif principal:
                sin_numero.append({"pagina": numero_pagina, "titulo": parrafo_limpio, "secciones": principal})
    return considerandos, titulos, subtitulos, sin_numero, menciones, resuelvo


def paginas_de_indice(titulos, sin_numero):
    """Páginas con títulos de 4 o más secciones distintas: probablemente un índice."""
    por_pagina = {}
    for item in titulos + sin_numero:
        por_pagina.setdefault(item["pagina"], set()).update(item["secciones"])
    return sorted(pagina for pagina, secciones in por_pagina.items() if len(secciones) >= 4)


# ------------------------------------------------------------- secciones

def fin_de_seccion(inicio, numero, metodo, considerandos, titulos, resuelvo, n_paginas, posicion=-1):
    """Página donde termina una sección: la del siguiente considerando o título del mismo nivel."""
    candidatos = []
    if metodo == "considerando":
        candidatos += [c["pagina"] for c in considerandos if c["numero"] > numero and c["pagina"] >= inicio]
        # RCAs antiguas mezclan "9. Que, ..." con títulos "10. Medidas de prevención ...": también cortan,
        # incluso en la misma página si el título viene después del considerando.
        candidatos += [t["pagina"] for t in titulos if t["numero"] > numero and t["secciones"]
                       and (t["pagina"] > inicio or (t["pagina"] == inicio and t["posicion"] > posicion))]
    else:
        # Un título sin tema reconocido y con un número muy lejano (p. ej. "23." dentro de una tabla) no cierra la sección.
        candidatos += [t["pagina"] for t in titulos if t["numero"] > numero and t["pagina"] >= inicio
                       and (t["secciones"] or t["numero"] <= numero + SALTO_MAXIMO_TITULO)]
        candidatos += [c["pagina"] for c in considerandos if c["pagina"] > inicio]
    if resuelvo and resuelvo >= inicio:
        candidatos.append(resuelvo)
    return min(candidatos) if candidatos else n_paginas


def marcar_aislados(tramos):
    """Marca como aislado (confianza baja) un tramo de una página lejos del bloque principal.

    El bloque principal es el tramo más largo (debe tener 2 páginas o más). Un tramo de una sola página
    a más de DISTANCIA_TRAMO_AISLADO páginas de todos los demás tramos no aislados queda "aislado": no se
    suma a las páginas que leen las skills ni al rango de la ficha.
    """
    if len(tramos) < 2:
        return
    principal = max(tramos, key=lambda t: t["pagina_fin"] - t["pagina_inicio"])
    if principal["pagina_fin"] == principal["pagina_inicio"]:
        return
    for tramo in tramos:
        if tramo is principal or tramo["pagina_fin"] != tramo["pagina_inicio"]:
            continue
        otros = [t for t in tramos if t is not tramo and not t.get("aislado")]
        distancia = min(max(t["pagina_inicio"] - tramo["pagina_fin"], tramo["pagina_inicio"] - t["pagina_fin"], 0) for t in otros)
        if distancia > DISTANCIA_TRAMO_AISLADO:
            tramo["aislado"] = True
            tramo["confianza"] = "baja"


def tramos_utiles(seccion_o_tramos):
    """Tramos que cuentan para lectura y rangos (sin los aislados)."""
    tramos = seccion_o_tramos["tramos"] if isinstance(seccion_o_tramos, dict) else seccion_o_tramos
    return [t for t in tramos if not t.get("aislado")]


def confianza_de(tramos):
    """Confianza de la sección: la más baja de sus tramos útiles (los aislados no cuentan)."""
    utiles = tramos_utiles(tramos)
    if not utiles:
        return None
    orden = {"alta": 0, "media": 1, "baja": 2}
    return max((t["confianza"] for t in utiles), key=orden.get)


def localizar(datos_texto):
    """Recibe el diccionario de leer_pdf.py y devuelve el mapa de secciones."""
    paginas = datos_texto["paginas"]
    n_paginas = len(paginas)
    considerandos, titulos, subtitulos, sin_numero, menciones, resuelvo = buscar_hallazgos(paginas)
    considerandos = sorted(considerandos + recuperar_por_hueco(paginas, considerandos, titulos),
                           key=lambda c: (c["pagina"], c["posicion"]))
    excluidos = [c for c in considerandos if c["excluido"]]
    indice = paginas_de_indice(titulos, sin_numero)
    titulos = [t for t in titulos if t["pagina"] not in indice]
    subtitulos = [t for t in subtitulos if t["pagina"] not in indice]
    sin_numero = [t for t in sin_numero if t["pagina"] not in indice]

    secciones, avisos = {}, []
    for clave, definicion in SECCIONES.items():
        principales = [dict(c) for c in considerandos if clave in c["secciones"]]
        if not principales:
            principales = [dict(t, metodo="titulo_numerado") for t in titulos if clave in t["secciones"]]
        tramos = []
        for item in principales:
            inicio = item["pagina"]
            metodo_fin = "considerando" if item["metodo"].startswith("considerando") else item["metodo"]
            fin = fin_de_seccion(inicio, item["numero"], metodo_fin, considerandos, titulos, resuelvo, n_paginas,
                                 item.get("posicion", -1))
            tramo = {"pagina_inicio": inicio, "pagina_fin": max(fin, inicio), "titulo": item["titulo"], "metodo": item["metodo"],
                     "confianza": "media" if item["metodo"] == "considerando_sin_que" else "alta"}
            if not any(t["pagina_inicio"] == tramo["pagina_inicio"] and t["pagina_fin"] == tramo["pagina_fin"] for t in tramos):
                tramos.append(tramo)
        marcar_aislados(tramos)
        confianza = confianza_de(tramos)
        if not tramos:
            medias = [t for t in subtitulos if clave in t["secciones"]]
            for item in medias:
                inicio = item["pagina"]
                fin = fin_de_seccion(inicio, item["numero"], "titulo_numerado", considerandos, titulos, resuelvo, n_paginas)
                tramos.append({"pagina_inicio": inicio, "pagina_fin": max(fin, inicio), "titulo": item["titulo"],
                               "metodo": "subtitulo_numerado", "confianza": "media"})
            if tramos:
                marcar_aislados(tramos)
                confianza = confianza_de(tramos)
        if not tramos:
            debiles = [t for t in sin_numero if clave in t["secciones"]]
            if debiles:
                confianza = "baja"
                tramos = [{"pagina_inicio": t["pagina"], "pagina_fin": t["pagina"], "titulo": t["titulo"],
                           "metodo": "titulo_sin_numero", "confianza": "baja"} for t in debiles]
        fuera_de_rango = [
            {"pagina": t["pagina"], "titulo": t["titulo"]}
            for t in sin_numero
            if clave in t["secciones"] and not any(tr["pagina_inicio"] <= t["pagina"] <= tr["pagina_fin"] for tr in tramos)
        ]
        paginas_mencion = sorted(menciones.get(clave, set()))
        seccion = {
            "nombre": definicion["nombre"],
            "apoyo_para_ficha": definicion.get("apoyo", False),
            "encontrada": bool(tramos_utiles(tramos)),
            "confianza": confianza,
            "tramos": tramos,
            "otros_titulos_fuera_del_rango": fuera_de_rango[:MAXIMO_MENCIONES_PROPUESTAS],
            "paginas_con_menciones": paginas_mencion,
        }
        if definicion.get("opcional"):
            pass  # sección opcional (trámite): no se avisa si no existe
        elif not tramos:
            propuesta = paginas_mencion[:MAXIMO_MENCIONES_PROPUESTAS]
            texto_propuesta = (
                f"revisar las páginas donde se menciona: {propuesta}" if propuesta
                else "no hay menciones; ampliar la lectura a la parte considerativa completa"
            )
            avisos.append(f"No se ubicó la sección \"{definicion['nombre']}\". Propuesta: {texto_propuesta}.")
        elif confianza == "media":
            if any(t["metodo"] == "considerando_sin_que" for t in tramos):
                avisos.append(f"La sección \"{definicion['nombre']}\" se ubicó por un considerando sin \"Que\" recuperado por "
                              f"un hueco en la numeración (confianza media): confirmar leyendo la página.")
            else:
                avisos.append(f"La sección \"{definicion['nombre']}\" se ubicó por un subtítulo (por ejemplo \"9.1.\"), no por un título principal (confianza media).")
        elif confianza == "baja":
            avisos.append(f"La sección \"{definicion['nombre']}\" solo se ubicó por títulos sin número (confianza baja).")
        for tramo in tramos:
            if tramo.get("aislado"):
                avisos.append(f"La sección \"{definicion['nombre']}\" tiene un tramo aislado en la p. {tramo['pagina_inicio']} "
                              f"(confianza baja): no se suma a las páginas que leen las skills.")
        secciones[clave] = seccion

    if resuelvo:
        secciones["parte_resolutiva"] = {
            "nombre": "Parte resolutiva (RESUELVO)", "apoyo_para_ficha": False, "encontrada": True, "confianza": "alta",
            "tramos": [{"pagina_inicio": resuelvo, "pagina_fin": n_paginas, "titulo": "RESUELVO", "metodo": "resuelvo", "confianza": "alta"}],
            "otros_titulos_fuera_del_rango": [], "paginas_con_menciones": [resuelvo],
        }
    else:
        secciones["parte_resolutiva"] = {
            "nombre": "Parte resolutiva (RESUELVO)", "apoyo_para_ficha": False, "encontrada": False, "confianza": None,
            "tramos": [], "otros_titulos_fuera_del_rango": [], "paginas_con_menciones": [],
        }
        ultimas = list(range(max(1, n_paginas - 2), n_paginas + 1))
        avisos.append(f"No se ubicó la sección \"Parte resolutiva (RESUELVO)\". Propuesta: revisar las últimas páginas {ultimas}.")

    identificacion = list(range(1, min(PAGINAS_IDENTIFICACION, n_paginas) + 1))
    para_ficha, para_obligaciones = set(identificacion), set()
    for clave, seccion in secciones.items():
        limite = PAGINAS_FICHA_POR_SECCION.get(clave, PAGINAS_FICHA_OTRAS)
        for tramo in tramos_utiles(seccion):
            paginas_tramo = range(tramo["pagina_inicio"], tramo["pagina_fin"] + 1)
            para_ficha.update(list(paginas_tramo)[:limite])
            if clave in SECCIONES_DE_OBLIGACIONES:
                para_obligaciones.update(paginas_tramo)

    return {
        "archivo": datos_texto["archivo"],
        "n_paginas": n_paginas,
        "version_script": VERSION,
        "fecha_procesamiento": datetime.now().isoformat(timespec="seconds"),
        "identificacion": {"paginas": identificacion},
        "secciones": secciones,
        "paginas_indice_ignoradas": indice,
        "considerandos_detectados": [{"pagina": c["pagina"], "numero": c["numero"], "metodo": c["metodo"]} for c in considerandos],
        "considerandos_excluidos": [{"pagina": c["pagina"], "numero": c["numero"], "titulo": c["titulo"],
                                     "motivo": "cláusula estándar de seguimiento (no es sección temática ni de trámite)"}
                                    for c in excluidos],
        "paginas_para_ficha": sorted(para_ficha),
        "paginas_para_obligaciones": sorted(para_obligaciones),
        "avisos": avisos,
    }


# ---------------------------------------------------------- uso por consola

def cargar(ruta):
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".json":
        with open(ruta, encoding="utf-8") as archivo:
            return json.load(archivo)
    return leer_pdf.leer_pdf(ruta)


def imprimir(mapa):
    print(f"== {mapa['archivo']} ({mapa['n_paginas']} páginas)")
    print(f"   identificación: páginas {mapa['identificacion']['paginas']}")
    for clave, seccion in mapa["secciones"].items():
        if seccion["encontrada"]:
            rangos = ", ".join(
                (f"{t['pagina_inicio']}-{t['pagina_fin']}" if t["pagina_fin"] != t["pagina_inicio"] else f"{t['pagina_inicio']}")
                + (" (aislado)" if t.get("aislado") else "")
                for t in seccion["tramos"]
            )
            titulo = seccion["tramos"][0]["titulo"][:90]
            print(f"   {clave:26} págs. {rangos:18} [{seccion['confianza']}] «{titulo}»")
        else:
            print(f"   {clave:26} NO UBICADA")
    if mapa["paginas_indice_ignoradas"]:
        print(f"   páginas de índice ignoradas: {mapa['paginas_indice_ignoradas']}")
    print(f"   páginas para la ficha: {len(mapa['paginas_para_ficha'])} de {mapa['n_paginas']}; "
          f"para obligaciones (Etapa 4): {len(mapa['paginas_para_obligaciones'])}")
    for aviso in mapa["avisos"]:
        print(f"   aviso: {aviso}")


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Ubica las secciones principales de RCAs (sin IA).")
    parser.add_argument("rutas", nargs="+", help="JSON de salida/texto/ o PDF")
    parser.add_argument("--salida", default="salida", help="Carpeta de salida (por defecto: salida)")
    opciones = parser.parse_args(argumentos)
    errores = 0
    for ruta in opciones.rutas:
        try:
            mapa = localizar(cargar(ruta))
        except (leer_pdf.ErrorLectura, OSError, json.JSONDecodeError, KeyError) as error:
            errores += 1
            print(f"ERROR  {Path(ruta).name}: {error}", file=sys.stderr)
            continue
        destino = Path(opciones.salida) / "secciones" / f"{Path(mapa['archivo']).stem}.json"
        leer_pdf.guardar_json(mapa, destino)
        imprimir(mapa)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
