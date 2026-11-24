"""Pruebas de scripts/validar_ficha.py y scripts/mostrar_paginas.py."""

import copy

import mostrar_paginas
import validar_ficha as vf

TEXTO = {
    "archivo": "rca_prueba.pdf",
    "paginas": [
        {"numero_pdf": 1, "origen_texto": "digital", "escaneada": False,
         "texto": "Califica Ambientalmente el proyecto “Parque Solar Ejemplo”\n\nResolución Exenta N° <NUM_RES>\n\n"
                  "en el D.S. Nº 40, de 30 de octubre de 2012, del Ministerio del Medio Ambiente"},
        {"numero_pdf": 2, "origen_texto": "digital", "escaneada": False,
         "texto": "El Proyecto se ubica en la comuna de Calera de Tango, Región Metropolitana de Santiago."},
        {"numero_pdf": 3, "origen_texto": "ocr_previo", "escaneada": False,
         "texto": "Servido de Evaluaci6n Ambiental. Vida útil de 30 años."},
        {"numero_pdf": 4, "origen_texto": "digital", "escaneada": False,
         "texto": "5.3. REASENTAMIENTO. No se evidencia que el Proyecto genere efectos del artículo 11 de la Ley, "
                  "de acuerdo al artículo 7º del RSEIA.\n\n8°. Que, para ejecutar el Proyecto deben cumplirse "
                  "las siguientes condiciones o exigencias"},
    ],
}

SECCIONES = {
    "secciones": {
        "condiciones_exigencias": {"tramos": [{"pagina_inicio": 4, "pagina_fin": 4}]},
        "compromisos_voluntarios": {"tramos": []},
        "contingencias": {"tramos": []},
    }
}


DS40 = "D.S. N° 40/2012, Ministerio del Medio Ambiente"
DS95 = "D.S. N° 95/2001, Ministerio Secretaría General de la Presidencia"


def dato(valor, pagina, cita, fuente="texto"):
    return {"valor": valor, "pagina_pdf": pagina, "cita_textual": cita, "fuente": fuente}


def ficha_valida():
    ficha = copy.deepcopy(vf.cargar_plantilla())
    ficha["archivo"] = "rca_prueba.pdf"
    campos = ficha["campos"]
    campos["nombre_proyecto"] = dato("Parque Solar Ejemplo", 1, "Califica Ambientalmente el proyecto “Parque Solar Ejemplo”")
    campos["numero_resolucion"] = dato("123", 1, "Resolución Exenta N° 123", fuente="imagen")
    campos["comuna"] = [dato("Calera de Tango", 2, "comuna de Calera de Tango")]
    campos["reglamento_aplicable"] = dato(DS40, 1, "en el D.S. Nº 40, de 30 de octubre de 2012, del Ministerio del Medio Ambiente")
    campos["vida_util"] = dato("30 años", 3, "Vida útil de 30 años", fuente="ocr_previo")
    for campo in vf.CAMPOS_CON_RANGO:
        campos[campo]["rango_localizador"] = "No ubicada"
    ficha["control"]["paginas_totales"] = 4
    ficha["control"]["campos_no_consta"] = sorted(
        c for c, v in campos.items() if v == [] or (isinstance(v, dict) and v["valor"] == "No consta")
    )
    return ficha


def test_ficha_valida_sin_errores():
    errores, advertencias, informe = vf.validar(ficha_valida(), TEXTO)
    assert errores == []
    # El dato leído en imagen y la cita de OCR quedan como advertencias para revisar.
    assert any("numero_resolucion" in a and "imagen" in a for a in advertencias)
    assert informe["resumen"]["confirmada"] >= 2


def test_detecta_cita_inventada_y_pagina_inexistente():
    ficha = ficha_valida()
    ficha["campos"]["titular"] = dato("Ejemplo SpA", 2, "titular Ejemplo SpA")
    ficha["campos"]["region"] = [dato("Región de Atacama", 9, "Región de Atacama")]
    ficha["control"]["campos_no_consta"].remove("titular")
    ficha["control"]["campos_no_consta"].remove("region")
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any("titular" in e and "no se encontró" in e for e in errores)
    assert any("region" in e and "no existe" in e for e in errores)


def test_detecta_no_consta_mal_declarado_y_fuente_incorrecta():
    ficha = ficha_valida()
    ficha["control"]["campos_no_consta"].remove("monto_inversion")  # falta declararlo
    ficha["campos"]["vida_util"]["fuente"] = "texto"  # la página 3 tiene OCR previo
    ficha["campos"]["fecha_resolucion"] = dato("20 de noviembre de 2025", 1, "Califica Ambientalmente")
    ficha["control"]["campos_no_consta"].remove("fecha_resolucion")
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any("campos_no_consta" in e and "monto_inversion" in e for e in errores)
    assert any("vida_util" in e and "OCR previo" in e for e in errores)
    assert any("fecha_resolucion" in e and "AAAA-MM-DD" in e for e in errores)


def test_detecta_campos_faltantes_y_aviso():
    ficha = ficha_valida()
    del ficha["campos"]["decision"]
    ficha["aviso"] = ""
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any(e.startswith("decision: falta el campo") for e in errores)
    assert any(e.startswith("aviso") for e in errores)


def test_mostrar_paginas_rango_y_busqueda():
    assert mostrar_paginas.parsear_rango("1-2, 3, 9", 3) == [1, 2, 3]
    assert mostrar_paginas.comprimir_rango([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    salida = mostrar_paginas.mostrar(TEXTO, [3])
    assert "Página PDF 3" in salida and "OCR PREVIO" in salida
    hallazgos = mostrar_paginas.buscar(TEXTO, ["vida util", "calera"])
    assert [a["pagina"] for a in hallazgos["vida util"]] == [3]
    assert [a["pagina"] for a in hallazgos["calera"]] == [2]


# --- Equivalencia legal del artículo 11 (letra_equivalente) ---

def efecto(letra_equivalente):
    elemento = dato("Reasentamiento (5.3): descartado", 4,
                    "No se evidencia que el Proyecto genere efectos del artículo 11 de la Ley, de acuerdo al artículo 7º del RSEIA.")
    elemento["letra_equivalente"] = letra_equivalente
    return elemento


def equivalente(valor, fuente="equivalencia_legal"):
    return {"valor": valor, "pagina_pdf": None, "cita_textual": None, "fuente": fuente}


def test_tablas_de_equivalencias_por_reglamento_en_config():
    reglamentos = vf.cargar_reglamentos()
    assert reglamentos[DS40] == {"a": 5, "b": 6, "c": 7, "d": 8, "e": 9, "f": 10}
    # En el D.S. 95/2001 el artículo 7 trata las normas de referencia: c) a f) se corren en uno.
    assert reglamentos[DS95] == {"a": 5, "b": 6, "c": 8, "d": 9, "e": 10, "f": 11}


def test_letra_equivalente_valida_coincide_con_el_articulo_citado():
    ficha = ficha_valida()
    ficha["campos"]["efectos_articulo_11"] = [efecto(equivalente(f"letra c) (artículo 7 del {DS40})"))]
    ficha["control"]["campos_no_consta"].remove("efectos_articulo_11")
    errores, advertencias, informe = vf.validar(ficha, TEXTO)
    assert errores == []
    # La equivalencia no tiene cita, así que no se cuenta como cita por verificar.
    assert all("letra_equivalente" not in c["campo"] for c in informe["citas"])


def test_letra_equivalente_contradictoria_falta_o_con_fuente_incorrecta():
    for elemento, esperado in [
        (efecto(equivalente(f"letra d) (artículo 8 del {DS40})")), "contradice"),
        (efecto(equivalente(f"letra c) (artículo 7 del {DS40})", fuente="texto")), "equivalencia_legal"),
        (efecto(equivalente(f"letra c) (artículo 8 del {DS95})")), "no está en la tabla"),
        (efecto(None), "falta"),
    ]:
        ficha = ficha_valida()
        ficha["campos"]["efectos_articulo_11"] = [elemento]
        ficha["control"]["campos_no_consta"].remove("efectos_articulo_11")
        errores, _, _ = vf.validar(ficha, TEXTO)
        assert any("letra_equivalente" in e and esperado in e for e in errores), (esperado, errores)


def test_letra_equivalente_sin_respaldo_en_el_efecto_es_advertencia():
    ficha = ficha_valida()
    elemento = dato("Reasentamiento: descartado", 4, "No se evidencia que el Proyecto genere efectos del artículo 11 de la Ley")
    elemento["letra_equivalente"] = equivalente(f"letra c) (artículo 7 del {DS40})")
    ficha["campos"]["efectos_articulo_11"] = [elemento]
    ficha["control"]["campos_no_consta"].remove("efectos_articulo_11")
    errores, advertencias, _ = vf.validar(ficha, TEXTO)
    assert errores == []
    assert any("letra_equivalente" in a and "no se apoya" in a for a in advertencias)


def test_menciones_articulo_11_por_letra_y_por_articulo():
    equivalencias = vf.cargar_reglamentos()[DS40]
    assert vf.menciones_articulo_11("Letra a), riesgo para la salud", equivalencias) == {"a"}
    assert vf.menciones_articulo_11("de acuerdo al artículo 9º del Reglamento del SEIA", equivalencias) == {"e"}
    assert vf.menciones_articulo_11("artículo 10 del RSEIA", equivalencias) == {"f"}
    assert vf.menciones_articulo_11("artículo 25 de la Ley N°19.300", equivalencias) == set()


# --- Condiciones, compromisos y contingencias con rango del localizador ---

def test_hay_condiciones_con_rango_del_localizador():
    ficha = ficha_valida()
    condiciones = dato("sí", 4, "deben cumplirse las siguientes condiciones o exigencias")
    condiciones["rango_localizador"] = "4"
    ficha["campos"]["hay_condiciones_exigencias"] = condiciones
    ficha["control"]["campos_no_consta"].remove("hay_condiciones_exigencias")
    errores, advertencias, _ = vf.validar(ficha, TEXTO, SECCIONES)
    assert errores == []
    assert not any("hay_condiciones_exigencias" in a for a in advertencias)


def test_rango_localizador_faltante_o_distinto_del_localizador():
    ficha = ficha_valida()
    ficha["campos"]["hay_compromisos_voluntarios"]["rango_localizador"] = None
    ficha["campos"]["hay_plan_contingencias"]["rango_localizador"] = "10-12"
    errores, _, _ = vf.validar(ficha, TEXTO, SECCIONES)
    assert any("hay_compromisos_voluntarios" in e and "falta rango_localizador" in e for e in errores)
    assert any("hay_plan_contingencias" in e and "no coincide" in e for e in errores)


def test_cita_fuera_del_rango_del_localizador_es_advertencia_y_valor_no_permitido_es_error():
    ficha = ficha_valida()
    condiciones = dato("sí", 2, "comuna de Calera de Tango")
    condiciones["rango_localizador"] = "4"
    ficha["campos"]["hay_condiciones_exigencias"] = condiciones
    contingencias = dato("tal vez", 4, "deben cumplirse las siguientes condiciones o exigencias")
    contingencias["rango_localizador"] = "No ubicada"
    ficha["campos"]["hay_plan_contingencias"] = contingencias
    ficha["control"]["campos_no_consta"].remove("hay_condiciones_exigencias")
    ficha["control"]["campos_no_consta"].remove("hay_plan_contingencias")
    errores, advertencias, _ = vf.validar(ficha, TEXTO, SECCIONES)
    assert any("hay_condiciones_exigencias" in a and "fuera del rango" in a for a in advertencias)
    assert any("hay_plan_contingencias" in e and "no permitido" in e for e in errores)


def test_rango_de_seccion():
    assert vf.rango_de_seccion(SECCIONES, "condiciones_exigencias") == "4"
    assert vf.rango_de_seccion(SECCIONES, "contingencias") == "No ubicada"
    dos_tramos = {"secciones": {"x": {"tramos": [{"pagina_inicio": 5, "pagina_fin": 9}, {"pagina_inicio": 20, "pagina_fin": 20}]}}}
    assert vf.rango_de_seccion(dos_tramos, "x") == "5-9, 20"


def test_menciones_segun_reglamento_cambian_la_letra():
    reglamentos = vf.cargar_reglamentos()
    assert vf.menciones_articulo_11("artículo 8 del Reglamento", reglamentos[DS40]) == {"d"}
    assert vf.menciones_articulo_11("artículo 8 del Reglamento", reglamentos[DS95]) == {"c"}


def test_reglamento_no_identificado_o_tabla_vacia_solo_advierte(tmp_path, monkeypatch):
    # Sin reglamento: advertencia, nunca error, aunque haya letra_equivalente.
    ficha = ficha_valida()
    ficha["campos"]["reglamento_aplicable"] = {"valor": "No consta", "pagina_pdf": None, "cita_textual": None, "fuente": None}
    ficha["control"]["campos_no_consta"].append("reglamento_aplicable")
    ficha["campos"]["efectos_articulo_11"] = [efecto(equivalente(f"letra c) (artículo 7 del {DS40})"))]
    ficha["control"]["campos_no_consta"].remove("efectos_articulo_11")
    errores, advertencias, _ = vf.validar(ficha, TEXTO)
    assert errores == []
    assert any(a.startswith("reglamento_aplicable") and "no identifica" in a for a in advertencias)
    # Reglamento con tabla vacía (no verificada): también solo advierte.
    tabla = tmp_path / "equivalencias.yaml"
    tabla.write_text("reglamentos:\n  - nombre: \"D.S. N° 40/2012, Ministerio del Medio Ambiente\"\n    equivalencias: []\n", encoding="utf-8")
    monkeypatch.setattr(vf, "EQUIVALENCIAS", tabla)
    ficha = ficha_valida()
    ficha["campos"]["efectos_articulo_11"] = [efecto(equivalente(f"letra c) (artículo 7 del {DS40})"))]
    ficha["control"]["campos_no_consta"].remove("efectos_articulo_11")
    errores, advertencias, _ = vf.validar(ficha, TEXTO)
    assert errores == []
    assert any("tabla" in a and "vacía" in a for a in advertencias)


def test_letra_equivalente_de_otro_reglamento_es_error():
    ficha = ficha_valida()
    # La ficha dice D.S. 40/2012, pero la equivalencia usa la tabla del D.S. 95/2001.
    ficha["campos"]["efectos_articulo_11"] = [efecto(equivalente(f"letra c) (artículo 8 del {DS95})"))]
    ficha["control"]["campos_no_consta"].remove("efectos_articulo_11")
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any("letra_equivalente" in e and "no está en la tabla" in e for e in errores)


def test_categoria_de_areas_protegidas():
    ficha = ficha_valida()
    area = dato("Humedal de ejemplo", 2, "comuna de Calera de Tango")
    ficha["campos"]["areas_protegidas_o_sensibles"] = [area]
    ficha["control"]["campos_no_consta"].remove("areas_protegidas_o_sensibles")
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any("categoria" in e for e in errores)
    area["categoria"] = "humedal"
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert errores == []


def test_plantilla_sin_representante_legal_y_con_reglamento():
    campos = vf.cargar_plantilla()["campos"]
    assert "representante_legal" not in campos
    assert "reglamento_aplicable" in campos


def test_si_con_nota_aceptado_en_campos_si_no():
    ficha = ficha_valida()
    nota = dato("sí: mención aislada dentro de medidas, sin sección propia", 4, "deben cumplirse las siguientes condiciones o exigencias")
    nota["rango_localizador"] = "No ubicada"
    ficha["campos"]["hay_compromisos_voluntarios"] = nota
    ficha["control"]["campos_no_consta"].remove("hay_compromisos_voluntarios")
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert errores == []
    nota["valor"] = "quizás: algo"
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any("hay_compromisos_voluntarios" in e and "no permitido" in e for e in errores)


def test_marcas_de_calidad_ocr():
    ficha = ficha_valida()
    ficha["campos"]["vida_util"]["correccion_ocr"] = "el OCR dice \"3O\"; la imagen dice \"30\""
    ficha["control"]["paginas_revisadas_en_imagen"] = [3]
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert errores == []
    ficha["campos"]["comuna"][0]["correccion_ocr"] = "no corresponde: la página es digital"
    ficha["control"]["paginas_revisadas_en_imagen"] = [3, 99]
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert any("comuna" in e and "correccion_ocr" in e for e in errores)
    assert any("paginas_revisadas_en_imagen" in e for e in errores)


def test_paginas_no_leidas():
    ficha = ficha_valida()
    ficha["control"]["paginas_no_leidas"] = [{"pagina": 3, "seccion": "medidas", "motivo": "ilegible"}]
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert errores == []
    ficha["control"]["paginas_no_leidas"] = [{"pagina": 30, "seccion": "medidas", "motivo": "ilegible"}, {"pagina": 3}]
    errores, _, _ = vf.validar(ficha, TEXTO)
    assert len([e for e in errores if "paginas_no_leidas" in e]) == 2


def test_rango_de_seccion_ignora_tramos_aislados():
    secciones = {"secciones": {"x": {"tramos": [{"pagina_inicio": 2, "pagina_fin": 2, "aislado": True},
                                                {"pagina_inicio": 93, "pagina_fin": 99}]}}}
    assert vf.rango_de_seccion(secciones, "x") == "93-99"
