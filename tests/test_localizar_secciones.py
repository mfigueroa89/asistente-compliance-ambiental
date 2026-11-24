"""Pruebas de scripts/localizar_secciones.py.

Primero con textos sintéticos (sin PDF) y luego con las RCAs reales de ejemplos/rcas_publicas/.
"""

from pathlib import Path

import pytest

import leer_pdf
import localizar_secciones as loc

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLOS = RAIZ / "ejemplos" / "rcas_publicas"


def documento(*paginas):
    """Arma un diccionario como el de leer_pdf.py a partir de textos de página."""
    return {
        "archivo": "sintetico.pdf",
        "paginas": [{"numero_pdf": i, "texto": texto} for i, texto in enumerate(paginas, 1)],
    }


def tramos(mapa, clave):
    return [(t["pagina_inicio"], t["pagina_fin"]) for t in mapa["secciones"][clave]["tramos"]]


# ------------------------------------------------------------ sintéticos

def test_rca_moderna_con_considerandos():
    mapa = loc.localizar(documento(
        "REPÚBLICA DE CHILE\n\nVISTOS:\n\n1°. Que, el titular presentó la DIA.",
        "7°. Que, del proceso de evaluación puede concluirse que las siguientes medidas de mitigación son apropiadas "
        "para hacerse cargo de los efectos, características o circunstancias del artículo 11.",
        "Tabla de medidas.",
        "8°. Que, el plan de seguimiento de las variables ambientales relevantes es el siguiente:",
        "9°. Que, para ejecutar el Proyecto deben cumplirse las siguientes condiciones o exigencias:",
        "10° Que, las medidas relevantes del Plan de Prevención de Contingencias son las siguientes:",
        "11°. Que, el Titular deberá informar a la SMA.\n\nRESUELVO:\n\n1. Calificar favorablemente.",
    ))
    # El considerando 7° es de medidas aunque también nombre los efectos del artículo 11.
    assert tramos(mapa, "medidas") == [(2, 4)]
    assert not mapa["secciones"]["efectos_articulo_11"]["encontrada"]
    assert tramos(mapa, "plan_seguimiento") == [(4, 5)]
    assert tramos(mapa, "condiciones_exigencias") == [(5, 6)]
    assert tramos(mapa, "contingencias") == [(6, 7)]
    assert tramos(mapa, "parte_resolutiva") == [(7, 7)]
    assert mapa["secciones"]["medidas"]["confianza"] == "alta"


def test_rca_antigua_con_titulos_numerados_y_ocr():
    mapa = loc.localizar(documento(
        "COMISIÓN REGIONAL DEL MEDIO AMBIENTE",
        "6. Medidas de Mitigación, Reparación y Compensación\n\nEl titular deberá revegetar.",
        "-7. Plan de Seguimiento Ambiental Propuesto en el E.I.A.\n\nMonitoreo trimestral.",
        "Continuación del monitoreo.",
        "1 O. Condiciones o exigencias específicas\n\nEl titular deberá informar.",
        "11. Medidas de Prevención de Riesgo y Control de Accidente",
        "RESUELVE:\n\n1. CALIFICAR FAVORABLEMENTE el proyecto.",
    ))
    assert tramos(mapa, "medidas") == [(2, 3)]
    assert tramos(mapa, "plan_seguimiento") == [(3, 5)]
    assert tramos(mapa, "condiciones_exigencias") == [(5, 6)]  # "1 O." es 10 leído por OCR
    assert tramos(mapa, "contingencias") == [(6, 7)]
    assert tramos(mapa, "parte_resolutiva") == [(7, 7)]  # "RESUELVE" también cuenta


def test_seccion_no_ubicada_avisa_y_propone_paginas():
    mapa = loc.localizar(documento(
        "Identificación del proyecto.",
        "El titular asumió compromisos ambientales voluntarios en la Adenda, que se detallan en el anexo.",
        "RESUELVO: aprobar.",
    ))
    seccion = mapa["secciones"]["compromisos_voluntarios"]
    assert seccion["encontrada"] is False
    assert seccion["paginas_con_menciones"] == [2]
    assert any("No se ubicó la sección \"Compromisos ambientales voluntarios\"" in a and "[2]" in a for a in mapa["avisos"])


def test_no_adivina_si_no_hay_resuelvo():
    mapa = loc.localizar(documento("Texto uno.", "Texto dos.", "Texto tres.", "Texto cuatro."))
    assert mapa["secciones"]["parte_resolutiva"]["encontrada"] is False
    assert any("Parte resolutiva" in a and "[2, 3, 4]" in a for a in mapa["avisos"])


def test_pagina_de_indice_se_ignora():
    indice = "\n\n".join([
        "6. Medidas de mitigación", "7. Plan de seguimiento", "8. Condiciones o exigencias", "9. Plan de contingencias",
    ])
    mapa = loc.localizar(documento(
        "Identificación.", indice, "Texto.",
        "6. Medidas de mitigación, reparación y compensación\n\nEl titular deberá...",
        "RESUELVO",
    ))
    assert mapa["paginas_indice_ignoradas"] == [2]
    assert tramos(mapa, "medidas") == [(4, 5)]


def test_numero_titulo():
    assert loc.numero_titulo("6. Medidas") == 6
    assert loc.numero_titulo("1 O. Condiciones") == 10
    assert loc.numero_titulo("VII. Plan de seguimiento") == 7
    assert loc.numero_titulo("Plan de seguimiento") is None


def test_paginas_para_ficha_son_menos_que_las_de_obligaciones():
    paginas = ["Identificación."] * 3 + ["7°. Que, las siguientes medidas de mitigación son apropiadas:"] + ["Tabla."] * 40
    paginas += ["8°. Que, durante el proceso de participación ciudadana se recibieron observaciones:"] + ["Obs."] * 30
    paginas += ["RESUELVO"]
    mapa = loc.localizar(documento(*paginas))
    assert len(mapa["paginas_para_ficha"]) < 15
    assert set(range(4, 45)) <= set(mapa["paginas_para_obligaciones"])


# ------------------------------------------------------------ RCAs reales

def mapa_real(nombre):
    ruta = EJEMPLOS / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre} en ejemplos/rcas_publicas/")
    return loc.localizar(leer_pdf.leer_pdf(ruta))


def test_queltehue():
    mapa = mapa_real("rca_202513001415_queltehue_rm.pdf")
    assert tramos(mapa, "condiciones_exigencias") == [(66, 70)]
    assert tramos(mapa, "compromisos_voluntarios") == [(70, 85)]  # considerando escrito "9. Que" sin el símbolo °
    assert tramos(mapa, "contingencias") == [(85, 96)]
    assert tramos(mapa, "parte_resolutiva") == [(96, 98)]
    # Es una DIA sin medidas de mitigación: no se inventa la sección.
    assert mapa["secciones"]["medidas"]["encontrada"] is False
    # Sin cambios respecto de la versión 0.2.0 (no retroceso).
    assert tramos(mapa, "efectos_articulo_11") == [(34, 53)]
    assert tramos(mapa, "permisos_sectoriales") == [(53, 57)]
    assert tramos(mapa, "participacion_ciudadana") == [(96, 96)]
    assert tramos(mapa, "plan_seguimiento") == [(96, 96)]
    # Versión 0.4.0: normativa aplicable (considerando 7°) y permisos dentro de las páginas para obligaciones.
    assert tramos(mapa, "normativa_aplicable") == [(57, 66)]
    assert set(range(53, 67)) <= set(mapa["paginas_para_obligaciones"])


def test_arqueros():
    mapa = mapa_real("rca_151_2013_arqueros_atacama.pdf")
    assert tramos(mapa, "medidas") == [(146, 168)]
    assert tramos(mapa, "contingencias") == [(168, 186)]
    assert tramos(mapa, "plan_seguimiento") == [(186, 200)]
    assert tramos(mapa, "condiciones_exigencias") == [(200, 202)]
    assert tramos(mapa, "parte_resolutiva") == [(226, 228)]  # "RESUELVE:"
    assert tramos(mapa, "participacion_ciudadana") == [(41, 65)]
    # Permisos "de carácter ambiental" (D.S. 95/2001), considerando 14; sin el falso positivo de la p. 226.
    assert tramos(mapa, "permisos_sectoriales") == [(209, 225)]
    # La cláusula estándar de seguimiento (considerando 17) queda fuera de toda sección.
    assert [(c["pagina"], c["numero"]) for c in mapa["considerandos_excluidos"]] == [(226, 17)]
    # Compromisos: no hay sección propia, pero se informa la mención aislada de la p. 160.
    compromisos = mapa["secciones"]["compromisos_voluntarios"]
    assert compromisos["encontrada"] is False and 160 in compromisos["paginas_con_menciones"]
    assert any("160" in aviso for aviso in mapa["avisos"])
    assert tramos(mapa, "normativa_aplicable") == [(202, 209)]
    assert set(range(202, 226)) <= set(mapa["paginas_para_obligaciones"])
    # Los considerandos de trámite de la p. 226 los lee la Etapa 4.
    assert 226 in mapa["paginas_para_obligaciones"]


def test_albemarle_ocr():
    mapa = mapa_real("rca_021_2016_albemarle_salar_atacama.pdf")
    assert tramos(mapa, "medidas") == [(51, 53)]
    # Título "-7." con ruido de OCR; la celda "23. LP-24. TB-1 ..." de la p. 58 ya no lo corta (0.4.1).
    assert tramos(mapa, "plan_seguimiento") == [(53, 64)]
    assert tramos(mapa, "condiciones_exigencias") == [(67, 70)]  # título "1 O." por OCR
    assert tramos(mapa, "parte_resolutiva") == [(71, 72)]
    assert tramos(mapa, "contingencias") == [(70, 71)]
    # Considerando 9 con un nombre de proyecto largo entre comillas; termina en el título "1 O." de la misma página.
    assert tramos(mapa, "permisos_sectoriales") == [(67, 67)]
    # Considerando "4. Respecto de las observaciones ciudadanas ..." (sin "Que"), recuperado por hueco: confianza media.
    participacion = mapa["secciones"]["participacion_ciudadana"]
    assert tramos(mapa, "participacion_ciudadana") == [(14, 49)]
    assert participacion["confianza"] == "media" and participacion["tramos"][0]["metodo"] == "considerando_sin_que"
    assert mapa["secciones"]["compromisos_voluntarios"]["encontrada"] is False
    assert tramos(mapa, "normativa_aplicable") == [(64, 67)]


# ------------------------------------------------------------ versión 0.3.0 (sintéticos)

def test_permisos_de_caracter_ambiental_y_compromiso_singular():
    mapa = loc.localizar(documento(
        "1. Que, el titular presentó el EIA.",
        "2. Que, éste requiere para su ejecución los permisos de carácter ambiental de los siguientes artículos 88 y 94.",
        "El titular incluirá como un compromiso voluntario la reforestación.",
        "3. Que, otro tema.\n\nRESUELVE:",
    ))
    assert tramos(mapa, "permisos_sectoriales") == [(2, 4)]  # hasta el considerando 3, en la p. 4
    assert 3 in mapa["secciones"]["compromisos_voluntarios"]["paginas_con_menciones"]


@pytest.mark.parametrize("comillas", [('"', '"'), ("“", "”"), ("«", "»")])
def test_nombre_largo_entre_comillas_no_tapa_el_tema(comillas):
    abre, cierra = comillas
    nombre = "Proyecto de Modificaciones y Mejoramiento del Sistema de Pozas de Evaporación " * 3
    mapa = loc.localizar(documento(
        "1. Que, el titular presentó el EIA.",
        f"2. Que, de acuerdo a los antecedentes del proyecto {abre}{nombre}{cierra}, éste requiere los permisos "
        "de carácter ambiental de los artículos 88 y 94.",
        "3. Que, otro tema.\n\nRESUELVE:",
    ))
    assert tramos(mapa, "permisos_sectoriales") == [(2, 3)]


def test_considerando_sin_que_recuperado_por_hueco_tiene_confianza_media():
    mapa = loc.localizar(documento(
        "3. Que, el proyecto posee las siguientes características.",
        "4. Respecto de las observaciones ciudadanas presentadas, a continuación se presenta su ponderación.",
        "Observación 1.",
        "5. Que, los efectos, características y circunstancias del artículo 11 no se presentan.\n\nRESUELVO",
    ))
    participacion = mapa["secciones"]["participacion_ciudadana"]
    assert tramos(mapa, "participacion_ciudadana") == [(2, 4)]
    assert participacion["confianza"] == "media"
    assert participacion["tramos"][0]["metodo"] == "considerando_sin_que"
    assert participacion["tramos"][0]["confianza"] == "media"
    assert {"pagina": 2, "numero": 4, "metodo": "considerando_sin_que"} in mapa["considerandos_detectados"]
    assert any("sin \"Que\"" in aviso for aviso in mapa["avisos"])


def test_no_recupera_por_hueco_un_subtitulo_ni_un_numero_mayor():
    mapa = loc.localizar(documento(
        "3. Que, el proyecto posee las siguientes características.",
        "4.1. Observaciones ciudadanas de la comunidad.\n\n14. Lista de observaciones ciudadanas.",
        "5. Que, otro tema.\n\nRESUELVO",
    ))
    # Ni "4.1." (subtítulo) ni "14." (otro número) se toman como el considerando 4 que falta.
    assert not any(c["metodo"] == "considerando_sin_que" for c in mapa["considerandos_detectados"])


def test_considerandos_de_tramite_y_clausula_estandar_excluida():
    mapa = loc.localizar(documento(
        "10. Que, las siguientes medidas de mitigación son apropiadas.",
        "11. Que, el Titular deberá remitir a la Superintendencia del Medio Ambiente la información respecto de las "
        "condiciones o exigencias.",
        "12. Que, para el debido y adecuado seguimiento de las condiciones, compromisos o medidas y permisos "
        "ambientales sectoriales aplicables, el Titular deberá remitir los antecedentes.",
        "13. Que, todas las medidas son de responsabilidad del Titular.\n\nRESUELVO",
    ))
    # El considerando 11 nombra "condiciones o exigencias", pero es de trámite: no es sección temática.
    assert not mapa["secciones"]["condiciones_exigencias"]["encontrada"]
    assert not mapa["secciones"]["permisos_sectoriales"]["encontrada"]
    assert tramos(mapa, "otros_tramite") == [(2, 3), (4, 4)]
    assert 2 in mapa["paginas_para_obligaciones"]
    assert [(c["pagina"], c["numero"]) for c in mapa["considerandos_excluidos"]] == [(3, 12)]
    # La sección de trámite es opcional: no genera aviso de "no se ubicó" en otras RCAs.
    assert not any("trámite" in aviso for aviso in mapa["avisos"])


def test_seccion_termina_en_titulo_posterior_de_la_misma_pagina():
    mapa = loc.localizar(documento(
        "8. Que, otro tema.",
        "9. Que, éste requiere los permisos de carácter ambiental de los artículos 88 y 94.\n\n"
        "1 O. Condiciones o exigencias específicas\n\nEl titular deberá informar.",
        "Continuación de condiciones.",
        "11. Que, otro tema.\n\nRESUELVO",
    ))
    assert tramos(mapa, "permisos_sectoriales") == [(2, 2)]


def test_tramo_aislado_de_una_pagina_no_se_lee():
    # Como en un considerando de VISTOS que nombra condiciones: el siguiente considerando está en la misma página.
    paginas = ["1. Que, para ejecutar el Proyecto deben cumplirse las siguientes condiciones o exigencias según el ICE."
               "\n\n2. Que, otro tema."]
    paginas += [f"{n}. Que, otro tema." if n < 9 else "Texto." for n in range(3, 31)]
    paginas += ["30. Que, para ejecutar el Proyecto deben cumplirse las siguientes condiciones o exigencias:",
                "Tabla de condiciones.", "Tabla de condiciones.", "31. Que, otro tema.\n\nRESUELVO"]
    mapa = loc.localizar(documento(*paginas))
    condiciones = mapa["secciones"]["condiciones_exigencias"]
    aislado = condiciones["tramos"][0]
    assert (aislado["pagina_inicio"], aislado["pagina_fin"]) == (1, 1)
    assert aislado["aislado"] is True and aislado["confianza"] == "baja"
    assert condiciones["confianza"] == "alta"  # la del bloque principal
    assert 1 not in mapa["paginas_para_obligaciones"]
    assert {30, 31, 32, 33} <= set(mapa["paginas_para_obligaciones"])
    assert any("tramo aislado en la p. 1" in aviso for aviso in mapa["avisos"])


def test_tramo_de_una_pagina_cercano_no_es_aislado():
    mapa = loc.localizar(documento(
        "5. Que, para ejecutar el Proyecto deben cumplirse las siguientes condiciones o exigencias:",
        "6. Que, otro tema.",
        "7. Que, para ejecutar el Proyecto deben cumplirse las siguientes condiciones o exigencias:",
        "Tabla.", "Tabla.", "8. Que, otro tema.\n\nRESUELVO",
    ))
    assert not any(t.get("aislado") for t in mapa["secciones"]["condiciones_exigencias"]["tramos"])


def test_titulo_con_palabra_partida_por_ocr():
    mapa = loc.localizar(documento(
        "Introducción.",
        "7. Medidas de m itigación, reparación y/o compensación\n\nEl titular deberá revegetar.",
        "8. Plan de seg uim iento ambiental\n\nMonitoreo.",
        "9. Otro título sin tema",
        "RESUELVO",
    ))
    assert tramos(mapa, "medidas") == [(2, 3)]
    assert tramos(mapa, "plan_seguimiento") == [(3, 4)]


def test_comparacion_sin_espacios_solo_si_falla_la_normal():
    # Un título normal no cambia de sección por la comparación sin espacios.
    assert loc.clasificar_titulo("6. Medidas de Mitigación") == ["medidas"]
    assert loc.clasificar_titulo("7. Medidas de m itigación") == ["medidas"]
    assert loc.clasificar_titulo("10. Relación del proyecto con las políticas") == []


def test_normativa_aplicable_no_suma_paginas_a_la_ficha():
    mapa = loc.localizar(documento(
        "Identificación.", "Identificación.", "Identificación.",
        "7°. Que, la forma de cumplimiento de la normativa de carácter ambiental aplicable al Proyecto es la siguiente:",
        "Tabla de normativa.",
        "8°. Que, otro tema.\n\nRESUELVO",
    ))
    assert tramos(mapa, "normativa_aplicable") == [(4, 6)]
    assert {4, 5} <= set(mapa["paginas_para_obligaciones"])
    assert 5 not in mapa["paginas_para_ficha"]


# ------------------------------------------------------------ versión 0.4.1 (sintéticos)

def test_celda_de_tabla_con_codigos_no_es_titulo():
    # "8. LP-24. TB-1" tiene un número cercano a 7, pero son códigos de muestreo: no cierra el plan.
    mapa = loc.localizar(documento(
        "7. Plan de Seguimiento Ambiental",
        "8. LP-24. TB-1. TB-2 Conductividad eléctrica, salinidad",
        "Continuación de la tabla.",
        "9. Otro título del documento\n\nRESUELVO",
    ))
    assert tramos(mapa, "plan_seguimiento") == [(1, 4)]
    assert loc.PATRON_CODIGO_TABLA.match("23. LP-24. TB-1. TB-2 Conductividad")
    assert not loc.PATRON_CODIGO_TABLA.match("8. Normativa aplicable")


def test_titulo_sin_tema_con_numero_lejano_no_cierra_la_seccion():
    mapa = loc.localizar(documento(
        "7. Plan de Seguimiento Ambiental",
        "23. Puntos de muestreo en lagunas",  # número lejano y sin tema: no corta
        "8. Otro título del documento",        # número cercano: corta
        "Texto.\n\nRESUELVO",
    ))
    assert tramos(mapa, "plan_seguimiento") == [(1, 3)]
