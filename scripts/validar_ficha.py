"""Revisa por código que una ficha de RCA cumpla las reglas del proyecto (sin IA).

Uso:
    python scripts/validar_ficha.py FICHA_JSON TEXTO_JSON [--salida salida] [--secciones SECCIONES_JSON]

Revisa:
    - que estén todos los campos de skills/fichar-rca/plantilla_ficha.json, y ninguno inventado;
    - que cada dato tenga valor, página, cita y fuente ("texto", "imagen" u "ocr_previo"),
      o bien "No consta" sin página ni cita;
    - que la página exista, que la cita no supere unas 40 palabras, y formatos (fecha AAAA-MM-DD, sí/no);
    - que la fuente calce con la página (una página con OCR previo no puede tener fuente "texto");
    - que "campos_no_consta" coincida exactamente con los campos sin dato;
    - que cada cita exista en la página indicada (usa verificar_citas.py);
    - que letra_equivalente de cada efecto del artículo 11 venga de la tabla del reglamento_aplicable en
      config/equivalencias_articulo_11.yaml, con fuente "equivalencia_legal", y no contradiga la letra o el
      artículo que menciona el efecto (si la RCA no identifica reglamento, o su tabla está vacía, solo advierte);
    - que cada área protegida o sensible tenga una categoría permitida;
    - que hay_condiciones_exigencias, hay_compromisos_voluntarios y hay_plan_contingencias lleven
      rango_localizador igual al de salida/secciones/<archivo>.json (si existe).

Resultado: lista de ERRORES (hay que corregir) y ADVERTENCIAS (revisar), y salida/verificacion/<archivo>_citas.json.
Termina con código 1 si hay errores.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

import verificar_citas

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "skills" / "fichar-rca" / "plantilla_ficha.json"
NO_CONSTA = "No consta"
FUENTES = {"texto", "imagen", "ocr_previo"}
PALABRAS_AVISO = 40
PALABRAS_ERROR = 55
VALORES_PERMITIDOS = {
    "tipo_instrumento": {"DIA", "EIA", NO_CONSTA},
    "decision": {"favorable", "desfavorable", NO_CONSTA},
    "hay_medidas_mitigacion": {"sí", "no", NO_CONSTA},
    "hay_medidas_reparacion": {"sí", "no", NO_CONSTA},
    "hay_medidas_compensacion": {"sí", "no", NO_CONSTA},
    "hay_plan_seguimiento": {"sí", "no", NO_CONSTA},
    "hay_condiciones_exigencias": {"sí", "no", NO_CONSTA},
    "hay_compromisos_voluntarios": {"sí", "no", NO_CONSTA},
    "hay_plan_contingencias": {"sí", "no", NO_CONSTA},
}
CAMPOS_FECHA = {"fecha_resolucion"}

# Campos "hay_..." que además registran el rango de páginas que ubicó el localizador, y su sección.
CAMPOS_CON_RANGO = {
    "hay_condiciones_exigencias": "condiciones_exigencias",
    "hay_compromisos_voluntarios": "compromisos_voluntarios",
    "hay_plan_contingencias": "contingencias",
}
SIN_RANGO = "No ubicada"

# Equivalencia legal del artículo 11 (tablas fijas por reglamento en config/, no salen del documento).
EQUIVALENCIAS = RAIZ / "config" / "equivalencias_articulo_11.yaml"
FUENTE_EQUIVALENCIA = "equivalencia_legal"

# Categorías permitidas para cada elemento de areas_protegidas_o_sensibles.
CATEGORIAS_AREA = {"área protegida", "sitio prioritario", "humedal", "zona de interés turístico", "otra"}


def cargar_plantilla():
    return json.loads(PLANTILLA.read_text(encoding="utf-8"))


def cargar_reglamentos(ruta=None):
    """Devuelve {nombre del reglamento: {letra: artículo}} desde config/equivalencias_articulo_11.yaml.

    Un reglamento cuya tabla no se pudo verificar tiene {} (tabla vacía)."""
    datos = yaml.safe_load(Path(ruta or EQUIVALENCIAS).read_text(encoding="utf-8"))
    return {
        r["nombre"]: {fila["letra"]: int(fila["articulo_reglamento"]) for fila in (r.get("equivalencias") or [])}
        for r in datos["reglamentos"]
    }


def texto_equivalencia(letra, articulo, reglamento):
    """Valor del campo letra_equivalente, por ejemplo 'letra c) (artículo 8 del D.S. N° 95/2001, ...)'."""
    return f"letra {letra}) (artículo {articulo} del {reglamento})"


def menciones_articulo_11(texto, equivalencias):
    """Letras (a-f) que el texto nombra directamente o a través del artículo del Reglamento que cita.

    equivalencias es la tabla {letra: artículo} del reglamento aplicable (puede ser {})."""
    normal = verificar_citas.normalizar(texto)
    letras = set(re.findall(r"\bletra\s+([a-f])\)", normal))
    por_articulo = {articulo: letra for letra, articulo in equivalencias.items()}
    for numero in re.findall(r"\barticulo\s+(\d{1,2})\s*o?\s*,?\s+del\s+(?:rseia|reglamento)", normal):
        if int(numero) in por_articulo:
            letras.add(por_articulo[int(numero)])
    return letras


def reglamento_de_la_ficha(campos, reglamentos, advertencias):
    """Nombre del reglamento aplicable si está en la tabla; si no, None (con advertencia, nunca error)."""
    dato = campos.get("reglamento_aplicable")
    valor = dato.get("valor") if isinstance(dato, dict) else None
    if valor in (None, NO_CONSTA):
        advertencias.append("reglamento_aplicable: la RCA no identifica el reglamento; no se comprueba letra_equivalente")
        return None
    if valor not in reglamentos:
        advertencias.append(f"reglamento_aplicable: {valor!r} no está en config/equivalencias_articulo_11.yaml; no se comprueba letra_equivalente")
        return None
    if not reglamentos[valor]:
        advertencias.append(f"reglamento_aplicable: la tabla de {valor!r} está vacía (no verificada); no se comprueba letra_equivalente")
        return None
    return valor


def revisar_letra_equivalente(elemento, reglamento, reglamentos, errores, advertencias):
    """Revisa el campo letra_equivalente de un efecto del artículo 11 contra la tabla del reglamento aplicable."""
    nombre = "efectos_articulo_11[].letra_equivalente"
    equivalente = elemento.get("letra_equivalente")
    if not isinstance(equivalente, dict) or not {"valor", "pagina_pdf", "cita_textual", "fuente"} <= set(equivalente):
        errores.append(f"{nombre}: falta, o no tiene valor, pagina_pdf, cita_textual y fuente")
        return
    if equivalente["pagina_pdf"] is not None or equivalente["cita_textual"] is not None:
        errores.append(f"{nombre}: la equivalencia legal no lleva página ni cita")
    valor = equivalente["valor"]
    if valor == NO_CONSTA:
        if equivalente["fuente"] is not None:
            errores.append(f"{nombre}: \"No consta\" no lleva fuente")
        return
    if equivalente["fuente"] != FUENTE_EQUIVALENCIA:
        errores.append(f"{nombre}: la fuente debe ser \"{FUENTE_EQUIVALENCIA}\"")
    if reglamento is None:
        advertencias.append(f"{nombre}: {valor!r} no se puede comprobar sin un reglamento aplicable con tabla verificada")
        return
    tabla = reglamentos[reglamento]
    permitidos = {texto_equivalencia(letra, articulo, reglamento): letra for letra, articulo in tabla.items()}
    if valor not in permitidos:
        errores.append(f"{nombre}: valor {valor!r} no está en la tabla de {reglamento!r}")
        return
    mencionadas = menciones_articulo_11(f"{elemento.get('valor', '')} {elemento.get('cita_textual') or ''}", tabla)
    if not mencionadas:
        advertencias.append(f"{nombre}: {valor!r} no se apoya en una letra ni en un artículo del Reglamento mencionados en el efecto; revisar")
    elif permitidos[valor] not in mencionadas:
        errores.append(f"{nombre}: {valor!r} contradice lo que menciona el efecto (letras {sorted(mencionadas)})")


def revisar_categoria(elemento, errores):
    """Cada área protegida o sensible lleva una categoría de la lista permitida."""
    categoria = elemento.get("categoria") if isinstance(elemento, dict) else None
    if categoria not in CATEGORIAS_AREA:
        errores.append(f"areas_protegidas_o_sensibles[]: categoria {categoria!r} no válida; use una de {sorted(CATEGORIAS_AREA)}")


def rango_de_seccion(secciones, clave):
    """Rango de páginas que el localizador asignó a una sección, como texto ("66-70"), o "No ubicada"."""
    # Los tramos aislados (una página lejos del bloque principal, confianza baja) no cuentan para el rango.
    tramos = [t for t in (secciones.get("secciones", {}).get(clave, {}).get("tramos") or []) if not t.get("aislado")]
    partes = [f"{t['pagina_inicio']}-{t['pagina_fin']}" if t["pagina_fin"] != t["pagina_inicio"] else f"{t['pagina_inicio']}" for t in tramos]
    return ", ".join(partes) or SIN_RANGO


def revisar_rango(campo, dato, secciones, errores, advertencias):
    """Revisa rango_localizador de los campos hay_condiciones_exigencias, hay_compromisos_voluntarios y hay_plan_contingencias."""
    rango = dato.get("rango_localizador") if isinstance(dato, dict) else None
    if not isinstance(rango, str) or not rango.strip():
        errores.append(f"{campo}: falta rango_localizador (páginas que ubicó el localizador, o \"{SIN_RANGO}\")")
        return
    if secciones is None:
        return
    esperado = rango_de_seccion(secciones, CAMPOS_CON_RANGO[campo])
    if rango != esperado:
        errores.append(f"{campo}: rango_localizador {rango!r} no coincide con el localizador ({esperado!r})")
        return
    pagina = dato.get("pagina_pdf")
    if isinstance(pagina, int) and esperado != SIN_RANGO:
        dentro = any(
            int(inicio) <= pagina <= int(fin or inicio)
            for inicio, _, fin in (parte.partition("-") for parte in esperado.split(", "))
        )
        if not dentro:
            advertencias.append(f"{campo}: la cita (p. {pagina}) está fuera del rango del localizador ({esperado})")


def revisar_dato(campo, dato, paginas, errores, advertencias, en_lista=False):
    nombre = f"{campo}[]" if en_lista else campo
    if not isinstance(dato, dict) or not {"valor", "pagina_pdf", "cita_textual", "fuente"} <= set(dato):
        errores.append(f"{nombre}: debe tener valor, pagina_pdf, cita_textual y fuente")
        return
    valor = dato["valor"]
    if valor == NO_CONSTA:
        if en_lista:
            errores.append(f"{nombre}: una lista sin datos se deja vacía ([]), no con \"No consta\"")
        if dato["pagina_pdf"] is not None or dato["cita_textual"] is not None:
            errores.append(f"{nombre}: \"No consta\" no lleva página ni cita")
        return
    if valor in (None, "") or (isinstance(valor, str) and not valor.strip()):
        errores.append(f"{nombre}: valor vacío; si no consta, escribir \"No consta\"")
    pagina = dato["pagina_pdf"]
    if not isinstance(pagina, int) or pagina not in paginas:
        errores.append(f"{nombre}: la página {pagina!r} no existe en el PDF")
        return
    cita = dato["cita_textual"]
    if not isinstance(cita, str) or not cita.strip():
        errores.append(f"{nombre}: falta la cita textual")
    else:
        palabras = len(cita.split())
        if palabras > PALABRAS_ERROR:
            errores.append(f"{nombre}: la cita tiene {palabras} palabras (máximo unas {PALABRAS_AVISO})")
        elif palabras > PALABRAS_AVISO:
            advertencias.append(f"{nombre}: la cita tiene {palabras} palabras (máximo unas {PALABRAS_AVISO})")
    fuente = dato["fuente"]
    if "correccion_ocr" in dato and fuente != "ocr_previo":
        errores.append(f"{nombre}: correccion_ocr solo corresponde a datos con fuente \"ocr_previo\"")
    if fuente not in FUENTES:
        errores.append(f"{nombre}: fuente {fuente!r} no válida (texto, imagen u ocr_previo)")
    elif paginas[pagina].get("origen_texto") == "ocr_previo" and fuente == "texto":
        errores.append(f"{nombre}: la página {pagina} tiene OCR previo; la fuente debe ser \"ocr_previo\" o \"imagen\"")
    elif fuente == "ocr_previo" and paginas[pagina].get("origen_texto") != "ocr_previo":
        advertencias.append(f"{nombre}: fuente \"ocr_previo\" pero la página {pagina} tiene texto digital")
    permitidos = VALORES_PERMITIDOS.get(campo)
    if permitidos and "sí" in permitidos and isinstance(valor, str) and re.fullmatch(r"(sí|no): \S.*", valor):
        valor = valor.split(":", 1)[0]  # "sí: <nota breve>" se acepta; la nota aclara el alcance del dato
    if permitidos and valor not in permitidos:
        errores.append(f"{nombre}: valor {valor!r} no permitido; use uno de {sorted(permitidos)}")
    if campo in CAMPOS_FECHA and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(valor)):
        errores.append(f"{nombre}: la fecha debe ir en formato AAAA-MM-DD (valor: {valor!r})")


def validar(ficha, texto, secciones=None):
    """Devuelve (errores, advertencias, informe_de_citas). secciones: JSON del localizador (opcional)."""
    errores, advertencias = [], []
    plantilla = cargar_plantilla()
    reglamentos = cargar_reglamentos()
    paginas = {p["numero_pdf"]: p for p in texto["paginas"]}

    if ficha.get("archivo") != texto["archivo"]:
        errores.append(f"archivo: la ficha dice {ficha.get('archivo')!r} y el texto es de {texto['archivo']!r}")
    if ficha.get("aviso") != plantilla["aviso"]:
        errores.append("aviso: falta el aviso \"Herramienta de apoyo. Requiere revisión de un abogado.\"")

    campos = ficha.get("campos", {})
    esperados = plantilla["campos"]
    for faltante in sorted(set(esperados) - set(campos)):
        errores.append(f"{faltante}: falta el campo")
    for sobrante in sorted(set(campos) - set(esperados)):
        errores.append(f"{sobrante}: campo que no está en la plantilla")

    reglamento = reglamento_de_la_ficha(campos, reglamentos, advertencias)
    sin_dato = []
    for campo, modelo in esperados.items():
        if campo not in campos:
            continue
        valor = campos[campo]
        if isinstance(modelo, list):
            if not isinstance(valor, list):
                errores.append(f"{campo}: debe ser una lista (cada elemento con su página y cita)")
                continue
            if not valor:
                sin_dato.append(campo)
            for elemento in valor:
                revisar_dato(campo, elemento, paginas, errores, advertencias, en_lista=True)
                if campo == "efectos_articulo_11" and isinstance(elemento, dict):
                    revisar_letra_equivalente(elemento, reglamento, reglamentos, errores, advertencias)
                if campo == "areas_protegidas_o_sensibles":
                    revisar_categoria(elemento, errores)
        else:
            if isinstance(valor, dict) and valor.get("valor") == NO_CONSTA:
                sin_dato.append(campo)
            revisar_dato(campo, valor, paginas, errores, advertencias)
            if campo in CAMPOS_CON_RANGO:
                revisar_rango(campo, valor, secciones, errores, advertencias)

    control = ficha.get("control", {})
    declarados = control.get("campos_no_consta", [])
    if sorted(declarados) != sorted(sin_dato):
        faltan = sorted(set(sin_dato) - set(declarados))
        sobran = sorted(set(declarados) - set(sin_dato))
        errores.append(f"control.campos_no_consta no coincide (faltan: {faltan}; sobran: {sobran})")
    if control.get("paginas_totales") != len(paginas):
        errores.append(f"control.paginas_totales: {control.get('paginas_totales')} en vez de {len(paginas)}")
    revisadas = control.get("paginas_revisadas_en_imagen", [])
    if not isinstance(revisadas, list) or any(not isinstance(p, int) or p not in paginas for p in revisadas):
        errores.append("control.paginas_revisadas_en_imagen: debe ser una lista de páginas que existan en el PDF")
    for no_leida in control.get("paginas_no_leidas", []):
        if not isinstance(no_leida, dict) or no_leida.get("pagina") not in paginas or not all(
            isinstance(no_leida.get(clave), str) and no_leida[clave].strip() for clave in ("seccion", "motivo")
        ):
            errores.append(f"control.paginas_no_leidas: cada elemento necesita pagina (que exista), seccion y motivo: {no_leida!r}")
    escaneadas = [p for p, datos in paginas.items() if datos.get("escaneada")]
    if sorted(control.get("paginas_escaneadas", [])) != escaneadas:
        errores.append(f"control.paginas_escaneadas: debe ser {escaneadas}")

    informe = verificar_citas.verificar(ficha, texto)
    for cita in informe["citas"]:
        if cita["estado"] == "no encontrada en esa página":
            errores.append(f"{cita['campo']}: la cita no se encontró en la p. {cita['pagina_pdf']} ni en otra")
        elif cita["estado"] == "encontrada en otra página":
            advertencias.append(f"{cita['campo']}: la cita está en la p. {cita['pagina_encontrada']}, no en la p. {cita['pagina_pdf']}")
        elif cita["estado"] == "aproximada":
            advertencias.append(f"{cita['campo']}: cita aproximada (similitud {cita['similitud']}); confirmar contra el PDF")
        elif cita["estado"] == "leída en imagen":
            advertencias.append(f"{cita['campo']}: dato leído en la imagen de la p. {cita['pagina_pdf']}; confirmar visualmente")
    return errores, advertencias, informe


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Valida una ficha de RCA contra las reglas del proyecto.")
    parser.add_argument("ficha", help="JSON de salida/fichas/")
    parser.add_argument("texto", help="JSON de salida/texto/ de la misma RCA")
    parser.add_argument("--salida", default="salida")
    parser.add_argument("--secciones", help="JSON de salida/secciones/ (por defecto se deduce del nombre)")
    opciones = parser.parse_args(argumentos)
    ficha = json.loads(Path(opciones.ficha).read_text(encoding="utf-8"))
    texto = json.loads(Path(opciones.texto).read_text(encoding="utf-8"))
    ruta_secciones = Path(opciones.secciones) if opciones.secciones else Path(opciones.texto).parent.parent / "secciones" / Path(opciones.texto).name
    secciones = json.loads(ruta_secciones.read_text(encoding="utf-8")) if ruta_secciones.exists() else None
    if secciones is None:
        print(f"   (sin mapa del localizador en {ruta_secciones.as_posix()}: no se comprueba rango_localizador)")
    errores, advertencias, informe = validar(ficha, texto, secciones)
    destino = Path(opciones.salida) / "verificacion" / f"{Path(texto['archivo']).stem}_citas.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"== {texto['archivo']}: citas {informe['resumen']}")
    for error in errores:
        print(f"   ERROR: {error}")
    for advertencia in advertencias:
        print(f"   advertencia: {advertencia}")
    print("   Ficha válida." if not errores else f"   {len(errores)} errores por corregir.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
