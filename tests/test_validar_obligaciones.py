"""Pruebas de scripts/validar_obligaciones.py (datos sintéticos)."""

import copy

import validar_obligaciones as vo

TEXTO = {
    "archivo": "rca_prueba.pdf",
    "sha256": "abc",
    "paginas": [
        {"numero_pdf": 1, "numero_impreso": None, "origen_texto": "digital", "escaneada": False,
         "texto": "Identificación del proyecto."},
        {"numero_pdf": 2, "numero_impreso": "5", "origen_texto": "digital", "escaneada": False,
         "texto": "El Titular deberá capacitar a los trabajadores al inicio de cada fase. "
                  "Envío de informe a la SMA durante el mes siguiente."},
        {"numero_pdf": 3, "numero_impreso": None, "origen_texto": "digital", "escaneada": False,
         "texto": "Tabla de coordenadas UTM."},
        {"numero_pdf": 4, "numero_impreso": None, "origen_texto": "ocr_previo", "escaneada": True, "texto": ""},
    ],
}
SECCIONES = {"paginas_para_obligaciones": [2, 3, 4]}


def obligacion(numero, **cambios):
    base = copy.deepcopy(vo.cargar_plantilla()["modelo_obligacion"])
    base.update({
        "id_obligacion": f"OBL-{numero:03d}", "tipo": "compromiso ambiental voluntario", "fase": "construcción, cierre",
        "descripcion": "Capacitar a los trabajadores.", "responsable": "Titular",
        "ubicacion_en_documento": "Compromiso 9.1.1", "seccion_localizador": "compromisos_voluntarios",
        "pagina_pdf": 2, "pagina_impresa": "5", "confianza": "alta",
        "cita_textual": "El Titular deberá capacitar a los trabajadores al inicio de cada fase.",
    })
    base.update(cambios)
    return base


def datos(*obligaciones, sin=None, no_leidas=None):
    plantilla = copy.deepcopy(vo.cargar_plantilla())
    plantilla.pop("modelo_obligacion")
    plantilla.update(archivo="rca_prueba.pdf", sha256="abc", obligaciones=list(obligaciones))
    plantilla["control"]["paginas_rango"] = [2, 3, 4]
    plantilla["control"]["paginas_sin_obligaciones"] = sin if sin is not None else [{"pagina": 3, "motivo": "tabla de coordenadas"}]
    plantilla["control"]["paginas_no_leidas"] = no_leidas if no_leidas is not None else [
        {"pagina": 4, "seccion": "medidas", "motivo": "escaneada ilegible"}]
    return plantilla


def test_obligaciones_validas_con_reporte_separado():
    reporte = obligacion(2, tipo="reporte o informe a la autoridad", descripcion="Enviar informe a la SMA.",
                         plazo_o_frecuencia="durante el mes siguiente", autoridad_destinataria="SMA",
                         cita_textual="Envío de informe a la SMA durante el mes siguiente.")
    errores, advertencias, informe, cobertura = vo.validar(datos(obligacion(1), reporte), TEXTO, SECCIONES)
    assert errores == []
    assert informe["resumen"] == {"confirmada": 2}
    assert cobertura["faltan"] == []


def test_tramite_ante_la_autoridad_es_tipo_valido():
    tramite = obligacion(2, tipo="trámite o aprobación ante la autoridad", descripcion="Informar a la SMA el inicio de cada fase.",
                         autoridad_destinataria="SMA", cita_textual="Envío de informe a la SMA durante el mes siguiente.")
    errores, _, _, _ = vo.validar(datos(obligacion(1), tramite), TEXTO, SECCIONES)
    assert errores == []


def test_tipos_de_la_plantilla_coinciden_con_el_validador():
    assert vo.cargar_plantilla()["tipos_permitidos"] == vo.TIPOS
    assert "trámite o aprobación ante la autoridad" in vo.TIPOS


def test_cobertura_detecta_paginas_sin_revisar():
    errores, _, _, cobertura = vo.validar(datos(obligacion(1), sin=[], no_leidas=[]), TEXTO, SECCIONES)
    assert cobertura["faltan"] == [3, 4]
    assert any(e.startswith("COBERTURA") and "[3, 4]" in e for e in errores)


def test_valores_no_permitidos_y_campos_vacios():
    mala = obligacion(1, tipo="obligación genérica", fase="cierre, construcción", confianza="muy alta", hito_o_gatillo="")
    errores, _, _, _ = vo.validar(datos(mala), TEXTO, SECCIONES)
    assert any("tipo" in e for e in errores)
    assert any("fase" in e for e in errores)
    assert any("confianza" in e for e in errores)
    assert any("hito_o_gatillo" in e and "No consta" in e for e in errores)


def test_id_correlativo_pagina_impresa_y_cita_inventada():
    errores, _, _, _ = vo.validar(datos(obligacion(1), obligacion(3, pagina_impresa="No consta",
                                                                   cita_textual="El Titular deberá plantar árboles.")),
                                  TEXTO, SECCIONES)
    assert any("OBL-003" in e and "correlativo" in e for e in errores)
    assert any("pagina_impresa" in e for e in errores)
    assert any("no se encontró" in e for e in errores)


def test_posible_duplicado_debe_ser_reciproco():
    errores, _, _, _ = vo.validar(datos(obligacion(1, posible_duplicado=["OBL-002"]), obligacion(2)), TEXTO, SECCIONES)
    assert any("no la nombra de vuelta" in e for e in errores)
    errores, _, _, _ = vo.validar(
        datos(obligacion(1, posible_duplicado=["OBL-002"]), obligacion(2, posible_duplicado=["OBL-001"])), TEXTO, SECCIONES)
    assert errores == []


def test_pagina_escaneada_exige_fuente_imagen():
    leida = obligacion(1, pagina_pdf=4, pagina_impresa="No consta", fuente="texto", cita_textual="Medida leída en la imagen.")
    errores, _, _, _ = vo.validar(datos(leida, no_leidas=[]), TEXTO, SECCIONES)
    assert any("OCR previo" in e or "escaneada" in e for e in errores)


def test_fases_permitidas():
    assert vo.fase_valida("construcción, operación, cierre")
    assert vo.fase_valida("todas") and vo.fase_valida("No consta")
    assert not vo.fase_valida("operación, construcción")
    assert not vo.fase_valida("abandono")


def test_fila_agrupada_exige_varias_citas_y_rango():
    agrupada = obligacion(1, agrupada=True, cita_textual="El Titular deberá capacitar a los trabajadores al inicio de cada fase.")
    errores, _, _, _ = vo.validar(datos(agrupada), TEXTO, SECCIONES)
    assert any("una sola cita" in e for e in errores)
    assert any("paginas_respaldo" in e for e in errores)
    agrupada["citas_adicionales"] = [{"pagina_pdf": 2, "cita_textual": "Envío de informe a la SMA durante el mes siguiente."}]
    agrupada["paginas_respaldo"] = "2"
    errores, _, informe, _ = vo.validar(datos(agrupada), TEXTO, SECCIONES)
    assert errores == []
    assert informe["resumen"] == {"confirmada": 2}  # se verifican la cita principal y la adicional


def test_cita_adicional_inventada_o_fuera_del_rango():
    agrupada = obligacion(1, agrupada=True, paginas_respaldo="2",
                          citas_adicionales=[{"pagina_pdf": 3, "cita_textual": "Medida que no existe en la página."}])
    errores, _, _, _ = vo.validar(datos(agrupada, sin=[]), TEXTO, SECCIONES)
    assert any("no cubre" in e for e in errores)
    assert any("no se encontró" in e for e in errores)


# ------------------------------------------------------------------ temas_relacionados (Etapa 5)

TEMAS = {"humedales": ["humedal", "bofedal"], "flora_y_fauna": ["flora", "fauna"]}
TEXTO_TEMAS = {"archivo": "rca_prueba.pdf", "paginas": [
    {"numero_pdf": 1, "texto": "Se protegerá el pajonal hídrico salino. Se cuidará la fauna.", "estado": "texto",
     "origen_texto": "digital"},
    {"numero_pdf": 2, "texto": "", "estado": "escaneada", "origen_texto": "digital"}]}


def relacion(**cambios):
    base = {"tema": "humedales", "justificacion": "Se refiere al «pajonal hídrico salino», que la RCA no llama humedal.",
            "palabras_pdf": "pajonal hídrico salino", "pagina_pdf": 1, "estado": "revisar"}
    base.update(cambios)
    return base


def revisar_temas(*relaciones, cita="Se protegerá el pajonal hídrico salino."):
    datos = {"obligaciones": [{"id_obligacion": "OBL-001", "cita_textual": cita, "pagina_pdf": 1,
                               "citas_adicionales": [], "temas_relacionados": list(relaciones)}]}
    errores, advertencias = [], []
    vo.revisar_temas_relacionados(datos, TEXTO_TEMAS, errores, advertencias, TEMAS)
    return errores, advertencias


def test_relacion_tematica_valida():
    assert revisar_temas(relacion()) == ([], [])


def test_relacion_sin_justificacion_con_palabras_del_pdf():
    errores, _ = revisar_temas(relacion(justificacion="Es parecido a un humedal."))
    assert any("« »" in e for e in errores)


def test_relacion_con_tema_inexistente_o_sin_revisar():
    errores, _ = revisar_temas(relacion(tema="salares", estado="confirmada"))
    assert any("no está en config/temas.yaml" in e for e in errores)
    assert any("revisar" in e for e in errores)


def test_relacion_con_palabras_que_no_estan_en_la_pagina():
    errores, _ = revisar_temas(relacion(palabras_pdf="bofedal altoandino"))
    assert any("no están en la p. 1" in e for e in errores)


def test_relacion_no_repite_un_tema_literal():
    errores, _ = revisar_temas(relacion(tema="flora_y_fauna", palabras_pdf="fauna"), cita="Se cuidará la fauna.")
    assert any("ya es coincidencia literal" in e for e in errores)


def test_relacion_en_pagina_escaneada_solo_advierte():
    errores, advertencias = revisar_temas(relacion(pagina_pdf=2))
    assert errores == [] and "imagen" in advertencias[0]


def test_relacion_en_tabla_leida_en_imagen_solo_advierte():
    texto = {"archivo": "x.pdf", "paginas": [{"numero_pdf": 1, "texto": "tabla desordenada por el OCR", "estado": "texto",
                                              "origen_texto": "ocr_previo"}]}
    datos = {"control": {"paginas_revisadas_en_imagen": [1]},
             "obligaciones": [{"id_obligacion": "OBL-001", "fuente": "imagen", "cita_textual": "Nivel limnimétrico lagunas",
                               "pagina_pdf": 1, "citas_adicionales": [], "temas_relacionados": [relacion(palabras_pdf="lagunas")]}]}
    errores, advertencias = [], []
    vo.revisar_temas_relacionados(datos, texto, errores, advertencias, TEMAS)
    assert errores == [] and "imagen" in advertencias[0]


def test_relacion_dudosa_opcional():
    assert revisar_temas(relacion(dudosa=True)) == ([], [])
    errores, _ = revisar_temas(relacion(dudosa="sí"))
    assert any("true o false" in e for e in errores)
