"""Revisa por código que la lista de obligaciones de una RCA cumpla las reglas del proyecto (sin IA).

Uso:
    python scripts/validar_obligaciones.py OBLIGACIONES_JSON TEXTO_JSON [--secciones SECCIONES_JSON] [--salida salida]

Revisa:
    - estructura: campos de la sección 8 de ESPECIFICACION.md en cada obligación, sin campos vacíos
      (lo que no consta dice "No consta");
    - valores permitidos de tipo, fase, confianza y fuente; ID correlativos OBL-001, OBL-002...;
    - página existente, página impresa igual a la detectada por leer_pdf.py, cita de unas 40 palabras como máximo;
    - "posible_duplicado": los ID nombrados existen y la relación es recíproca;
    - filas agrupadas ("agrupada": true, varias medidas sin plazo propio en una fila): deben tener al menos una
      cita adicional (cada una con su página) y un rango de páginas de respaldo que cubra todas las citas;
    - que cada cita exista en su página (usa verificar_citas.py);
    - temas_relacionados (Etapa 5): cada elemento con un tema de config/temas.yaml que no sea ya literal,
      una justificación que cite entre « » las palabras del PDF, esas palabras (palabras_pdf) en su página
      (pagina_pdf, comprobado por código; en páginas escaneadas, o en tablas leídas en la imagen, solo se advierte)
      y estado "revisar"; opcionalmente "dudosa": true para las relaciones que el abogado marcó como dudosas;
    - COBERTURA: cada página del rango de obligaciones que propuso el localizador debe estar citada por al menos
      una obligación, o listada como "leída sin obligaciones" (con motivo), o como "no leída" (con motivo).
      Así una página no puede quedar sin revisar sin que se note.

Resultado: ERRORES (hay que corregir) y ADVERTENCIAS (revisar), y salida/verificacion/<archivo>_obligaciones_citas.json.
Termina con código 1 si hay errores.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import buscar_palabras
import verificar_citas

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "skills" / "extraer-obligaciones" / "plantilla_obligaciones.json"
AVISO = "Herramienta de apoyo. Requiere revisión de un abogado."
NO_CONSTA = "No consta"

TIPOS = [
    "condición o exigencia",
    "compromiso ambiental voluntario",
    "medida de mitigación",
    "medida de reparación",
    "medida de compensación",
    "plan de seguimiento o monitoreo",
    "reporte o informe a la autoridad",
    "trámite o aprobación ante la autoridad",
    "plan de contingencia o emergencia",
    "condición de PAS",
    "forma de cumplimiento de normativa",
    "otra",
]
FASES_SIMPLES = ["construcción", "operación", "cierre"]
FASES_ESPECIALES = ["todas", NO_CONSTA]
CONFIANZAS = ["alta", "media", "baja"]
FUENTES = ["texto", "imagen", "ocr_previo"]
CAMPOS_TEXTO = [
    "tipo", "componente_ambiental", "fase", "descripcion", "plazo_o_frecuencia", "hito_o_gatillo", "responsable",
    "autoridad_destinataria", "medio_de_verificacion", "parametro_o_indicador", "ubicacion_en_documento",
    "seccion_localizador", "pagina_impresa", "cita_textual", "fuente", "confianza",
]
PALABRAS_AVISO, PALABRAS_ERROR = 40, 55


def cargar_plantilla():
    return json.loads(PLANTILLA.read_text(encoding="utf-8"))


def fase_valida(fase):
    """"construcción", "operación, cierre" (combinación en orden), "todas" o "No consta"."""
    if fase in FASES_ESPECIALES:
        return True
    partes = [p.strip() for p in str(fase).split(",")]
    return all(p in FASES_SIMPLES for p in partes) and partes == sorted(set(partes), key=FASES_SIMPLES.index)


def revisar_obligacion(obligacion, indice, paginas, errores, advertencias):
    esperados = set(cargar_plantilla()["modelo_obligacion"])
    ident = obligacion.get("id_obligacion", f"#{indice}")
    faltan = sorted(esperados - set(obligacion))
    sobran = sorted(set(obligacion) - esperados - {"correccion_ocr"})
    if faltan:
        errores.append(f"{ident}: faltan campos {faltan}")
        return
    if sobran:
        errores.append(f"{ident}: campos que no están en la plantilla {sobran}")
    if obligacion["id_obligacion"] != f"OBL-{indice:03d}":
        errores.append(f"{ident}: el ID debería ser OBL-{indice:03d} (correlativo)")
    for campo in CAMPOS_TEXTO:
        valor = obligacion[campo]
        if not isinstance(valor, str) or not valor.strip():
            errores.append(f"{ident}.{campo}: vacío; si el texto no lo dice, escribir \"{NO_CONSTA}\"")
    if obligacion["descripcion"] == NO_CONSTA:
        errores.append(f"{ident}.descripcion: una obligación debe describirse")
    if obligacion["tipo"] not in TIPOS:
        errores.append(f"{ident}.tipo: {obligacion['tipo']!r} no permitido; use uno de {TIPOS}")
    if not fase_valida(obligacion["fase"]):
        errores.append(f"{ident}.fase: {obligacion['fase']!r} no permitida (construcción, operación, cierre, combinaciones "
                       f"en ese orden separadas por coma, todas o No consta)")
    if obligacion["confianza"] not in CONFIANZAS:
        errores.append(f"{ident}.confianza: {obligacion['confianza']!r} no permitida ({CONFIANZAS})")
    for campo in ("temas_literales", "temas_relacionados", "posible_duplicado"):
        if not isinstance(obligacion[campo], list):
            errores.append(f"{ident}.{campo}: debe ser una lista")
    pagina = obligacion["pagina_pdf"]
    if not isinstance(pagina, int) or pagina not in paginas:
        errores.append(f"{ident}.pagina_pdf: la página {pagina!r} no existe en el PDF")
        return
    impresa = paginas[pagina].get("numero_impreso")
    esperada = str(impresa) if impresa not in (None, "") else NO_CONSTA
    if str(obligacion["pagina_impresa"]) != esperada:
        errores.append(f"{ident}.pagina_impresa: {obligacion['pagina_impresa']!r}; según el PDF es {esperada!r}")
    palabras = len(str(obligacion["cita_textual"]).split())
    if palabras > PALABRAS_ERROR:
        errores.append(f"{ident}.cita_textual: {palabras} palabras (máximo unas {PALABRAS_AVISO})")
    elif palabras > PALABRAS_AVISO:
        advertencias.append(f"{ident}.cita_textual: {palabras} palabras (máximo unas {PALABRAS_AVISO})")
    fuente = obligacion["fuente"]
    if fuente not in FUENTES:
        errores.append(f"{ident}.fuente: {fuente!r} no válida ({FUENTES})")
    elif paginas[pagina].get("origen_texto") == "ocr_previo" and fuente == "texto":
        errores.append(f"{ident}.fuente: la página {pagina} tiene OCR previo; la fuente debe ser \"ocr_previo\" o \"imagen\"")
    elif paginas[pagina].get("escaneada") and fuente != "imagen":
        errores.append(f"{ident}.fuente: la página {pagina} está escaneada sin texto; la fuente debe ser \"imagen\"")
    if "correccion_ocr" in obligacion and fuente != "ocr_previo":
        errores.append(f"{ident}.correccion_ocr: solo corresponde a fuente \"ocr_previo\"")
    revisar_agrupada(obligacion, ident, paginas, errores)
    if obligacion["confianza"] == "baja" and not str(obligacion["notas"]).strip():
        advertencias.append(f"{ident}: confianza baja sin nota que explique por qué")


def paginas_de_rango(texto):
    """"85-86, 88" -> {85, 86, 88}; None si el formato no es válido."""
    paginas = set()
    for parte in str(texto).split(","):
        parte = parte.strip()
        if not re.fullmatch(r"\d+(-\d+)?", parte):
            return None
        inicio, _, fin = parte.partition("-")
        paginas.update(range(int(inicio), int(fin or inicio) + 1))
    return paginas


def revisar_agrupada(obligacion, ident, paginas, errores):
    """Una fila que agrupa varias medidas necesita varias citas y un rango de páginas de respaldo."""
    adicionales = obligacion.get("citas_adicionales", [])
    if not isinstance(adicionales, list):
        errores.append(f"{ident}.citas_adicionales: debe ser una lista")
        return
    for cita in adicionales:
        if not isinstance(cita, dict) or cita.get("pagina_pdf") not in paginas or not str(cita.get("cita_textual", "")).strip():
            errores.append(f"{ident}.citas_adicionales: cada cita necesita pagina_pdf (que exista) y cita_textual: {cita!r}")
    if not obligacion.get("agrupada"):
        return
    if not adicionales:
        errores.append(f"{ident}: fila agrupada con una sola cita; agregue en citas_adicionales una cita por cada medida que agrupa")
    rango = paginas_de_rango(obligacion.get("paginas_respaldo", ""))
    if not rango:
        errores.append(f"{ident}.paginas_respaldo: falta el rango de páginas que respalda la fila agrupada (ej.: \"85-86\")")
        return
    citadas = {obligacion["pagina_pdf"]} | {c.get("pagina_pdf") for c in adicionales if isinstance(c, dict)}
    if not citadas <= rango:
        errores.append(f"{ident}.paginas_respaldo: {obligacion['paginas_respaldo']!r} no cubre las páginas citadas {sorted(citadas)}")


def citas_planas(obligaciones):
    """Cita principal y citas adicionales de cada obligación, para verificarlas todas."""
    planas = []
    for obligacion in obligaciones:
        planas.append({"id": obligacion.get("id_obligacion"), "pagina_pdf": obligacion.get("pagina_pdf"),
                       "cita_textual": obligacion.get("cita_textual"), "fuente": obligacion.get("fuente")})
        for cita in obligacion.get("citas_adicionales", []) or []:
            if isinstance(cita, dict):
                planas.append({"id": obligacion.get("id_obligacion"), "pagina_pdf": cita.get("pagina_pdf"),
                               "cita_textual": cita.get("cita_textual"), "fuente": cita.get("fuente", obligacion.get("fuente"))})
    return planas


def revisar_duplicados(obligaciones, errores):
    por_id = {o.get("id_obligacion"): o for o in obligaciones}
    for obligacion in obligaciones:
        for otro in obligacion.get("posible_duplicado", []) or []:
            if otro not in por_id:
                errores.append(f"{obligacion['id_obligacion']}.posible_duplicado: {otro} no existe")
            elif obligacion["id_obligacion"] not in (por_id[otro].get("posible_duplicado") or []):
                errores.append(f"{obligacion['id_obligacion']}.posible_duplicado: {otro} no la nombra de vuelta")
            elif otro == obligacion["id_obligacion"]:
                errores.append(f"{otro}.posible_duplicado: no puede apuntarse a sí misma")


def revisar_cobertura(datos, paginas, secciones, errores, advertencias):
    """Cada página del rango: citada, leída sin obligaciones (con motivo) o no leída (con motivo)."""
    control = datos.get("control", {})
    rango = control.get("paginas_rango", [])
    if secciones is not None and sorted(rango) != sorted(secciones.get("paginas_para_obligaciones", [])):
        errores.append("control.paginas_rango no coincide con paginas_para_obligaciones del localizador")
    citadas = {c["pagina_pdf"] for c in citas_planas(datos.get("obligaciones", []))}
    sin_obligaciones, no_leidas = {}, {}
    for lista, destino, nombre in ((control.get("paginas_sin_obligaciones", []), sin_obligaciones, "paginas_sin_obligaciones"),
                                   (control.get("paginas_no_leidas", []), no_leidas, "paginas_no_leidas")):
        for item in lista:
            if not isinstance(item, dict) or item.get("pagina") not in paginas or not str(item.get("motivo", "")).strip():
                errores.append(f"control.{nombre}: cada elemento necesita pagina (que exista) y motivo: {item!r}")
            else:
                destino[item["pagina"]] = item["motivo"]
    for pagina in sorted(set(sin_obligaciones) & citadas):
        errores.append(f"p. {pagina}: está citada por una obligación y a la vez listada como leída sin obligaciones")
    for pagina in sorted(set(no_leidas) & citadas):
        errores.append(f"p. {pagina}: está citada por una obligación y a la vez listada como no leída")
    faltan = [p for p in rango if p not in citadas and p not in sin_obligaciones and p not in no_leidas]
    if faltan:
        errores.append(f"COBERTURA: páginas del rango sin revisar: {faltan}")
    for pagina in sorted(sin_obligaciones):
        if paginas.get(pagina, {}).get("escaneada"):
            advertencias.append(f"p. {pagina}: escaneada y listada sin obligaciones; confirmar que se leyó con visión")
    fuera = sorted({p for p in citadas if isinstance(p, int)} - set(rango))
    if fuera:
        advertencias.append(f"obligaciones citadas fuera del rango del localizador (encontradas por búsqueda): páginas {fuera}")
    return {"rango": len(rango), "citadas": len(set(rango) & citadas), "sin_obligaciones": len(sin_obligaciones),
            "no_leidas": len(no_leidas), "faltan": faltan}


CAMPOS_RELACION = {"tema", "justificacion", "palabras_pdf", "pagina_pdf", "estado"}


def revisar_temas_relacionados(datos, texto, errores, advertencias, temas=None):
    """Cada relación temática debe ser interpretación marcada "revisar" y respaldada por palabras del PDF."""
    obligaciones = datos.get("obligaciones", [])
    if not any(o.get("temas_relacionados") for o in obligaciones if isinstance(o, dict)) and "temas_relacionados_revisados" not in datos:
        return
    temas = temas if temas is not None else buscar_palabras.cargar_temas()
    revisados = datos.get("temas_relacionados_revisados")
    if revisados is not None:
        desconocidos = sorted(set((revisados or {}).get("temas") or []) - set(temas))
        if not (revisados or {}).get("temas") or desconocidos:
            errores.append(f"temas_relacionados_revisados.temas: debe listar temas de config/temas.yaml (sobran {desconocidos})")
    for obligacion in obligaciones:
        ident = obligacion.get("id_obligacion")
        literales = buscar_palabras.temas_literales(obligacion, temas)
        vistos = set()
        for relacion in obligacion.get("temas_relacionados") or []:
            if not isinstance(relacion, dict) or not CAMPOS_RELACION <= set(relacion) <= CAMPOS_RELACION | {"dudosa"}:
                errores.append(f"{ident}.temas_relacionados: cada elemento necesita {sorted(CAMPOS_RELACION)} "
                               f"(y opcionalmente \"dudosa\"): {relacion!r}")
                continue
            if "dudosa" in relacion and not isinstance(relacion["dudosa"], bool):
                errores.append(f"{ident}.temas_relacionados[{relacion.get('tema')}]: \"dudosa\" debe ser true o false")
            tema = relacion["tema"]
            if tema not in temas:
                errores.append(f"{ident}.temas_relacionados: el tema {tema!r} no está en config/temas.yaml")
            if tema in literales:
                errores.append(f"{ident}.temas_relacionados: {tema!r} ya es coincidencia literal; no se repite como relación")
            if tema in vistos:
                errores.append(f"{ident}.temas_relacionados: {tema!r} repetido")
            vistos.add(tema)
            if relacion["estado"] != "revisar":
                errores.append(f"{ident}.temas_relacionados[{tema}]: estado debe ser \"revisar\" (es interpretación)")
            if "«" not in str(relacion["justificacion"]) or len(str(relacion["justificacion"]).split()) < 5:
                errores.append(f"{ident}.temas_relacionados[{tema}]: la justificación debe ser una frase que cite entre « » las palabras del PDF")
            if not str(relacion["palabras_pdf"]).strip() or relacion["pagina_pdf"] not in {p["numero_pdf"] for p in texto["paginas"]}:
                errores.append(f"{ident}.temas_relacionados[{tema}]: faltan palabras_pdf o la página no existe")
                continue
            veredicto = verificar_citas.verificar_cita(relacion["palabras_pdf"], relacion["pagina_pdf"], texto["paginas"])
            if veredicto["estado"] in ("no encontrada en esa página", "encontrada en otra página"):
                pagina = next(p for p in texto["paginas"] if p["numero_pdf"] == relacion["pagina_pdf"])
                revisadas = set((datos.get("control") or {}).get("paginas_revisadas_en_imagen") or [])
                leida_en_imagen = obligacion.get("fuente") == "imagen" and relacion["pagina_pdf"] in revisadas
                if buscar_palabras.pagina_sin_texto(pagina) or leida_en_imagen:
                    advertencias.append(f"{ident}.temas_relacionados[{tema}]: palabras leídas en la imagen de la p. "
                                        f"{relacion['pagina_pdf']}; confirmar visualmente")
                else:
                    errores.append(f"{ident}.temas_relacionados[{tema}]: las palabras «{relacion['palabras_pdf']}» no están "
                                   f"en la p. {relacion['pagina_pdf']} ({veredicto['estado']})")


def validar(datos, texto, secciones=None):
    """Devuelve (errores, advertencias, informe_de_citas, cobertura)."""
    errores, advertencias = [], []
    paginas = {p["numero_pdf"]: p for p in texto["paginas"]}
    if datos.get("archivo") != texto["archivo"]:
        errores.append(f"archivo: {datos.get('archivo')!r} no corresponde al texto de {texto['archivo']!r}")
    if texto.get("sha256") and datos.get("sha256") != texto["sha256"]:
        errores.append("sha256: no coincide con el del PDF (¿obligaciones de otra versión del documento?)")
    if datos.get("aviso") != AVISO:
        errores.append(f"aviso: falta \"{AVISO}\"")
    obligaciones = datos.get("obligaciones", [])
    if not isinstance(obligaciones, list):
        errores.append("obligaciones: debe ser una lista")
        obligaciones = []
    for indice, obligacion in enumerate(obligaciones, start=1):
        revisar_obligacion(obligacion, indice, paginas, errores, advertencias)
    revisar_duplicados(obligaciones, errores)
    revisar_temas_relacionados(datos, texto, errores, advertencias)
    cobertura = revisar_cobertura(datos, paginas, secciones, errores, advertencias)
    planas = citas_planas(obligaciones)
    informe = verificar_citas.verificar({"citas": planas}, texto)
    for cita in informe["citas"]:
        ident = planas[int(re.search(r"\[(\d+)\]", cita["campo"]).group(1))]["id"]
        if cita["estado"] == "no encontrada en esa página":
            errores.append(f"{ident}: la cita no se encontró en la p. {cita['pagina_pdf']} ni en otra")
        elif cita["estado"] == "encontrada en otra página":
            errores.append(f"{ident}: la cita está en la p. {cita['pagina_encontrada']}, no en la p. {cita['pagina_pdf']}")
        elif cita["estado"] == "aproximada":
            advertencias.append(f"{ident}: cita aproximada (similitud {cita['similitud']}); confirmar contra el PDF")
        elif cita["estado"] == "leída en imagen":
            advertencias.append(f"{ident}: leída en la imagen de la p. {cita['pagina_pdf']}; confirmar visualmente")
    return errores, advertencias, informe, cobertura


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Valida las obligaciones extraídas de una RCA.")
    parser.add_argument("obligaciones", help="JSON de salida/obligaciones/")
    parser.add_argument("texto", help="JSON de salida/texto/ de la misma RCA")
    parser.add_argument("--secciones", help="JSON de salida/secciones/ (por defecto se deduce del nombre)")
    parser.add_argument("--salida", default="salida")
    opciones = parser.parse_args(argumentos)
    datos = json.loads(Path(opciones.obligaciones).read_text(encoding="utf-8"))
    texto = json.loads(Path(opciones.texto).read_text(encoding="utf-8"))
    ruta_secciones = Path(opciones.secciones) if opciones.secciones else Path(opciones.texto).parent.parent / "secciones" / Path(opciones.texto).name
    secciones = json.loads(ruta_secciones.read_text(encoding="utf-8")) if ruta_secciones.exists() else None
    if secciones is None:
        print(f"   (sin mapa del localizador en {ruta_secciones.as_posix()}: no se compara el rango)")
    errores, advertencias, informe, cobertura = validar(datos, texto, secciones)
    destino = Path(opciones.salida) / "verificacion" / f"{Path(texto['archivo']).stem}_obligaciones_citas.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"== {texto['archivo']}: {len(datos.get('obligaciones', []))} obligaciones; citas {informe['resumen']}")
    print(f"   cobertura: {cobertura['rango']} páginas en el rango; {cobertura['citadas']} citadas, "
          f"{cobertura['sin_obligaciones']} leídas sin obligaciones, {cobertura['no_leidas']} no leídas, "
          f"{len(cobertura['faltan'])} sin revisar")
    for error in errores:
        print(f"   ERROR: {error}")
    for advertencia in advertencias:
        print(f"   advertencia: {advertencia}")
    print("   Obligaciones válidas." if not errores else f"   {len(errores)} errores por corregir.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
