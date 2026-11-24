"""Pruebas de scripts/exportar_excel.py, con un PDF, un texto y una ficha sintéticos."""

import copy
import json

import pymupdf
from openpyxl import load_workbook

import exportar_excel as ee
import validar_ficha as vf
import validar_obligaciones as vo
from leer_pdf import calcular_sha256

TEXTO_PAGINA = "Resolución Exenta N° 123\nEl Proyecto se ubica en la comuna de Calera de Tango."


def preparar(tmp_path, cambiar_pdf=False, manifiesto=None):
    """Crea rcas/a.pdf (con ficha) y rcas/b.pdf (sin ficha), sus JSON en salida/ y el manifiesto."""
    rcas, salida = tmp_path / "rcas", tmp_path / "salida"
    for carpeta in (rcas, salida / "fichas", salida / "texto"):
        carpeta.mkdir(parents=True)
    for nombre in ("a.pdf", "b.pdf"):
        documento = pymupdf.open()
        documento.new_page().insert_text((72, 72), f"{nombre} {TEXTO_PAGINA}")
        documento.save(rcas / nombre)
    texto = {"archivo": "a.pdf", "paginas": [
        {"numero_pdf": 1, "origen_texto": "ocr_previo", "escaneada": False, "texto": TEXTO_PAGINA}]}
    (salida / "texto" / "a.json").write_text(json.dumps(texto), encoding="utf-8")

    ficha = copy.deepcopy(vf.cargar_plantilla())
    ficha.update(archivo="a.pdf", sha256=calcular_sha256(rcas / "a.pdf"))
    campos = ficha["campos"]
    campos["numero_resolucion"] = {"valor": "123", "pagina_pdf": 1, "cita_textual": "Resolución Exenta N° 123",
                                   "fuente": "ocr_previo"}
    campos["fecha_resolucion"] = {"valor": "2025-11-20", "pagina_pdf": 1, "cita_textual": "Resolución Exenta N° 123",
                                  "fuente": "ocr_previo", "correccion_ocr": "el OCR dice \"2O\"; la imagen dice \"20\""}
    campos["comuna"] = [{"valor": "Calera de Tango", "pagina_pdf": 1, "cita_textual": "comuna de Calera de Tango",
                         "fuente": "ocr_previo"}]
    ficha["control"]["paginas_revisadas_en_imagen"] = [1]
    ficha["control"]["paginas_no_leidas"] = [{"pagina": 1, "seccion": "medidas", "motivo": "ilegible"}]
    (salida / "fichas" / "a.json").write_text(json.dumps(ficha), encoding="utf-8")
    obligacion = copy.deepcopy(vo.cargar_plantilla()["modelo_obligacion"])
    obligacion.update(id_obligacion="OBL-001", tipo="reporte o informe a la autoridad", descripcion="Informar a la SMA.",
                      autoridad_destinataria="SMA", pagina_pdf=1, cita_textual="Resolución Exenta N° 123", confianza="media",
                      posible_duplicado=["OBL-002"])
    (salida / "obligaciones").mkdir()
    (salida / "obligaciones" / "a.json").write_text(json.dumps(
        {"archivo": "a.pdf", "sha256": ficha["sha256"], "obligaciones": [obligacion]}), encoding="utf-8")
    if cambiar_pdf:
        documento = pymupdf.open()
        documento.new_page().insert_text((72, 72), "versión distinta")
        documento.save(rcas / "a.pdf")

    ruta_manifiesto = tmp_path / "manifiesto.csv"
    ruta_manifiesto.write_text(manifiesto or (
        "archivo;unidad_fiscalizable;id_uf_snifa;enlace_uf_snifa;proyecto\n"
        "a.pdf;UF Uno;1;https://snifa.sma.gob.cl/UnidadFiscalizable/Ficha/1;Proyecto A\n"
        "a.pdf;UF Dos;;;Proyecto A\n"
        "b.pdf;UF Uno;1;;Proyecto B\n"), encoding="utf-8")
    return ruta_manifiesto, rcas, salida


def filas(hoja):
    encabezado = [c.value for c in hoja[1]]
    return [dict(zip(encabezado, fila)) for fila in hoja.iter_rows(min_row=2, values_only=True)]


def test_hojas_aviso_y_sin_celdas_vacias(tmp_path):
    destino, resumen = ee.exportar(*preparar(tmp_path))
    libro = load_workbook(destino)
    assert libro.sheetnames == ["Léeme", "Índice UF", "Resumen", "Obligaciones", "Obligaciones detalle", "Fichas",
                               "Menciones en texto"]
    assert libro["Léeme"]["A2"].value == ee.AVISO
    for nombre in ("Índice UF", "Resumen", "Obligaciones", "Obligaciones detalle", "Fichas", "Menciones en texto"):
        for fila in libro[nombre].iter_rows():
            assert all(celda.value not in (None, "") for celda in fila), nombre
    assert resumen["estados"] == {"a.pdf": "al día", "b.pdf": "sin ficha (falta fichar)"}


def test_fichas_valor_pagina_cita_fuente_y_marcas(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    datos = filas(load_workbook(destino)["Fichas"])
    numero = next(d for d in datos if d["campo"] == "numero_resolucion" and d["unidad_fiscalizable"] == "UF Uno"
                  and d["archivo"] == "a.pdf")
    assert (numero["valor"], numero["pagina_pdf"], numero["cita_textual"], numero["fuente"]) == (
        "123", 1, "Resolución Exenta N° 123", "ocr_previo")
    assert numero["calidad"] == "OCR confirmado en la imagen" and numero["verificacion"] == "confirmada"
    fecha = next(d for d in datos if d["campo"] == "fecha_resolucion" and d["archivo"] == "a.pdf")
    assert fecha["calidad"].startswith("OCR corregido según la imagen")
    titular = next(d for d in datos if d["campo"] == "titular" and d["archivo"] == "a.pdf")
    assert titular["valor"] == "No consta" and titular["pagina_pdf"] == "—"
    fases = next(d for d in datos if d["campo"] == "fases" and d["archivo"] == "a.pdf")
    assert fases["valor"] == "No consta (lista vacía)"
    assert any(d["campo"] == "paginas_no_leidas" and d["pagina_pdf"] == 1 for d in datos)


def test_muchos_a_muchos_repite_filas_por_unidad(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    libro = load_workbook(destino)
    datos = filas(libro["Fichas"])
    por_uf = {uf: sum(1 for d in datos if d["archivo"] == "a.pdf" and d["unidad_fiscalizable"] == uf)
              for uf in ("UF Uno", "UF Dos")}
    assert por_uf["UF Uno"] == por_uf["UF Dos"] > 30
    indice = {d["unidad_fiscalizable"]: d for d in filas(libro["Índice UF"])}
    assert indice["UF Uno"]["cantidad_rcas"] == 2 and indice["UF Dos"]["cantidad_rcas"] == 1
    assert indice["UF Uno"]["paginas_no_leidas"] == 1
    resumen = {d["archivo"]: d for d in filas(libro["Resumen"])}
    assert resumen["a.pdf"]["unidades_fiscalizables"] == "UF Uno; UF Dos"
    assert resumen["b.pdf"]["numero_resolucion"] == "No consta"


def test_pdf_cambiado_marca_ficha_desactualizada(tmp_path):
    destino, resumen = ee.exportar(*preparar(tmp_path, cambiar_pdf=True))
    assert resumen["estados"]["a.pdf"].startswith("DESACTUALIZADA")
    leeme = [c.value for fila in load_workbook(destino)["Léeme"].iter_rows() for c in fila if c.value]
    assert any("a.pdf" in str(v) and "DESACTUALIZADA" in str(v) for v in leeme)


def test_el_excel_se_regenera_completo(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    ee.exportar(manifiesto, rcas, salida)
    manifiesto.write_text("archivo,unidad_fiscalizable,proyecto\nb.pdf,UF Tres,Proyecto B\n", encoding="utf-8")
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    unidades = {d["unidad_fiscalizable"] for d in filas(load_workbook(destino)["Índice UF"])}
    # No quedan restos del Excel anterior (UF Uno, UF Dos); a.pdf quedó sin fila y aparece sin unidad.
    assert unidades == {"UF Tres", "SIN UF ASIGNADA"}


def test_hoja_obligaciones_marca_calidad_del_ocr(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    ruta = salida / "obligaciones" / "a.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["obligaciones"][0]["fuente"] = "ocr_previo"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    assert filas(load_workbook(destino)["Obligaciones detalle"])[0]["calidad"] == "Solo OCR (imagen no revisada)"
    datos["control"] = {"paginas_revisadas_en_imagen": [1]}
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    assert filas(load_workbook(destino)["Obligaciones detalle"])[0]["calidad"] == "OCR confirmado en la imagen"


def test_hoja_obligaciones_con_estado_de_cita_y_conteo(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    libro = load_workbook(destino)
    datos = filas(libro["Obligaciones detalle"])
    de_a = [d for d in datos if d["archivo"] == "a.pdf"]
    assert {d["unidad_fiscalizable"] for d in de_a} == {"UF Uno", "UF Dos"}  # se repite por unidad
    assert de_a[0]["estado_verificacion"] == "confirmada" and de_a[0]["confianza"] == "media"
    assert de_a[0]["posible_duplicado"] == "OBL-002"
    sin = next(d for d in datos if d["archivo"] == "b.pdf")
    assert sin["descripcion"].startswith("No consta")
    indice = {d["unidad_fiscalizable"]: d for d in filas(libro["Índice UF"])}
    assert indice["UF Dos"]["obligaciones_filas_totales"] == 1
    assert indice["UF Uno"]["obligaciones_filas_totales"] == "1 (faltan RCAs por extraer)"


def test_duplicados_y_obligaciones_distintas():
    lista = [{"id_obligacion": "OBL-001", "posible_duplicado": ["OBL-003"]},
             {"id_obligacion": "OBL-002", "posible_duplicado": []},
             {"id_obligacion": "OBL-003", "posible_duplicado": ["OBL-001", "OBL-004"]},
             {"id_obligacion": "OBL-004", "posible_duplicado": ["OBL-003"]}]
    grupos = ee.grupos_de_duplicados(lista)
    assert grupos == {"OBL-001": "OBL-001", "OBL-002": "OBL-002", "OBL-003": "OBL-001", "OBL-004": "OBL-001"}
    assert ee.conteo_obligaciones({"obligaciones": {"obligaciones": lista}}) == (4, 2)


def test_enlace_eseia_en_resumen_y_nota_uf_en_indice(tmp_path):
    manifiesto = ("archivo,unidad_fiscalizable,proyecto,enlace_eseia,nota_uf\n"
                  "a.pdf,UF Uno,Proyecto A,https://seia.sea.gob.cl/expediente/ficha/fichaPrincipal.php?id_expediente=1,\n"
                  "b.pdf,,Proyecto B,,No encontrada en SNIFA al 2026-11-23.\n")
    destino, _ = ee.exportar(*preparar(tmp_path, manifiesto=manifiesto))
    libro = load_workbook(destino)
    hoja = libro["Resumen"]
    columna = [c.value for c in hoja[1]].index("enlace_eseia")
    celdas = {fila[2].value: fila[columna] for fila in hoja.iter_rows(min_row=2)}
    assert celdas["a.pdf"].hyperlink.target == celdas["a.pdf"].value
    assert celdas["b.pdf"].value == "—" and celdas["b.pdf"].hyperlink is None
    indice = {d["unidad_fiscalizable"]: d for d in filas(libro["Índice UF"])}
    assert indice["SIN UF ASIGNADA"]["nota_uf"] == "No encontrada en SNIFA al 2026-11-23."
    assert indice["UF Uno"]["nota_uf"] == "—"


def test_manifiesto_viejo_sin_columnas_nuevas(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    libro = load_workbook(destino)
    assert {d["enlace_eseia"] for d in filas(libro["Resumen"])} == {"—"}
    assert {d["nota_uf"] for d in filas(libro["Índice UF"])} == {"—"}


def test_temas_en_obligaciones_y_hoja_de_menciones(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    ruta_texto = salida / "texto" / "a.json"
    texto = json.loads(ruta_texto.read_text(encoding="utf-8"))
    texto["paginas"][0]["texto"] += " Se protegerá el humedal norte. El bofedal del sector se describe aquí."
    texto["paginas"].append({"numero_pdf": 2, "origen_texto": "digital", "estado": "escaneada", "escaneada": True, "texto": ""})
    ruta_texto.write_text(json.dumps(texto), encoding="utf-8")
    ruta_obligaciones = salida / "obligaciones" / "a.json"
    datos = json.loads(ruta_obligaciones.read_text(encoding="utf-8"))
    obligacion = datos["obligaciones"][0]
    obligacion["citas_adicionales"] = [{"pagina_pdf": 1, "cita_textual": "Se protegerá el humedal norte."}]
    obligacion["temas_relacionados"] = [{"tema": "flora_y_fauna", "justificacion": "Se refiere a «humedal norte».",
                                         "palabras_pdf": "humedal norte", "pagina_pdf": 1, "estado": "revisar", "dudosa": True}]
    ruta_obligaciones.write_text(json.dumps(datos), encoding="utf-8")
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    libro = load_workbook(destino)
    fila = next(d for d in filas(libro["Obligaciones detalle"]) if d["archivo"] == "a.pdf")
    assert fila["temas_literales"] == "humedales"
    assert fila["temas_relacionados"] == "flora_y_fauna [revisar] (dudosa): Se refiere a «humedal norte». (p. 1)"
    menciones = [d for d in filas(libro["Menciones en texto"]) if d["archivo"] == "a.pdf" and d["unidad_fiscalizable"] == "UF Uno"]
    por_termino = {d["termino"]: d for d in menciones}
    assert por_termino["humedal"]["recogido_en_obligacion"] == "OBL-001"
    assert por_termino["bofedal"]["recogido_en_obligacion"] == "no"
    assert any(d["pagina_pdf"] == 2 and d["recogido_en_obligacion"] == "no revisada" for d in menciones)


# --------------------------------------------------------------------------- hoja Consulta (Etapa 6)

import buscar_palabras as bp


def guardar_consulta(salida, consulta, temas, marca, en_excel=True):
    """Ejecuta buscar_palabras.consultar sobre los datos sintéticos de preparar() y lo guarda con fecha y hora fijas.
    en_excel=True simula una consulta que el usuario ya pidió agregar al Excel."""
    rca = bp.cargar_rca("a.pdf", salida)
    resultado = bp.consultar(consulta, [rca], temas)
    resultado["fecha_hora"] = marca
    resultado["en_excel"] = en_excel
    (salida / "consultas").mkdir(exist_ok=True)
    nombre = f"consulta_{bp.nombre_seguro(consulta)}_{marca.replace('-', '').replace(':', '').replace(' ', '-')}.json"
    (salida / "consultas" / nombre).write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return resultado


def test_hoja_consulta_historial_mas_reciente_arriba_y_sin_resultados(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    ruta_texto = salida / "texto" / "a.json"
    texto = json.loads(ruta_texto.read_text(encoding="utf-8"))
    texto["paginas"][0]["texto"] += " El bofedal del sector se describe aquí."
    ruta_texto.write_text(json.dumps(texto), encoding="utf-8")
    temas = bp.cargar_temas()
    guardar_consulta(salida, "humedales", temas, "2026-11-23 10:00:00")
    sin = guardar_consulta(salida, "glaciares", temas, "2026-11-23 12:00:00")
    assert sin["sin_resultados"] is True

    destino, _ = ee.exportar(manifiesto, rcas, salida)
    libro = load_workbook(destino)
    assert libro.sheetnames[-1] == "Consulta"
    datos = filas(libro["Consulta"])
    assert [c.value for c in libro["Consulta"][1]][:5] == ["consulta", "fecha_hora", "filtro", "alcance", "categoria"]
    # La más reciente (glaciares, 12:00) arriba; sin resultados, con su alcance.
    assert datos[0]["consulta"].startswith("glaciares") and datos[0]["fecha_hora"] == "2026-11-23 12:00:00"
    assert datos[0]["categoria"] == ee.SIN_RESULTADOS
    assert datos[0]["descripcion"] == "No hay resultados para «glaciares» en el alcance indicado."
    assert datos[0]["alcance"].startswith("Alcance: 1 RCA(s) y 1 obligaciones buscadas.")
    # Después, humedales (10:00): la mención del bofedal.
    assert [d["categoria"] for d in datos[1:]] == [bp.MENCION]
    assert datos[1]["termino_encontrado"] == "bofedal" and datos[1]["fecha_hora"] == "2026-11-23 10:00:00"
    for fila in libro["Consulta"].iter_rows():
        assert all(celda.value not in (None, "") for celda in fila)


def test_sin_consultas_no_hay_hoja_consulta(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    assert "Consulta" not in load_workbook(destino).sheetnames


def test_consulta_danada_se_avisa_y_no_detiene(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    (salida / "consultas").mkdir()
    (salida / "consultas" / "consulta_x_20261123-100000.json").write_text("{no es json", encoding="utf-8")
    destino, resumen = ee.exportar(manifiesto, rcas, salida)
    assert "Consulta" not in load_workbook(destino).sheetnames
    assert any("consulta_x_20261123-100000.json" in a for a in resumen["avisos"])


def test_consulta_dice_que_se_busco_y_el_filtro():
    assert ee.texto_de_que({"consulta": "turbera", "tema": None, "tema_del_termino": "humedales"}) == \
        "turbera (término del tema humedales, buscado solo)"
    assert ee.texto_de_que({"consulta": "pajonal", "tema": None}) == "pajonal (término libre)"
    assert ee.texto_filtro({"filtro": {"unidad_fiscalizable": None, "archivos_pedidos": None, "archivos": ["a", "b"]}}) == \
        "Todas las RCAs procesadas (2)"
    assert ee.texto_filtro({"filtro": {"unidad_fiscalizable": None, "archivos_pedidos": ["a.pdf"], "archivos": ["a.pdf"]}}) == \
        "RCAs: a.pdf"
    assert ee.texto_filtro({}).startswith("No consta")


# --------------------------------------------------------------------------- Consulta solo a pedido (2026-11-24)

def ruta_consulta(salida, consulta, marca):
    return salida / "consultas" / f"consulta_{bp.nombre_seguro(consulta)}_{marca.replace('-', '').replace(':', '').replace(' ', '-')}.json"


def test_consulta_no_pedida_no_entra_en_el_excel(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    temas = bp.cargar_temas()
    guardar_consulta(salida, "humedales", temas, "2026-11-24 10:00:00", en_excel=False)
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    assert "Consulta" not in load_workbook(destino).sheetnames


def test_agregar_consulta_la_incluye_y_la_marca(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    temas = bp.cargar_temas()
    guardar_consulta(salida, "humedales", temas, "2026-11-24 10:00:00", en_excel=False)
    guardar_consulta(salida, "glaciares", temas, "2026-11-24 11:00:00", en_excel=False)
    ruta = ruta_consulta(salida, "glaciares", "2026-11-24 11:00:00")
    assert ee.main(["--manifiesto", str(manifiesto), "--rcas", str(rcas), "--salida", str(salida),
                    "--agregar-consulta", str(ruta)]) == 0
    datos = filas(load_workbook(salida / ee.NOMBRE_EXCEL)["Consulta"])
    assert {d["consulta"].split(" ")[0] for d in datos} == {"glaciares"}  # humedales no se pidió
    assert json.loads(ruta.read_text(encoding="utf-8"))["en_excel"] is True
    # Desde entonces queda en el historial, aunque el Excel se regenere sin volver a pedirla.
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    assert {d["consulta"].split(" ")[0] for d in filas(load_workbook(destino)["Consulta"])} == {"glaciares"}


def test_excel_abierto_se_avisa_y_no_cambia_nada(tmp_path, capsys):
    manifiesto, rcas, salida = preparar(tmp_path)
    temas = bp.cargar_temas()
    guardar_consulta(salida, "humedales", temas, "2026-11-24 10:00:00", en_excel=False)
    ruta = ruta_consulta(salida, "humedales", "2026-11-24 10:00:00")
    destino, _ = ee.exportar(manifiesto, rcas, salida)
    antes = destino.read_bytes()
    (salida / f"~${ee.NOMBRE_EXCEL}").write_bytes(b"")  # el archivo de bloqueo que crea Excel al abrirlo
    assert ee.main(["--manifiesto", str(manifiesto), "--rcas", str(rcas), "--salida", str(salida),
                    "--agregar-consulta", str(ruta)]) == 3
    assert "está abierto en Excel" in capsys.readouterr().out
    assert destino.read_bytes() == antes
    assert json.loads(ruta.read_text(encoding="utf-8"))["en_excel"] is False


def test_agregar_consulta_inexistente_es_error(tmp_path):
    manifiesto, rcas, salida = preparar(tmp_path)
    assert ee.main(["--manifiesto", str(manifiesto), "--rcas", str(rcas), "--salida", str(salida),
                    "--agregar-consulta", "consulta_no_existe.json"]) == 1
    assert not (salida / ee.NOMBRE_EXCEL).exists()


# --------------------------------------------------------------------------- ID visible y revisión humana (mejora 2)

def test_id_visible_y_revision_humana_en_el_excel(tmp_path):
    manifiesto = ("archivo,unidad_fiscalizable,proyecto,prefijo_id\n"
                  "a.pdf,UF Uno,Proyecto A,AAA\n"
                  "b.pdf,UF Uno,Proyecto B,BBB\n")
    ruta_manifiesto, rcas, salida = preparar(tmp_path, manifiesto=manifiesto)
    import registrar_revision as rr
    (salida / "revision").mkdir()
    rr.escribir_csv([{"fecha_registro": "2026-11-24 10:00:00", "archivo": "a.pdf", "id_obligacion": "OBL-001",
                      "id_visible": "AAA-001", "estado": "confirmada", "fecha_revision": "2026-11-24",
                      "revisado_por": "Ignacio", "comentario": "", "origen": "prueba.csv"}],
                    rr.COLUMNAS_REGISTRO, rr.ruta_registro(salida))
    destino, _ = ee.exportar(ruta_manifiesto, rcas, salida)
    libro = load_workbook(destino)
    fila = next(d for d in filas(libro["Obligaciones detalle"]) if d["archivo"] == "a.pdf")
    assert (fila["id_visible"], fila["id_obligacion"]) == ("AAA-001", "OBL-001")
    assert fila["posible_duplicado"] == "AAA-002"  # también con prefijo
    assert (fila["revision_estado"], fila["revision_por"]) == ("confirmada", "Ignacio")
    sin = next(d for d in filas(libro["Obligaciones detalle"]) if d["archivo"] == "b.pdf")
    assert sin["descripcion"].startswith("No consta") and sin["revision_estado"] == "—"
    indice = filas(libro["Índice UF"])[0]
    assert (indice["filas_revisadas"], indice["filas_confirmadas"]) == (1, 1)


def test_sin_revision_la_obligacion_queda_pendiente(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    fila = next(d for d in filas(load_workbook(destino)["Obligaciones detalle"]) if d["archivo"] == "a.pdf")
    assert fila["revision_estado"] == "pendiente" and fila["id_visible"] == "OBL-001"  # sin prefijo_id


# --------------------------------------------------------------------------- vista compacta (mejora 3)

def test_hoja_compacta_con_lo_esencial(tmp_path):
    manifiesto = ("archivo,unidad_fiscalizable,proyecto,prefijo_id\n"
                  "a.pdf,UF Uno,Proyecto A,AAA\n"
                  "a.pdf,UF Dos,Proyecto A,AAA\n"
                  "b.pdf,UF Uno,Proyecto B,BBB\n")
    destino, _ = ee.exportar(*preparar(tmp_path, manifiesto=manifiesto))
    libro = load_workbook(destino)
    hoja = libro["Obligaciones"]
    assert [c.value for c in hoja[1]] == ee.COLUMNAS_COMPACTAS
    assert hoja.freeze_panes == "B2" and hoja.auto_filter.ref == hoja.dimensions
    assert hoja.column_dimensions["E"].width == 70  # descripción ancha
    compacta = filas(hoja)
    a_uno = next(d for d in compacta if d["id_visible"] == "AAA-001" and d["unidad_fiscalizable"] == "UF Uno")
    assert a_uno["rca"] == "Proyecto A, RCA N° 123 (2025)"
    assert (a_uno["tipo"], a_uno["descripcion"], a_uno["pagina_pdf"], a_uno["revision_estado"]) == (
        "reporte o informe a la autoridad", "Informar a la SMA.", 1, "pendiente")
    sin = next(d for d in compacta if d["rca"].startswith("Proyecto B"))
    assert sin["descripcion"].startswith("No consta") and sin["rca"] == "Proyecto B (b.pdf)"


def test_compacta_y_detalle_tienen_las_mismas_filas(tmp_path):
    destino, _ = ee.exportar(*preparar(tmp_path))
    libro = load_workbook(destino)
    clave = lambda d: (d["id_visible"], d["unidad_fiscalizable"])
    detalle = filas(libro["Obligaciones detalle"])
    assert [clave(d) for d in filas(libro["Obligaciones"])] == [clave(d) for d in detalle]
    encabezado = [c.value for c in libro["Obligaciones detalle"][1]]
    assert encabezado[:6] == ["id_visible", "unidad_fiscalizable", "proyecto", "archivo", "numero_resolucion", "id_obligacion"]
    assert libro["Obligaciones detalle"].freeze_panes == "B2"
