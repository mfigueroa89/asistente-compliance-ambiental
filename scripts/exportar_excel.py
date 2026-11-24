"""Genera el Excel de compliance a partir del manifiesto y de las fichas (sin IA).

Uso:
    python scripts/exportar_excel.py [--manifiesto manifiesto.csv] [--rcas rcas] [--salida salida]
                                     [--agregar-consulta salida/consultas/consulta_X.json ...]

Ejemplo con las RCAs públicas del repositorio:
    python scripts/exportar_excel.py --manifiesto ejemplos/manifiesto_ejemplo.csv --rcas ejemplos/rcas_publicas

Resultado: salida/compliance_ambiental.xlsx, con las hojas:
    Léeme        qué contiene el archivo, avisos, páginas no leídas y leyenda de colores;
    Índice UF    una fila por unidad fiscalizable;
    Resumen      una fila por RCA con sus datos clave;
    Fichas       una fila por dato: valor, página, cita y fuente, con marcas de calidad;
    Obligaciones vista compacta: una fila por obligación con lo esencial (ID visible, RCA, tipo, descripción, plazo...);
    Obligaciones detalle  todas las columnas (sección 8 de la especificación), sus temas y el estado de su cita;
    Menciones en texto  una fila por aparición de un término de config/temas.yaml en el texto completo;
    Consulta     (solo si hay consultas agregadas) historial de consultas, la más reciente arriba. Una consulta
                 entra solo si el usuario lo pidió: --agregar-consulta la marca ("en_excel": true en su JSON)
                 y queda en el historial desde entonces. Las demás quedan solo en salida/consultas/.
La hoja de verificación se agrega en una etapa posterior.

El Excel se regenera completo cada vez, desde los JSON de salida/ (nunca se edita a mano).
Si el archivo está abierto en Excel (o LibreOffice), no se puede reescribir: el script lo avisa, no cambia nada
y termina con código 3.
Si el PDF cambió desde que se fichó (su huella SHA-256 no coincide con la de la ficha),
la ficha se marca como DESACTUALIZADA.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import buscar_palabras
import ids_visibles
import leer_manifiesto
import registrar_revision
import validar_obligaciones
import verificar_citas
from leer_pdf import calcular_sha256

AVISO = "Herramienta de apoyo. Requiere revisión de un abogado."
NO_CONSTA = "No consta"
SIN_DATO = "—"
NOMBRE_EXCEL = "compliance_ambiental.xlsx"

GRUPOS = {
    "Identificación": ["numero_resolucion", "fecha_resolucion", "organo_calificador", "numero_expediente_o_codigo",
                       "tipo_instrumento", "decision", "reglamento_aplicable"],
    "Proyecto y titular": ["nombre_proyecto", "titular", "region", "provincia", "comuna", "tipologia", "descripcion_breve",
                           "monto_inversion", "vida_util", "fases", "superficie_o_dimensiones"],
    "Evaluación ambiental": ["componentes_ambientales_relevantes", "efectos_articulo_11", "participacion_ciudadana",
                             "pueblos_indigenas", "permisos_ambientales_sectoriales", "areas_protegidas_o_sensibles"],
    "Medidas y seguimiento": ["hay_medidas_mitigacion", "hay_medidas_reparacion", "hay_medidas_compensacion",
                              "hay_plan_seguimiento", "hay_condiciones_exigencias", "hay_compromisos_voluntarios",
                              "hay_plan_contingencias"],
}
GRUPO_DE = {campo: grupo for grupo, campos in GRUPOS.items() for campo in campos}

ETIQUETAS = {
    "numero_resolucion": "N° de resolución", "fecha_resolucion": "Fecha de la resolución",
    "organo_calificador": "Órgano calificador", "numero_expediente_o_codigo": "Expediente o código",
    "tipo_instrumento": "Tipo de instrumento", "decision": "Decisión", "reglamento_aplicable": "Reglamento aplicable",
    "nombre_proyecto": "Nombre del proyecto", "titular": "Titular", "region": "Región", "provincia": "Provincia",
    "comuna": "Comuna", "tipologia": "Tipología", "descripcion_breve": "Descripción breve",
    "monto_inversion": "Monto de inversión", "vida_util": "Vida útil", "fases": "Fases",
    "superficie_o_dimensiones": "Superficie o dimensiones",
    "componentes_ambientales_relevantes": "Componentes ambientales relevantes",
    "efectos_articulo_11": "Efectos del artículo 11", "participacion_ciudadana": "Participación ciudadana",
    "pueblos_indigenas": "Pueblos indígenas", "permisos_ambientales_sectoriales": "Permisos ambientales sectoriales",
    "areas_protegidas_o_sensibles": "Áreas protegidas o sensibles",
    "hay_medidas_mitigacion": "¿Medidas de mitigación?", "hay_medidas_reparacion": "¿Medidas de reparación?",
    "hay_medidas_compensacion": "¿Medidas de compensación?", "hay_plan_seguimiento": "¿Plan de seguimiento?",
    "hay_condiciones_exigencias": "¿Condiciones o exigencias?", "hay_compromisos_voluntarios": "¿Compromisos voluntarios?",
    "hay_plan_contingencias": "¿Plan de contingencias?",
}

# Colores (relleno de celda).
VERDE, AMARILLO, ROJO, AZUL, GRIS = "E2EFDA", "FFF2CC", "F8CBAD", "DDEBF7", "EDEDED"
COLOR_ENCABEZADO = "1F4E78"
COLOR_VERIFICACION = {
    "confirmada": VERDE, "aproximada": AMARILLO, "encontrada en otra página": AMARILLO,
    "no encontrada en esa página": ROJO, "leída en imagen": AZUL,
}
COLOR_FUENTE = {"imagen": AZUL, "ocr_previo": AMARILLO}


# --------------------------------------------------------------------------- carga de datos

def cargar_json(ruta):
    ruta = Path(ruta)
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def cargar_rca(archivo, carpeta_rcas, carpeta_salida):
    """Reúne ficha, texto, verificación de citas y estado (al día, desactualizada, sin ficha, sin PDF)."""
    stem = Path(archivo).stem
    ficha = cargar_json(Path(carpeta_salida) / "fichas" / f"{stem}.json")
    texto = cargar_json(Path(carpeta_salida) / "texto" / f"{stem}.json")
    pdf = Path(carpeta_rcas) / archivo
    obligaciones = cargar_json(Path(carpeta_salida) / "obligaciones" / f"{stem}.json")
    rca = {"archivo": archivo, "ficha": ficha, "texto": texto, "verificacion": {}, "estado": "al día",
           "obligaciones": obligaciones, "verificacion_obligaciones": {}, "estado_obligaciones": "sin extraer"}
    if not pdf.exists():
        rca["estado"] = "sin PDF en la carpeta"
    elif ficha is None:
        rca["estado"] = "sin ficha (falta fichar)"
    elif ficha.get("sha256") != calcular_sha256(pdf):
        rca["estado"] = "DESACTUALIZADA (el PDF cambió desde que se fichó)"
    if ficha is not None and texto is not None:
        informe = verificar_citas.verificar(ficha, texto)
        rca["verificacion"] = {cita["campo"]: cita["estado"] for cita in informe["citas"]}
    if obligaciones is not None:
        if pdf.exists() and obligaciones.get("sha256") != calcular_sha256(pdf):
            rca["estado_obligaciones"] = "DESACTUALIZADAS (el PDF cambió desde la extracción)"
        else:
            rca["estado_obligaciones"] = "al día"
        if texto is not None:
            # Se verifican la cita principal y las adicionales; cada obligación queda con el peor estado de sus citas.
            planas = validar_obligaciones.citas_planas(obligaciones.get("obligaciones", []))
            informe = verificar_citas.verificar({"citas": planas}, texto)
            orden = ["confirmada", "leída en imagen", "aproximada", "encontrada en otra página", "no encontrada en esa página"]
            for cita in informe["citas"]:
                ident = planas[int(cita["campo"].split("[")[1].split("]")[0])]["id"]
                actual = rca["verificacion_obligaciones"].get(ident, "confirmada")
                rca["verificacion_obligaciones"][ident] = max(actual, cita["estado"], key=orden.index)
    return rca


def dato_de(ficha, campo):
    return (ficha or {}).get("campos", {}).get(campo)


def valor_simple(ficha, campo):
    """Valor de un campo no lista; "No consta" si no hay ficha o dato."""
    dato = dato_de(ficha, campo)
    if isinstance(dato, dict) and dato.get("valor") not in (None, ""):
        return dato["valor"]
    return NO_CONSTA


def valor_lista(ficha, campo):
    datos = dato_de(ficha, campo)
    if not datos:
        return NO_CONSTA
    return "; ".join(str(d.get("valor")) for d in datos)


def como_fecha(valor):
    try:
        return datetime.date.fromisoformat(valor)
    except (TypeError, ValueError):
        return valor


# --------------------------------------------------------------------------- marcas de calidad

def calidad(dato, pagina_info, revisadas):
    """Marca de calidad legible del dato según su fuente."""
    fuente = dato.get("fuente")
    if dato.get("valor") == NO_CONSTA:
        return SIN_DATO
    if fuente == "texto":
        return "Texto digital"
    if fuente == "imagen":
        return "Leído en la imagen de la página"
    if fuente == "ocr_previo":
        if dato.get("correccion_ocr"):
            return f"OCR corregido según la imagen: {dato['correccion_ocr']}"
        if dato.get("pagina_pdf") in revisadas:
            return "OCR confirmado en la imagen"
        return "Solo OCR (imagen no revisada)"
    return fuente or SIN_DATO


def complemento(dato):
    """Datos complementarios del elemento (equivalencia legal, categoría, rango del localizador)."""
    partes = []
    equivalente = dato.get("letra_equivalente")
    if isinstance(equivalente, dict) and equivalente.get("valor"):
        partes.append(f"Equivalencia legal (no es dato de la RCA): {equivalente['valor']}")
    if dato.get("categoria"):
        partes.append(f"Categoría: {dato['categoria']}")
    if dato.get("rango_localizador"):
        partes.append(f"Páginas que ubicó el localizador: {dato['rango_localizador']}")
    return " | ".join(partes) or SIN_DATO


def filas_de_ficha(rca):
    """Una fila por dato de la ficha (y por elemento en las listas), más las filas de control."""
    ficha = rca["ficha"]
    if ficha is None:
        return [{"grupo": SIN_DATO, "campo": SIN_DATO, "dato": SIN_DATO, "elemento": SIN_DATO,
                 "valor": f"{NO_CONSTA}: {rca['estado']}", "pagina": SIN_DATO, "cita": SIN_DATO,
                 "fuente": SIN_DATO, "calidad": SIN_DATO, "verificacion": SIN_DATO, "complemento": SIN_DATO}]
    paginas = {p["numero_pdf"]: p for p in (rca["texto"] or {}).get("paginas", [])}
    revisadas = set(ficha.get("control", {}).get("paginas_revisadas_en_imagen", []))
    filas = []
    for campo, contenido in ficha.get("campos", {}).items():
        base = {"grupo": GRUPO_DE.get(campo, "Otros"), "campo": campo, "dato": ETIQUETAS.get(campo, campo)}
        elementos = contenido if isinstance(contenido, list) else [contenido]
        if isinstance(contenido, list) and not contenido:
            filas.append({**base, "elemento": SIN_DATO, "valor": f"{NO_CONSTA} (lista vacía)", "pagina": SIN_DATO,
                          "cita": SIN_DATO, "fuente": SIN_DATO, "calidad": SIN_DATO, "verificacion": SIN_DATO,
                          "complemento": SIN_DATO})
            continue
        for indice, dato in enumerate(elementos):
            ruta = f"campos.{campo}[{indice}]" if isinstance(contenido, list) else f"campos.{campo}"
            no_consta = dato.get("valor") == NO_CONSTA
            valor = dato.get("valor")
            if campo == "fecha_resolucion" and not no_consta:
                valor = como_fecha(valor)
            filas.append({
                **base,
                "elemento": indice + 1 if isinstance(contenido, list) else SIN_DATO,
                "valor": valor if valor not in (None, "") else NO_CONSTA,
                "pagina": dato.get("pagina_pdf") if dato.get("pagina_pdf") is not None else SIN_DATO,
                "cita": dato.get("cita_textual") or SIN_DATO,
                "fuente": dato.get("fuente") or SIN_DATO,
                "calidad": calidad(dato, paginas.get(dato.get("pagina_pdf")), revisadas),
                "verificacion": SIN_DATO if no_consta else rca["verificacion"].get(ruta, "no verificada"),
                "complemento": complemento(dato),
            })
    control = ficha.get("control", {})
    for no_leida in control.get("paginas_no_leidas", []):
        filas.append({"grupo": "Control", "campo": "paginas_no_leidas", "dato": "Página no leída",
                      "elemento": SIN_DATO, "valor": f"{no_leida['seccion']}: {no_leida['motivo']}",
                      "pagina": no_leida["pagina"], "cita": SIN_DATO, "fuente": SIN_DATO, "calidad": SIN_DATO,
                      "verificacion": SIN_DATO, "complemento": SIN_DATO})
    for indice, observacion in enumerate(control.get("observaciones_generales", []), start=1):
        filas.append({"grupo": "Control", "campo": "observaciones_generales", "dato": "Observación general",
                      "elemento": indice, "valor": observacion, "pagina": SIN_DATO, "cita": SIN_DATO,
                      "fuente": SIN_DATO, "calidad": SIN_DATO, "verificacion": SIN_DATO, "complemento": SIN_DATO})
    return filas


def alertas_de(rca):
    """Citas que no quedaron confirmadas por código (incluye las leídas en imagen) y páginas no leídas."""
    citas = sum(1 for estado in rca["verificacion"].values() if estado != "confirmada")
    no_leidas = len((rca["ficha"] or {}).get("control", {}).get("paginas_no_leidas", []))
    return citas, no_leidas


# --------------------------------------------------------------------------- formato

def hoja_tabla(libro, titulo, encabezados, filas, anchos):
    """Crea una hoja con encabezado en negrita, primera fila fija, filtros y ajuste de texto."""
    hoja = libro.create_sheet(titulo)
    hoja.append(encabezados)
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=COLOR_ENCABEZADO)
        celda.alignment = Alignment(wrap_text=True, vertical="center")
    for fila in filas:
        hoja.append([SIN_DATO if v in (None, "") else v for v in fila])
    for indice, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    for fila in hoja.iter_rows(min_row=2):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")
            if isinstance(celda.value, str) and celda.value.startswith(NO_CONSTA):
                celda.font = Font(italic=True, color="7F7F7F")
            if isinstance(celda.value, datetime.date):
                celda.number_format = "DD-MM-YYYY"
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions
    return hoja


def pintar(hoja, columna, colores):
    """Pinta las celdas de una columna según su valor (o el comienzo del valor)."""
    indice = [c.value for c in hoja[1]].index(columna) + 1
    for fila in hoja.iter_rows(min_row=2, min_col=indice, max_col=indice):
        celda = fila[0]
        for inicio, color in colores.items():
            if isinstance(celda.value, str) and celda.value.startswith(inicio):
                celda.fill = PatternFill("solid", fgColor=color)
                break



# --------------------------------------------------------------------------- revisión humana

COLUMNAS_REVISION = ["revision_estado", "revision_fecha", "revision_por", "revision_comentario"]
COLOR_REVISION = {"confirmada": VERDE, "corregida": AMARILLO, "descartada": GRIS}


def valores_revision(fila):
    """Las cuatro columnas de revisión humana de una obligación (pendiente si no se ha revisado)."""
    if not fila:
        return [registrar_revision.PENDIENTE, SIN_DATO, SIN_DATO, SIN_DATO]
    return [fila["estado"], como_fecha(fila["fecha_revision"]) or fila["fecha_revision"], fila["revisado_por"],
            fila.get("comentario") or SIN_DATO]


def rca_revision(rca):
    """Revisiones vigentes de las obligaciones que existen en la RCA (ignora IDs que ya no existen)."""
    existentes = {o["id_obligacion"] for o in (rca["obligaciones"] or {}).get("obligaciones", [])}
    return {i: f for i, f in (rca.get("revision") or {}).items() if i in existentes}


# --------------------------------------------------------------------------- hojas

def hoja_leeme(libro, manifiesto, rcas, generado):
    hoja = libro.active
    hoja.title = "Léeme"
    unidades = {f["unidad_fiscalizable"] for f in manifiesto["filas"]}
    lineas = [
        ("Asistente de Compliance Ambiental: fichas de RCA por unidad fiscalizable", None),
        (AVISO, "aviso"),
        ("", None),
        ("Generado", generado.strftime("%d-%m-%Y %H:%M")),
        ("RCAs en el manifiesto", len(rcas)),
        ("RCAs con ficha al día", sum(1 for r in rcas.values() if r["estado"] == "al día")),
        ("Unidades fiscalizables", len(unidades)),
        ("Separador del manifiesto", manifiesto["separador"]),
        ("", None),
        ("Hojas", None),
        ("Índice UF", "Una fila por unidad fiscalizable (concepto de SNIFA, SMA), con sus RCAs y alertas. La columna "
                      "nota_uf trae la nota del manifiesto (por ejemplo, la fecha en que se buscó la unidad en SNIFA). "
                      "filas_revisadas y filas_confirmadas cuentan las obligaciones con revisión humana registrada."),
        ("Resumen", "Una fila por RCA con sus datos clave y el enlace a su expediente en el e-SEIA. Si una RCA pertenece a "
                    "varias unidades, se nombran todas."),
        ("Fichas", "Una fila por dato: valor, página del PDF, cita textual y fuente. Si una RCA pertenece a varias "
                   "unidades, sus filas se repiten en cada unidad para que el filtro por unidad muestre la ficha completa."),
        ("Obligaciones", "Vista compacta para leer y filtrar: una fila por obligación con lo esencial (ID visible, unidad "
                         "fiscalizable, RCA, tipo, descripción, plazo o frecuencia, responsable, página y estado de la revisión "
                         "humana). El respaldo de cada fila (cita textual, temas, verificación, calidad del OCR y demás campos) "
                         "está en Obligaciones detalle, con el mismo ID visible en la primera columna."),
        ("Obligaciones detalle", "Una fila por obligación: tipo, fase, descripción, temas, plazo, autoridad, página, cita, confianza, "
                         "calidad (en páginas con OCR: confirmado en la imagen o solo OCR) y estado de la cita. "
                         "temas_literales la calcula el código: temas de config/temas.yaml cuyos términos están en las citas "
                         "(texto del PDF). temas_relacionados es interpretación del asistente, siempre marcada [revisar], con "
                         "las palabras del PDF que la motivan y su página; las marcadas (dudosa) requieren especial atención. "
                         "Las obligaciones que aparecen en dos partes de la RCA no se fusionan: se marcan como posible duplicado, "
                         "y la columna duplicado_de indica la obligación representante (filtrar por \"—\" deja las obligaciones "
                         "distintas). Las filas agrupadas (contingencias) llevan citas adicionales y su rango de páginas. "
                         "id_visible es el ID con el prefijo de la RCA (columna prefijo_id del manifiesto; por ejemplo "
                         "ARQ-024); id_obligacion es el ID interno, que no cambia. Las columnas revision_* registran la "
                         "revisión de un abogado: pendiente, confirmada (verde), corregida (amarillo) o descartada (gris), "
                         "con fecha, quién y comentario; se cargan con registrar_revision.py desde una planilla llenada."),
        ("Menciones en texto", "Una fila por aparición de un término de config/temas.yaml en el texto completo de la RCA "
                               "(búsqueda exacta, sin IA). recogido_en_obligacion indica si la aparición está dentro de la cita "
                               "de una obligación; \"no\" es una mención sin obligación (por ejemplo, en la evaluación). Las "
                               "páginas escaneadas sin texto se listan como \"no revisada\"."),
        ("Consulta", "Aparece cuando se ha pedido agregar alguna consulta (skill consultar-obligaciones). Es el historial "
                     "de las consultas que el usuario pidió agregar al Excel (las demás quedan solo en salida/consultas/), "
                     "la más reciente arriba: una fila por resultado, con la consulta, su "
                     "fecha y hora, el filtro (unidad fiscalizable o RCAs), el alcance y la categoría. Coincidencia literal "
                     "(verde): el término está en una cita de la obligación. Relación temática (amarillo): interpretación del "
                     "asistente, siempre a revisar; \"(propuesta en esta consulta)\" indica que se propuso para un término "
                     "libre y se comprobó por código que sus palabras están en la página. Mención sin obligación (gris): el "
                     "término está en la RCA fuera de toda obligación. \"No hay resultados\" (rojo) va siempre con su alcance. "
                     "Cada consulta se muestra tal como se hizo, con los datos de ese momento: no se recalcula."),
        ("", None),
        ("Cómo leer las columnas", None),
        ("No consta", "El dato no aparece en el documento. Nunca se completa de memoria."),
        ("—", "No aplica (por ejemplo, un dato \"No consta\" no tiene página ni cita)."),
        ("Fuente", "texto = texto digital; imagen = leído en la imagen de la página; ocr_previo = texto de un OCR anterior."),
        ("Calidad", "Para datos con OCR: confirmado en la imagen, corregido según la imagen (se indica qué) o solo OCR."),
        ("Verificación", "Comprobación por código de que la cita está en la página indicada."),
        ("Equivalencia legal", "La letra del artículo 11 y su artículo del Reglamento SEIA: conocimiento jurídico "
                               "agregado desde config/, no un dato de la RCA."),
        ("", None),
        ("Colores", None),
        ("Verde", "Cita confirmada en su página."),
        ("Amarillo", "Cita aproximada o en otra página; o dato con fuente OCR (confirmar contra el PDF)."),
        ("Rojo", "Cita no encontrada; o ficha desactualizada; o página no leída."),
        ("Azul", "Dato leído en la imagen de la página (confirmar visualmente)."),
        ("Confianza", "En Obligaciones: alta (verde) si el texto impone el deber de forma expresa; media (amarillo); baja (rojo) si es dudoso."),
    ]
    for etiqueta, valor in lineas:
        hoja.append([etiqueta, valor if valor != "aviso" else None])
    hoja["A1"].font = Font(bold=True, size=14)
    hoja["A2"].font = Font(bold=True, color="C00000")
    for fila in hoja.iter_rows():
        if fila[0].value in ("Hojas", "Cómo leer las columnas", "Colores"):
            fila[0].font = Font(bold=True)
    for etiqueta, color in (("Verde", VERDE), ("Amarillo", AMARILLO), ("Rojo", ROJO), ("Azul", AZUL)):
        for fila in hoja.iter_rows():
            if fila[0].value == etiqueta:
                fila[0].fill = PatternFill("solid", fgColor=color)

    # Avisos del manifiesto y del estado de las fichas.
    hoja.append([])
    hoja.append(["Avisos"])
    hoja.cell(hoja.max_row, 1).font = Font(bold=True)
    avisos = [a for a in manifiesto["avisos"] if not a.startswith("Separador")]
    avisos += [f"{r['archivo']}: {r['estado']}." for r in rcas.values() if r["estado"] != "al día"]
    for aviso in avisos or ["Sin avisos."]:
        hoja.append(["", aviso])
        if "DESACTUALIZADA" in aviso or "sin ficha" in aviso:
            hoja.cell(hoja.max_row, 2).fill = PatternFill("solid", fgColor=ROJO)

    # Páginas no leídas (hasta que exista la hoja de verificación).
    hoja.append([])
    hoja.append(["Páginas no leídas", "Mientras no exista la hoja Verificación, las páginas no leídas se informan aquí."])
    hoja.cell(hoja.max_row, 1).font = Font(bold=True)
    hay = False
    for rca in rcas.values():
        for no_leida in (rca["ficha"] or {}).get("control", {}).get("paginas_no_leidas", []):
            hay = True
            hoja.append(["", f"{rca['archivo']}, p. {no_leida['pagina']} ({no_leida['seccion']}): {no_leida['motivo']}"])
            hoja.cell(hoja.max_row, 2).fill = PatternFill("solid", fgColor=ROJO)
    if not hay:
        hoja.append(["", "Ninguna."])
    hoja.column_dimensions["A"].width = 30
    hoja.column_dimensions["B"].width = 110
    for fila in hoja.iter_rows():
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")


def grupos_de_duplicados(obligaciones):
    """{ID: ID representante} uniendo las cadenas de posible_duplicado; el representante es el ID menor."""
    padre = {o["id_obligacion"]: o["id_obligacion"] for o in obligaciones}

    def raiz(ident):
        while padre[ident] != ident:
            padre[ident] = padre[padre[ident]]
            ident = padre[ident]
        return ident

    for obligacion in obligaciones:
        for otro in obligacion.get("posible_duplicado", []) or []:
            if otro in padre:
                a, b = sorted((raiz(obligacion["id_obligacion"]), raiz(otro)))
                padre[b] = a
    return {ident: raiz(ident) for ident in padre}


def conteo_obligaciones(rca):
    """(filas totales, obligaciones distintas) de una RCA; los posibles duplicados cuentan una vez."""
    lista = rca["obligaciones"].get("obligaciones", [])
    return len(lista), len(set(grupos_de_duplicados(lista).values()))


def hoja_indice(libro, manifiesto, rcas):
    por_uf = {}
    for fila in manifiesto["filas"]:
        por_uf.setdefault(fila["unidad_fiscalizable"], []).append(fila)
    filas = []
    for unidad, filas_uf in sorted(por_uf.items(), key=lambda x: (x[0] == leer_manifiesto.SIN_UF, x[0])):
        archivos = [f["archivo"] for f in filas_uf]
        titulares = sorted({valor_simple(rcas[a]["ficha"], "titular") for a in archivos})
        citas = sum(alertas_de(rcas[a])[0] for a in archivos)
        no_leidas = sum(alertas_de(rcas[a])[1] for a in archivos)
        estados = sorted({rcas[a]["estado"] for a in archivos})
        con_obligaciones = [a for a in archivos if rcas[a]["obligaciones"] is not None]
        totales = sum(conteo_obligaciones(rcas[a])[0] for a in con_obligaciones) if con_obligaciones else "Sin extraer"
        distintas = sum(conteo_obligaciones(rcas[a])[1] for a in con_obligaciones) if con_obligaciones else "Sin extraer"
        if con_obligaciones and len(con_obligaciones) < len(archivos):
            totales = f"{totales} (faltan RCAs por extraer)"
            distintas = f"{distintas} (faltan RCAs por extraer)"
        revisadas = [f for a in con_obligaciones for i, f in rca_revision(rcas[a]).items()]
        filas_revisadas = len(revisadas) if con_obligaciones else "Sin extraer"
        filas_confirmadas = sum(1 for f in revisadas if f["estado"] == "confirmada") if con_obligaciones else "Sin extraer"
        citas += sum(1 for a in con_obligaciones for e in rcas[a]["verificacion_obligaciones"].values() if e != "confirmada")
        primero = filas_uf[0]
        notas = [(f["archivo"], f["nota_uf"]) for f in filas_uf if f.get("nota_uf")]
        nota_uf = notas[0][1] if len(notas) == 1 and len(archivos) == 1 else "\n".join(f"{a}: {n}" for a, n in notas)
        filas.append([
            unidad, primero["id_uf_snifa"] or SIN_DATO, primero["enlace_uf_snifa"] or SIN_DATO,
            "; ".join(sorted({f["proyecto"] for f in filas_uf})), "; ".join(titulares), len(archivos),
            "\n".join(archivos), totales, distintas, filas_revisadas, filas_confirmadas, citas, no_leidas,
            "; ".join(estados), nota_uf,
        ])
    hoja = hoja_tabla(libro, "Índice UF", [
        "unidad_fiscalizable", "id_uf_snifa", "enlace_uf_snifa", "proyectos", "titular (según ficha)",
        "cantidad_rcas", "archivos", "obligaciones_filas_totales", "obligaciones_distintas", "filas_revisadas",
        "filas_confirmadas", "citas_por_revisar",
        "paginas_no_leidas", "estado_fichas", "nota_uf",
    ], filas, [38, 12, 34, 40, 28, 10, 40, 14, 14, 12, 12, 12, 12, 22, 40])
    enlazar(hoja, "enlace_uf_snifa")
    pintar(hoja, "estado_fichas", {"DESACTUALIZADA": ROJO, "sin ": ROJO})


def enlazar(hoja, columna):
    """Convierte en hipervínculo cada celda de la columna que sea un enlace web."""
    indice = [c.value for c in hoja[1]].index(columna) + 1
    for fila in hoja.iter_rows(min_row=2, min_col=indice, max_col=indice):
        if isinstance(fila[0].value, str) and fila[0].value.lower().startswith(("http://", "https://")):
            fila[0].hyperlink = fila[0].value
            fila[0].font = Font(color="0563C1", underline="single")


def hoja_resumen(libro, manifiesto, rcas):
    unidades = {}
    for fila in manifiesto["filas"]:
        unidades.setdefault(fila["archivo"], []).append(fila["unidad_fiscalizable"])
    proyectos = {f["archivo"]: f["proyecto"] for f in manifiesto["filas"]}
    enlaces = leer_manifiesto.enlaces_eseia(manifiesto["filas"])
    filas = []
    for archivo, rca in rcas.items():
        ficha = rca["ficha"]
        filas.append([
            "; ".join(unidades[archivo]), proyectos[archivo], archivo, enlaces.get(archivo),
            valor_simple(ficha, "numero_resolucion"), como_fecha(valor_simple(ficha, "fecha_resolucion")),
            valor_simple(ficha, "tipo_instrumento"), valor_simple(ficha, "decision"), valor_simple(ficha, "titular"),
            valor_lista(ficha, "region"),
            valor_simple(ficha, "hay_medidas_mitigacion"), valor_simple(ficha, "hay_medidas_reparacion"),
            valor_simple(ficha, "hay_medidas_compensacion"), valor_simple(ficha, "hay_plan_seguimiento"),
            valor_simple(ficha, "hay_compromisos_voluntarios"), valor_simple(ficha, "hay_plan_contingencias"),
            rca["estado"],
        ])
    hoja = hoja_tabla(libro, "Resumen", [
        "unidades_fiscalizables", "proyecto", "archivo", "enlace_eseia", "numero_resolucion", "fecha_resolucion", "tipo",
        "decision", "titular", "region", "medidas_mitigacion", "medidas_reparacion", "medidas_compensacion",
        "plan_seguimiento", "compromisos_voluntarios", "plan_contingencias", "estado_ficha",
    ], filas, [34, 34, 30, 40, 16, 13, 8, 12, 26, 22, 22, 14, 14, 14, 26, 14, 18])
    enlazar(hoja, "enlace_eseia")
    pintar(hoja, "estado_ficha", {"DESACTUALIZADA": ROJO, "sin ": ROJO})


def texto_relacion(relacion):
    """Una relación temática legible: «tema [revisar] (dudosa): justificación (p. N)»."""
    dudosa = " (dudosa)" if relacion.get("dudosa") else ""
    return (f"{relacion.get('tema')} [{relacion.get('estado', 'revisar')}]{dudosa}: {relacion.get('justificacion')} "
            f"(p. {relacion.get('pagina_pdf')})")


COLUMNAS_COMPACTAS = ["id_visible", "unidad_fiscalizable", "rca", "tipo", "descripcion", "plazo_o_frecuencia", "responsable",
                      "pagina_pdf", "revision_estado"]


def nombre_rca(proyecto, numero, ficha, archivo):
    """"Proyecto Arqueros, RCA N° 151 (2013)": proyecto del manifiesto, N° y año de la resolución según la ficha."""
    if not numero or str(numero).startswith(NO_CONSTA):
        return f"{proyecto} ({archivo})"
    fecha = str(valor_simple(ficha, "fecha_resolucion") or "")
    anio = f" ({fecha[:4]})" if fecha[:4].isdigit() else ""
    return f"{proyecto}, RCA N° {numero}{anio}"


def hoja_obligaciones(libro, manifiesto, rcas, temas):
    """Dos hojas con las mismas filas: una por obligación (y por unidad fiscalizable, si la RCA pertenece a varias).
    "Obligaciones" es la vista compacta (lo esencial); "Obligaciones detalle" trae todas las columnas.
    Ambas empiezan por id_visible, para cruzarlas."""
    columnas = ["id_visible", "id_obligacion", "tipo", "componente_ambiental", "fase", "descripcion", "temas_literales", "temas_relacionados",
                "plazo_o_frecuencia", "hito_o_gatillo",
                "responsable", "autoridad_destinataria", "medio_de_verificacion", "parametro_o_indicador", "ubicacion_en_documento",
                "pagina_pdf", "pagina_impresa", "cita_textual", "citas_adicionales", "paginas_respaldo", "fuente", "calidad", "confianza",
                "posible_duplicado", "duplicado_de", "notas"]
    filas, compactas = [], []
    for fila_manifiesto in manifiesto["filas"]:
        rca = rcas[fila_manifiesto["archivo"]]
        numero = valor_simple(rca["ficha"], "numero_resolucion")
        base = [fila_manifiesto["unidad_fiscalizable"], fila_manifiesto["proyecto"], rca["archivo"], numero]
        rca_texto = nombre_rca(fila_manifiesto["proyecto"], numero, rca["ficha"], rca["archivo"])
        if rca["obligaciones"] is None:
            compactas.append([SIN_DATO, fila_manifiesto["unidad_fiscalizable"], rca_texto, SIN_DATO,
                              f"{NO_CONSTA}: obligaciones sin extraer", SIN_DATO, SIN_DATO, SIN_DATO, SIN_DATO])
            filas.append(base + [SIN_DATO] * 5 + [f"{NO_CONSTA}: obligaciones sin extraer"]
                         + [SIN_DATO] * (len(columnas) - 6) + [SIN_DATO] + [SIN_DATO] * len(COLUMNAS_REVISION))
            continue
        lista = rca["obligaciones"].get("obligaciones", [])
        representante = grupos_de_duplicados(lista)
        revisadas = set((rca["obligaciones"].get("control") or {}).get("paginas_revisadas_en_imagen", []))
        for obligacion in lista:
            valores = []
            for columna in columnas:
                valor = obligacion.get(columna)
                visible = lambda ident: ids_visibles.id_visible(rca["archivo"], ident, rca["prefijos"])
                if columna == "id_visible":
                    valor = visible(obligacion["id_obligacion"])
                elif columna == "posible_duplicado":
                    valor = [visible(i) for i in valor or []]
                elif columna == "duplicado_de":
                    # Vacío ("—") en la obligación representante; filtrar por "—" deja las obligaciones distintas.
                    ident = obligacion["id_obligacion"]
                    valor = visible(representante[ident]) if representante[ident] != ident else SIN_DATO
                elif columna == "temas_literales":
                    # Calculado por código: temas cuyos términos aparecen en las citas (texto del PDF).
                    valor = ", ".join(buscar_palabras.temas_literales(obligacion, temas)) or SIN_DATO
                elif columna == "temas_relacionados":
                    valor = "\n".join(texto_relacion(r) for r in obligacion.get("temas_relacionados") or []) or SIN_DATO
                elif columna == "calidad":
                    # Misma marca que en Fichas: "OCR confirmado en la imagen", "Solo OCR (imagen no revisada)", etc.
                    valor = calidad(obligacion, None, revisadas)
                elif columna == "citas_adicionales":
                    valor = "\n".join(f"p. {c.get('pagina_pdf')}: «{c.get('cita_textual')}»" for c in valor or [])
                if isinstance(valor, list):
                    valor = ", ".join(valor) if valor else SIN_DATO
                valores.append(valor if valor not in (None, "") else SIN_DATO)
            estado = rca["verificacion_obligaciones"].get(obligacion.get("id_obligacion"), "no verificada")
            revision = valores_revision(rca["revision"].get(obligacion["id_obligacion"]))
            filas.append(base + valores + [estado] + revision)
            dato = dict(zip(columnas, valores))
            compactas.append([dato["id_visible"], fila_manifiesto["unidad_fiscalizable"], rca_texto, dato["tipo"], dato["descripcion"],
                              dato["plazo_o_frecuencia"], dato["responsable"], dato["pagina_pdf"], revision[0]])
    compacta = hoja_tabla(libro, "Obligaciones", COLUMNAS_COMPACTAS, compactas, [11, 30, 30, 24, 70, 30, 18, 8, 13])
    compacta.freeze_panes = "B2"  # títulos y la columna del ID quedan fijos
    pintar(compacta, "revision_estado", COLOR_REVISION)
    # La hoja de detalle empieza por id_visible (para cruzarla con la compacta) y sigue con UF, proyecto, archivo y N°.
    filas = [[f[4]] + f[:4] + f[5:] for f in filas]
    hoja = hoja_tabla(libro, "Obligaciones detalle", ["id_visible", "unidad_fiscalizable", "proyecto", "archivo", "numero_resolucion"]
                      + columnas[1:] + ["estado_verificacion"] + COLUMNAS_REVISION, filas,
                      [10, 28, 24, 24, 14, 10, 22, 18, 14, 50, 22, 50, 22, 22, 16, 22, 26, 22, 28, 9, 9, 50, 50, 10, 10, 24, 10, 16, 12, 40, 16, 14, 12, 14, 40])
    hoja.freeze_panes = "B2"
    pintar(hoja, "confianza", {"alta": VERDE, "media": AMARILLO, "baja": ROJO})
    pintar(hoja, "estado_verificacion", COLOR_VERIFICACION)
    pintar(hoja, "fuente", COLOR_FUENTE)
    pintar(hoja, "calidad", {"OCR corregido": AMARILLO, "Solo OCR": AMARILLO, "OCR confirmado": VERDE, "Leído en la imagen": AZUL})
    ids_con_prefijo = {f"{p}-": AMARILLO for p in set().union(*(r.get("prefijos", {}).values() for r in rcas.values()))}
    pintar(hoja, "posible_duplicado", {"OBL-": AMARILLO, **ids_con_prefijo})
    pintar(hoja, "duplicado_de", {"OBL-": AMARILLO, **ids_con_prefijo})
    pintar(hoja, "revision_estado", COLOR_REVISION)
    pintar(hoja, "temas_relacionados", {tema: AMARILLO for tema in temas})


def hoja_menciones(libro, manifiesto, rcas, temas):
    """Una fila por aparición de un término de config/temas.yaml en el texto completo de la RCA (búsqueda exacta),
    indicando si está dentro de la cita de alguna obligación. Las páginas sin texto se listan como no revisadas."""
    columnas = ["unidad_fiscalizable", "proyecto", "archivo", "termino", "encontrado", "tema", "pagina_pdf",
                "pagina_impresa", "contexto", "recogido_en_obligacion", "obligaciones_en_la_pagina", "origen_texto"]
    filas = []
    for fila_manifiesto in manifiesto["filas"]:
        rca = rcas[fila_manifiesto["archivo"]]
        base = [fila_manifiesto["unidad_fiscalizable"], fila_manifiesto["proyecto"], rca["archivo"]]
        if rca["texto"] is None:
            filas.append(base + [SIN_DATO, SIN_DATO, SIN_DATO, SIN_DATO, SIN_DATO,
                                 f"{NO_CONSTA}: falta el texto de la RCA (leer_pdf.py)", SIN_DATO, SIN_DATO, SIN_DATO])
            continue
        obligaciones = (rca["obligaciones"] or {}).get("obligaciones", [])
        for h in buscar_palabras.buscar_en_rca(rca["texto"], obligaciones, temas):
            filas.append(base + [h["termino"], h["encontrado"], h["tema"], h["pagina_pdf"], h["pagina_impresa"] or SIN_DATO,
                                 h["contexto"], ", ".join(h["recogido_en"]) or "no",
                                 ", ".join(h["obligaciones_en_la_pagina"]) or "ninguna", h["origen_texto"]])
        no_leidas = {p.get("pagina"): p for p in ((rca["obligaciones"] or {}).get("control") or {}).get("paginas_no_leidas") or []}
        for pagina in rca["texto"]["paginas"]:
            motivo = None
            if buscar_palabras.pagina_sin_texto(pagina):
                motivo = "Página sin texto (escaneada): no se pudo buscar en ella"
            elif pagina["numero_pdf"] in no_leidas:
                motivo = f"Página no leída ({no_leidas[pagina['numero_pdf']].get('motivo')}): su texto puede estar incompleto"
            if motivo:
                filas.append(base + [SIN_DATO, SIN_DATO, SIN_DATO, pagina["numero_pdf"], pagina.get("numero_impreso") or SIN_DATO,
                                     motivo, "no revisada", SIN_DATO, pagina.get("origen_texto")])
    hoja = hoja_tabla(libro, "Menciones en texto", columnas, filas, [28, 24, 24, 18, 18, 18, 9, 9, 70, 16, 24, 12])
    pintar(hoja, "recogido_en_obligacion", {"OBL-": VERDE, "no revisada": ROJO, "no": AMARILLO})


SIN_RESULTADOS = "No hay resultados"
COLUMNAS_HOJA_CONSULTA = ["consulta", "fecha_hora", "filtro", "alcance"] + buscar_palabras.COLUMNAS_CONSULTA


class ExcelAbierto(Exception):
    """El Excel de salida está abierto en otro programa y no se puede reescribir."""


class ErrorAgregarConsulta(Exception):
    """La consulta pedida con --agregar-consulta no existe o no se puede leer."""


def archivo_de_bloqueo(destino):
    """Archivo que Excel (~$nombre) o LibreOffice (.~lock.nombre#) crean junto al libro mientras está abierto."""
    destino = Path(destino)
    for bloqueo in (destino.with_name(f"~${destino.name}"), destino.with_name(f".~lock.{destino.name}#")):
        if bloqueo.exists():
            return bloqueo
    return None


def mensaje_excel_abierto(destino):
    return (f"El archivo {Path(destino).as_posix()} está abierto en Excel (u otro programa) y no se puede reescribir. "
            f"Ciérrelo y vuelva a ejecutar; no se cambió nada.")


def cargar_consultas(carpeta_salida, incluir=()):
    """Consultas de salida/consultas/ que van a la hoja Consulta, la más reciente primero: las marcadas
    "en_excel": true y las de `incluir` (nombres de archivo que se están agregando ahora).
    Devuelve (consultas, avisos). Un JSON dañado se informa y se salta."""
    consultas, avisos = [], []
    for ruta in sorted((Path(carpeta_salida) / "consultas").glob("consulta_*.json")):
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if not isinstance(datos, dict) or "consulta" not in datos:
                raise ValueError("no tiene el formato de una consulta")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            avisos.append(f"Consulta {ruta.name}: no se pudo leer ({error}); no aparece en la hoja Consulta.")
            continue
        if datos.get("en_excel") is not True and ruta.name not in incluir:
            continue  # el usuario no pidió agregarla: queda solo en salida/consultas/
        datos["_archivo"] = ruta.name
        consultas.append(datos)
    consultas.sort(key=lambda c: (c.get("fecha_hora") or c.get("fecha") or "", c["_archivo"]), reverse=True)
    return consultas, avisos


def texto_filtro(consulta):
    filtro = consulta.get("filtro")
    if not filtro:
        return "No consta (consulta anterior a la Etapa 6)"
    if filtro.get("unidad_fiscalizable"):
        return f"Unidad fiscalizable: {filtro['unidad_fiscalizable']}"
    if filtro.get("archivos_pedidos"):
        return "RCAs: " + ", ".join(filtro["archivos_pedidos"])
    return f"Todas las RCAs procesadas ({len(filtro.get('archivos') or [])})"


def texto_de_que(consulta):
    """Qué se buscó: el tema con sus términos, un término de un tema buscado solo, o un término libre."""
    if consulta.get("tema"):
        return f"{consulta['consulta']} (tema {consulta['tema']}: {', '.join(consulta.get('terminos') or [])})"
    if consulta.get("tema_del_termino"):
        return f"{consulta['consulta']} (término del tema {consulta['tema_del_termino']}, buscado solo)"
    return f"{consulta['consulta']} (término libre)"


def hoja_consulta(libro, carpeta_salida, incluir=()):
    """Historial de consultas (consultar-obligaciones): una fila por resultado, la consulta más reciente arriba.
    Se crea solo si hay consultas guardadas. Cada consulta se muestra tal como se guardó: no se recalcula."""
    consultas, avisos = cargar_consultas(carpeta_salida, incluir)
    if not consultas:
        return avisos
    filas = []
    for consulta in consultas:
        base = [texto_de_que(consulta), consulta.get("fecha_hora") or consulta.get("fecha") or NO_CONSTA, texto_filtro(consulta),
                "\n".join(consulta.get("alcance_texto") or []) or NO_CONSTA]
        resultados = consulta.get("filas") or []
        if not resultados:
            vacia = {c: SIN_DATO for c in buscar_palabras.COLUMNAS_CONSULTA}
            vacia.update(categoria=SIN_RESULTADOS,
                         descripcion=consulta.get("mensaje") or f"No hay resultados para «{consulta['consulta']}».")
            resultados = [vacia]
        for fila in resultados:
            filas.append(base + [fila.get(c, SIN_DATO) for c in buscar_palabras.COLUMNAS_CONSULTA])
    hoja = hoja_tabla(libro, "Consulta", COLUMNAS_HOJA_CONSULTA, filas,
                      [26, 18, 28, 60, 20, 28, 24, 24, 12, 10, 26, 50, 24, 18, 8, 8, 60, 18, 26, 18, 50, 12, 60, 20, 20])
    pintar(hoja, "categoria", {buscar_palabras.LITERAL: VERDE, buscar_palabras.RELACION: AMARILLO,
                               buscar_palabras.MENCION: GRIS, SIN_RESULTADOS: ROJO})
    return avisos


def hoja_fichas(libro, manifiesto, rcas):
    filas = []
    for fila_manifiesto in manifiesto["filas"]:
        rca = rcas[fila_manifiesto["archivo"]]
        numero = valor_simple(rca["ficha"], "numero_resolucion")
        for dato in filas_de_ficha(rca):
            filas.append([
                fila_manifiesto["unidad_fiscalizable"], fila_manifiesto["id_uf_snifa"] or SIN_DATO,
                fila_manifiesto["proyecto"], rca["archivo"], numero, dato["grupo"], dato["dato"], dato["campo"],
                dato["elemento"], dato["valor"], dato["pagina"], dato["cita"], dato["fuente"], dato["calidad"],
                dato["verificacion"], dato["complemento"],
            ])
    hoja = hoja_tabla(libro, "Fichas", [
        "unidad_fiscalizable", "id_uf_snifa", "proyecto", "archivo", "numero_resolucion", "grupo", "dato", "campo",
        "elemento", "valor", "pagina_pdf", "cita_textual", "fuente", "calidad", "verificacion", "dato_complementario",
    ], filas, [30, 10, 28, 26, 14, 18, 24, 22, 8, 50, 9, 60, 11, 30, 16, 36])
    pintar(hoja, "verificacion", COLOR_VERIFICACION)
    pintar(hoja, "fuente", COLOR_FUENTE)
    pintar(hoja, "calidad", {"OCR corregido": AMARILLO, "Solo OCR": AMARILLO, "OCR confirmado": VERDE, "Leído en la imagen": AZUL})
    pintar(hoja, "dato", {"Página no leída": ROJO})


# --------------------------------------------------------------------------- principal

def consultas_a_agregar(carpeta_salida, rutas):
    """Valida las consultas pedidas con --agregar-consulta: deben ser JSON de consulta en salida/consultas/."""
    carpeta = (Path(carpeta_salida) / "consultas").resolve()
    elegidas = []
    for ruta in rutas or ():
        ruta = Path(ruta)
        if ruta.parent == Path("."):
            ruta = carpeta / ruta.name  # basta el nombre del archivo
        if ruta.suffix != ".json":
            ruta = ruta.with_suffix(".json")  # también se acepta la ruta del CSV de la consulta
        if not ruta.exists() or ruta.resolve().parent != carpeta:
            raise ErrorAgregarConsulta(f"No existe la consulta {ruta.as_posix()} en {carpeta.as_posix()}.")
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ErrorAgregarConsulta(f"La consulta {ruta.name} no se puede leer ({error}).")
        if not isinstance(datos, dict) or "consulta" not in datos:
            raise ErrorAgregarConsulta(f"{ruta.name} no tiene el formato de una consulta.")
        elegidas.append((ruta, datos))
    return elegidas


def marcar_en_excel(elegidas, momento):
    for ruta, datos in elegidas:
        datos["en_excel"] = True
        datos["agregada_al_excel"] = momento.strftime("%Y-%m-%d %H:%M:%S")
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def exportar(ruta_manifiesto, carpeta_rcas, carpeta_salida, generado=None, ruta_temas=None, agregar_consultas=()):
    """Genera el Excel y devuelve (ruta, resumen). Lanza leer_manifiesto.ErrorManifiesto si el manifiesto falla,
    ExcelAbierto si el archivo está abierto y ErrorAgregarConsulta si una consulta pedida no sirve.
    agregar_consultas: JSON de consultas que el usuario pidió agregar a la hoja Consulta; se marcan
    "en_excel": true solo si el Excel se guardó."""
    destino = Path(carpeta_salida) / NOMBRE_EXCEL
    if archivo_de_bloqueo(destino):
        raise ExcelAbierto(mensaje_excel_abierto(destino))
    elegidas = consultas_a_agregar(carpeta_salida, agregar_consultas)
    manifiesto = leer_manifiesto.leer_manifiesto(ruta_manifiesto, carpeta_rcas)
    rcas = {}
    for fila in manifiesto["filas"]:
        if fila["archivo"] not in rcas:
            rcas[fila["archivo"]] = cargar_rca(fila["archivo"], carpeta_rcas, carpeta_salida)
    prefijos = ids_visibles.prefijos_de(manifiesto["filas"])
    revision = registrar_revision.estado_actual(carpeta_salida)
    for archivo, rca in rcas.items():
        rca["prefijos"] = prefijos
        rca["revision"] = {ident: fila for (a, ident), fila in revision.items() if a == archivo}
    libro = Workbook()
    manifiesto["avisos"] += cargar_consultas(carpeta_salida)[1]  # antes de la Léeme, para que los muestre
    hoja_leeme(libro, manifiesto, rcas, generado or datetime.datetime.now())
    hoja_indice(libro, manifiesto, rcas)
    hoja_resumen(libro, manifiesto, rcas)
    try:
        temas = buscar_palabras.cargar_temas(ruta_temas or buscar_palabras.TEMAS_POR_DEFECTO)
    except buscar_palabras.ErrorTemas as error:
        manifiesto["avisos"].append(f"Temas: {error} Las columnas de temas y la hoja de menciones quedan vacías.")
        temas = {}
    hoja_obligaciones(libro, manifiesto, rcas, temas)
    hoja_fichas(libro, manifiesto, rcas)
    hoja_menciones(libro, manifiesto, rcas, temas)
    hoja_consulta(libro, carpeta_salida, {ruta.name for ruta, _ in elegidas})
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        libro.save(destino)
    except PermissionError:  # Windows bloquea el archivo mientras Excel lo tiene abierto
        raise ExcelAbierto(mensaje_excel_abierto(destino))
    marcar_en_excel(elegidas, datetime.datetime.now())
    resumen = {
        "rcas": len(rcas),
        "unidades": len({f["unidad_fiscalizable"] for f in manifiesto["filas"]}),
        "estados": {a: r["estado"] for a, r in rcas.items()},
        "avisos": manifiesto["avisos"],
    }
    return destino, resumen


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Genera salida/compliance_ambiental.xlsx.")
    parser.add_argument("--manifiesto", default="manifiesto.csv")
    parser.add_argument("--rcas", default="rcas", help="Carpeta de los PDFs")
    parser.add_argument("--salida", default="salida")
    parser.add_argument("--temas", default=None, help="Archivo de temas (por defecto: config/temas.yaml)")
    parser.add_argument("--agregar-consulta", action="append", default=[],
                        help="JSON (o su nombre) de una consulta de salida/consultas/ que se agrega a la hoja Consulta")
    opciones = parser.parse_args(argumentos)
    try:
        destino, resumen = exportar(opciones.manifiesto, opciones.rcas, opciones.salida, ruta_temas=opciones.temas,
                                    agregar_consultas=opciones.agregar_consulta)
    except ExcelAbierto as error:
        print(f"AVISO: {error}")
        return 3
    except (leer_manifiesto.ErrorManifiesto, ErrorAgregarConsulta) as error:
        print(f"ERROR: {error}")
        return 1
    print(f"== Excel generado: {destino.as_posix()} ({resumen['rcas']} RCAs, {resumen['unidades']} unidades fiscalizables)")
    for ruta in opciones.agregar_consulta:
        print(f"   consulta agregada a la hoja Consulta: {Path(ruta).name}")
    for archivo, estado in resumen["estados"].items():
        print(f"   {archivo}: {estado}")
    for aviso in resumen["avisos"]:
        print(f"   aviso: {aviso}")
    print(f"   {AVISO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
