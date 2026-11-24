"""Pruebas de scripts/buscar_palabras.py (búsqueda exacta, sin IA).

Las pruebas sobre Arqueros usan el texto y las obligaciones de salida/ (que no se suben a GitHub):
si faltan, se saltan con un aviso. El caso de página escaneada usa un PDF sintético que la prueba genera.
"""

import copy
import json
from pathlib import Path

import pymupdf
import pytest

import buscar_palabras as bp
import leer_pdf

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "salida"
ARQUEROS = "rca_151_2013_arqueros_atacama.pdf"
MANIFIESTO = RAIZ / "ejemplos" / "manifiesto_ejemplo.csv"

requiere_arqueros = pytest.mark.skipif(
    not (SALIDA / "obligaciones" / "rca_151_2013_arqueros_atacama.json").exists()
    or not (SALIDA / "texto" / "rca_151_2013_arqueros_atacama.json").exists(),
    reason="Faltan el texto o las obligaciones de Arqueros en salida/ (se generan en las etapas 1 y 4)",
)


@pytest.fixture(scope="module")
def temas():
    return bp.cargar_temas()


@pytest.fixture(scope="module")
def arqueros():
    return bp.cargar_rca(ARQUEROS, SALIDA)


def ids(resultado, categoria):
    return sorted({f["id_obligacion"] for f in resultado["filas"] if f["categoria"] == categoria})


# ------------------------------------------------------------------ comparación de texto

def test_sin_tildes_ni_mayusculas():
    assert [e for _, _, e in bp.buscar("Área Protegida y AREA PROTEGIDA", "área protegida")] == ["Área Protegida", "AREA PROTEGIDA"]


def test_plural_simple_en_ambos_sentidos():
    texto = "un humedal y dos humedales; una vega y las vegas"
    assert [e for _, _, e in bp.buscar(texto, "humedal")] == ["humedal", "humedales"]
    assert [e for _, _, e in bp.buscar(texto, "humedales")] == ["humedal", "humedales"]
    assert [e for _, _, e in bp.buscar(texto, "vega")] == ["vega", "vegas"]


def test_solo_palabras_completas():
    assert bp.buscar("vegetación azonal y Las Vegetas", "vega") == []
    assert bp.buscar("napas freáticas y canapé", "napa") != []
    assert [e for _, _, e in bp.buscar("canapé", "napa")] == []


def test_frase_cortada_por_salto_de_linea_o_guion():
    assert [e for _, _, e in bp.buscar("el sitio\nRamsar del salar", "sitio Ramsar")] == ["sitio\nRamsar"]
    assert len(bp.buscar("humedales alto-  andinos", "humedal")) == 1
    assert len(bp.buscar("Convenio  169 de la OIT", "Convenio 169")) == 1


def test_contexto_marca_el_termino():
    texto = "x" * 300 + " bofedal " + "y" * 300
    inicio, fin, _ = bp.buscar(texto, "bofedal")[0]
    contexto = bp.contexto_de(texto, inicio, fin)
    assert "[bofedal]" in contexto and contexto.startswith("…") and contexto.endswith("…")


# ------------------------------------------------------------------ temas.yaml

def test_temas_yaml_del_proyecto(temas):
    assert temas["humedales"] == ["humedal", "bofedal", "vega", "turbera", "ecosistema lacustre", "sitio Ramsar"]
    assert "pajonal hídrico" not in temas["humedales"]  # decisión de Ignacio (2026-11-23): por ahora no


def test_temas_yaml_inexistente(tmp_path):
    with pytest.raises(bp.ErrorTemas, match="No existe"):
        bp.cargar_temas(tmp_path / "temas.yaml")


def test_temas_yaml_mal_escrito(tmp_path):
    ruta = tmp_path / "temas.yaml"
    ruta.write_text("humedales:\n  - humedal\n - bofedal\n", encoding="utf-8")
    with pytest.raises(bp.ErrorTemas, match="error de formato"):
        bp.cargar_temas(ruta)


def test_temas_yaml_tema_sin_terminos(tmp_path):
    ruta = tmp_path / "temas.yaml"
    ruta.write_text("humedales:\nglaciares:\n  - glaciar\n", encoding="utf-8")
    with pytest.raises(bp.ErrorTemas, match="«humedales» no tiene una lista"):
        bp.cargar_temas(ruta)


def test_resolver_consulta(temas):
    assert bp.resolver_consulta("Humedales", temas)["tema"] == "humedales"
    assert bp.resolver_consulta("humedal", temas)["tema"] == "humedales"
    suelto = bp.resolver_consulta("bofedal", temas)
    assert suelto["tema"] is None and suelto["terminos"] == ["bofedal"] and "humedales" in suelto["aviso"]
    assert suelto["tema_del_termino"] == "humedales"
    assert bp.resolver_consulta("pajonal hídrico", temas) == {"tema": None, "terminos": ["pajonal hídrico"], "aviso": None,
                                                              "tema_del_termino": None}


# ------------------------------------------------------------------ obligaciones (datos sintéticos)

def obligacion(ident, cita, pagina=1, descripcion="", adicionales=(), relacionados=()):
    return {"id_obligacion": ident, "descripcion": descripcion, "cita_textual": cita, "pagina_pdf": pagina,
            "citas_adicionales": [{"pagina_pdf": p, "cita_textual": c} for p, c in adicionales],
            "temas_relacionados": list(relacionados), "posible_duplicado": []}


def test_literal_solo_en_citas_no_en_descripcion(temas):
    o = obligacion("OBL-001", "Se protegerán las áreas de alimentación.", descripcion="Proteger los humedales.")
    assert bp.temas_literales(o, temas) == {}
    assert bp.terminos_en_descripcion_sin_cita(o, temas) == [("humedales", "humedal", "humedales")]


def test_literal_en_cita_adicional(temas):
    o = obligacion("OBL-002", "Se protegerán las áreas.", adicionales=[(3, "cercano a bofedales no salinos")])
    assert bp.temas_literales(o, temas) == {"humedales": [("bofedal", "bofedales", "cita adicional 1 (p. 3)")]}


def test_ubica_la_cita_en_la_pagina_aunque_cambien_espacios():
    pagina = "Inicio.  Se  establecerán áreas de protección en los\nhumedales. Fin."
    tramos = bp.tramos_de_cita("se establecerán áreas de protección en los humedales", pagina)
    assert len(tramos) == 1 and pagina[tramos[0][0]:tramos[0][1]].endswith("humedales")


def texto_sintetico(*paginas):
    return {"archivo": "rca_x.pdf", "sha256": "abc", "paginas": [
        {"numero_pdf": i, "numero_impreso": None, "texto": t, "estado": "texto", "origen_texto": "digital"}
        for i, t in enumerate(paginas, start=1)]}


def rca_sintetica(texto, obligaciones, revisados=None):
    datos = {"obligaciones": obligaciones, "control": {}}
    if revisados:
        datos["temas_relacionados_revisados"] = {"temas": revisados}
    return {"archivo": texto["archivo"], "texto": texto, "datos_obligaciones": datos, "obligaciones": obligaciones,
            "numero_resolucion": "1", "avisos": []}


def test_tres_categorias_con_datos_sinteticos(temas):
    texto = texto_sintetico(
        "Descripción: el proyecto se ubica junto a un bofedal.",
        "Se establecerán áreas de protección en los humedales. Se retirarán desechos del pajonal.",
    )
    obligaciones = [
        obligacion("OBL-001", "Se establecerán áreas de protección en los humedales.", pagina=2),
        obligacion("OBL-002", "Se retirarán desechos del pajonal.", pagina=2,
                   relacionados=[{"tema": "humedales", "justificacion": "La cita dice «pajonal».", "estado": "revisar"}]),
    ]
    r = bp.consultar("humedales", [rca_sintetica(texto, obligaciones, ["humedales"])], temas)
    assert ids(r, bp.LITERAL) == ["OBL-001"]
    assert ids(r, bp.RELACION) == ["OBL-002"]
    menciones = [f for f in r["filas"] if f["categoria"] == bp.MENCION]
    assert [(m["pagina_pdf"], m["termino_encontrado"]) for m in menciones] == [(1, "bofedal")]
    assert r["conteo"] == {bp.LITERAL: 1, bp.RELACION: 1, bp.MENCION: 1}
    assert set(r["filas"][0]) == set(bp.COLUMNAS_CONSULTA)
    assert r["filas"][0]["unidad_fiscalizable"] == bp.SIN_UF


def test_un_tema_literal_no_se_repite_como_relacion(temas):
    texto = texto_sintetico("Se protegerán los humedales.")
    o = obligacion("OBL-001", "Se protegerán los humedales.",
                   relacionados=[{"tema": "humedales", "justificacion": "x", "estado": "revisar"}])
    r = bp.consultar("humedales", [rca_sintetica(texto, [o], ["humedales"])], temas)
    assert [f["categoria"] for f in r["filas"]] == [bp.LITERAL]


def test_sin_resultados_lo_dice_y_trae_alcance(temas):
    texto = texto_sintetico("Se protegerán las áreas.")
    r = bp.consultar("glaciares", [rca_sintetica(texto, [obligacion("OBL-001", "Se protegerán las áreas.")])], temas)
    assert r["sin_resultados"] is True and r["filas"] == []
    assert r["mensaje"] == "No hay resultados para «glaciares» en el alcance indicado."
    assert r["alcance_texto"][0] == "Alcance: 1 RCA(s) y 1 obligaciones buscadas."
    assert "AÚN NO REVISADA" in r["alcance_texto"][1]


def test_termino_libre_avisa_que_no_hay_relacion_tematica(temas):
    texto = texto_sintetico("Se protegerán las áreas.")
    r = bp.consultar("pajonal", [rca_sintetica(texto, [obligacion("OBL-001", "Se protegerán las áreas.")])], temas)
    assert "fuera de config/temas.yaml" in r["alcance_texto"][1]


# ------------------------------------------------------------------ página escaneada (PDF sintético)

def test_pagina_escaneada_queda_en_el_alcance(tmp_path, temas):
    borrador = pymupdf.open()
    hoja = borrador.new_page()
    hoja.insert_text((72, 100), "Humedal escaneado", fontsize=20)
    foto = hoja.get_pixmap(dpi=72)
    borrador.close()
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), "El titular deberá proteger el humedal ubicado al norte del área del proyecto.")
    escaneada = documento.new_page()
    escaneada.insert_image(escaneada.rect, pixmap=foto)
    ruta = tmp_path / "sintetico.pdf"
    documento.save(ruta)
    documento.close()

    texto = leer_pdf.leer_pdf(ruta)
    o = obligacion("OBL-001", "El titular deberá proteger el humedal ubicado al norte del área del proyecto.")
    r = bp.consultar("humedales", [rca_sintetica(texto, [o])], temas)
    assert ids(r, bp.LITERAL) == ["OBL-001"]
    assert r["alcance"][0]["paginas_sin_texto"] == [2]
    assert "páginas sin texto, no revisadas en el texto completo: 2" in r["alcance_texto"][1]


# ------------------------------------------------------------------ Arqueros (caso de prueba de Ignacio)

@requiere_arqueros
def test_arqueros_humedales_literales(arqueros, temas):
    r = bp.consultar("humedales", [arqueros], temas)
    # OBL-038 es literal desde que tiene la cita adicional de la p. 151 («bofedales no salinos»), aprobada el 2026-11-23.
    assert ids(r, bp.LITERAL) == ["OBL-006", "OBL-024", "OBL-038"]
    for ident in ("OBL-060", "OBL-061", "OBL-202"):
        assert ident not in ids(r, bp.LITERAL)


@requiere_arqueros
def test_arqueros_humedales_relacion_tematica(arqueros, temas):
    # Relación temática anotada el 2026-11-23 con el criterio aprobado por Ignacio.
    r = bp.consultar("humedales", [arqueros], temas)
    relacion = ids(r, bp.RELACION)
    assert {"OBL-060", "OBL-061", "OBL-202"} <= set(relacion)
    assert "OBL-074" not in relacion  # el SVAHT solo ubica el tramo del balizado (decisión de criterio)
    assert not set(relacion) & set(ids(r, bp.LITERAL))
    assert "relación temática ya revisada" in r["alcance_texto"][1]
    fila = next(f for f in r["filas"] if f["id_obligacion"] == "OBL-202")
    assert "«" in fila["justificacion"] and fila["justificacion"].endswith("(p. 191)")


@requiere_arqueros
def test_arqueros_menciones_sin_obligacion(arqueros, temas):
    r = bp.consultar("humedales", [arqueros], temas)
    menciones = [f for f in r["filas"] if f["categoria"] == bp.MENCION]
    paginas = {m["pagina_pdf"] for m in menciones}
    assert {94, 100, 102, 115, 153} <= paginas  # evaluación y tabla de compensación sin obligaciones
    # Las dos oraciones de la p. 150 están citadas en OBL-024: ya no son menciones sin obligación.
    assert 150 not in paginas
    # La p. 163 repite el texto de OBL-038 sin cita que nombre los bofedales: sigue como mención.
    assert 163 in paginas


@requiere_arqueros
def test_arqueros_alcance_con_paginas_escaneadas(arqueros, temas):
    r = bp.consultar("turbera", [arqueros], temas)
    assert r["sin_resultados"] is True
    assert r["alcance"][0]["obligaciones_buscadas"] == 291  # 289 + OBL-290 y 291 (p. 189), agregadas el 2026-11-24
    assert r["alcance"][0]["paginas_sin_texto"] == [60, 166, 167]
    assert r["alcance"][0]["paginas_sin_texto_con_obligaciones_leidas_en_imagen"] == [166, 167]


@requiere_arqueros
def test_arqueros_manifiesto_pone_uf_y_proyecto(arqueros, temas):
    unidades, _ = bp.unidades_por_archivo(MANIFIESTO)
    r = bp.consultar("humedales", [arqueros], temas, unidades)
    fila = next(f for f in r["filas"] if f["id_obligacion"] == "OBL-024")
    assert fila["unidad_fiscalizable"] == "LAGUNA RESOURCES CHILE LIMITADA-PROYECTO ARQUEROS"
    assert fila["proyecto"] == "Proyecto Arqueros"
    assert fila["numero_resolucion"] == "151"
    assert fila["donde_aparece"] == "cita principal (p. 150); cita adicional 1 (p. 150)"


def copia_de_salida(destino, archivos):
    """Copia texto, obligaciones y fichas de salida/ a una carpeta temporal, para que las pruebas
    no agreguen consultas al historial real de Ignacio (salida/consultas/)."""
    for archivo in archivos:
        base = Path(archivo).stem
        for carpeta in ("texto", "obligaciones", "fichas"):
            origen = SALIDA / carpeta / f"{base}.json"
            if origen.exists():
                (destino / carpeta).mkdir(parents=True, exist_ok=True)
                (destino / carpeta / origen.name).write_bytes(origen.read_bytes())
    return destino


def consultas_guardadas(salida):
    return sorted((salida / "consultas").glob("consulta_*.json"))


@requiere_arqueros
def test_consulta_no_modifica_las_obligaciones(tmp_path):
    salida = copia_de_salida(tmp_path / "salida", [ARQUEROS])
    ruta = salida / "obligaciones" / "rca_151_2013_arqueros_atacama.json"
    antes = ruta.read_bytes()
    assert bp.main(["--salida", str(salida), "consultar", "humedales", "--archivo", ARQUEROS,
                    "--manifiesto", str(MANIFIESTO)]) == 0
    assert ruta.read_bytes() == antes
    [guardada] = consultas_guardadas(salida)
    datos = json.loads(guardada.read_text(encoding="utf-8"))
    assert datos["aviso"] == bp.AVISO
    assert guardada.with_suffix(".csv").exists()
    # La consulta no regenera el Excel: entra en la hoja Consulta solo si el usuario lo pide.
    assert datos["en_excel"] is False
    assert not (salida / "compliance_ambiental.xlsx").exists()


@requiere_arqueros
def test_cada_consulta_queda_guardada_aparte(tmp_path):
    # Historial (decisión (b) de Ignacio): dos consultas, aunque sean del mismo término y segundo, no se pisan.
    salida = copia_de_salida(tmp_path / "salida", [ARQUEROS])
    for _ in range(2):
        assert bp.main(["--salida", str(salida), "consultar", "humedales", "--manifiesto", str(MANIFIESTO)]) == 0
    guardadas = consultas_guardadas(salida)
    assert len(guardadas) == 2
    assert all(g.name.startswith("consulta_humedales_") for g in guardadas)
    assert "fecha_hora" in json.loads(guardadas[0].read_text(encoding="utf-8"))


# ------------------------------------------------------------------ filtro por unidad fiscalizable

UNIDADES_SINTETICAS = {
    "a.pdf": [("UF NORTE", "Proyecto A")],
    "b.pdf": [("UF NORTE", "Proyecto B"), ("UF SUR", "Proyecto B")],
}


def test_seleccionar_uf_sin_tildes_ni_mayusculas():
    assert bp.seleccionar_uf("uf norte", UNIDADES_SINTETICAS, ["a.pdf", "b.pdf"]) == ("UF NORTE", ["a.pdf", "b.pdf"])
    assert bp.seleccionar_uf("SUR", UNIDADES_SINTETICAS, ["a.pdf", "b.pdf"]) == ("UF SUR", ["b.pdf"])


def test_seleccionar_uf_pdf_sin_manifiesto_es_sin_uf():
    assert bp.seleccionar_uf("sin uf asignada", UNIDADES_SINTETICAS, ["a.pdf", "c.pdf"]) == (bp.SIN_UF, ["c.pdf"])


def test_seleccionar_uf_inexistente_o_ambigua():
    with pytest.raises(bp.ErrorConsulta, match="No hay ninguna unidad fiscalizable «oeste»"):
        bp.seleccionar_uf("oeste", UNIDADES_SINTETICAS, [])
    with pytest.raises(bp.ErrorConsulta, match="calza con varias"):
        bp.seleccionar_uf("UF", UNIDADES_SINTETICAS, [])


def test_uf_deja_solo_las_filas_de_esa_unidad(temas):
    texto = texto_sintetico("Se protegerán los humedales.")
    texto["archivo"] = "b.pdf"
    r = bp.consultar("humedales", [rca_sintetica(texto, [obligacion("OBL-001", "Se protegerán los humedales.")])],
                     temas, UNIDADES_SINTETICAS, uf="UF SUR")
    assert [f["unidad_fiscalizable"] for f in r["filas"]] == ["UF SUR"]
    assert r["filtro"]["unidad_fiscalizable"] == "UF SUR"
    assert "solo de la unidad fiscalizable «UF SUR»" in r["alcance_texto"][0]


@requiere_arqueros
def test_uf_de_arqueros_entrega_solo_arqueros(tmp_path):
    todas = [ARQUEROS, "rca_202513001415_queltehue_rm.pdf", "rca_021_2016_albemarle_salar_atacama.pdf"]
    salida = copia_de_salida(tmp_path / "salida", todas)
    assert bp.main(["--salida", str(salida), "consultar", "humedales", "--uf", "proyecto arqueros",
                    "--manifiesto", str(MANIFIESTO)]) == 0
    [guardada] = consultas_guardadas(salida)
    datos = json.loads(guardada.read_text(encoding="utf-8"))
    assert datos["filtro"] == {"unidad_fiscalizable": "LAGUNA RESOURCES CHILE LIMITADA-PROYECTO ARQUEROS",
                               "archivos_pedidos": None, "archivos": [ARQUEROS],
                               "manifiesto": MANIFIESTO.as_posix()}
    assert [a["obligaciones_buscadas"] for a in datos["alcance"]] == [291]
    assert {f["archivo"] for f in datos["filas"]} == {ARQUEROS}
    assert {f["unidad_fiscalizable"] for f in datos["filas"]} == {"LAGUNA RESOURCES CHILE LIMITADA-PROYECTO ARQUEROS"}


def test_uf_inexistente_por_linea_de_comandos(tmp_path):
    (tmp_path / "obligaciones").mkdir()
    assert bp.main(["--salida", str(tmp_path), "consultar", "humedales", "--uf", "no existe",
                    "--manifiesto", str(MANIFIESTO)]) == 2


# ------------------------------------------------------------------ relaciones propuestas para un término libre

def rca_pajonal(temas):
    texto = texto_sintetico(
        "Se retirarán los desechos del sector de vegetación azonal hídrica.",
        "En el pajonal se ubican las aves.",
    )
    obligaciones = [obligacion("OBL-001", "Se retirarán los desechos del sector de vegetación azonal hídrica."),
                    obligacion("OBL-002", "En el pajonal se ubican las aves.", pagina=2)]
    return rca_sintetica(texto, obligaciones)


def propuesta(ident="OBL-001", palabras="vegetación azonal hídrica", pagina=1):
    return {"archivo": "rca_x.pdf", "id_obligacion": ident, "palabras_pdf": palabras, "pagina_pdf": pagina,
            "justificacion": f"La obligación protege la «{palabras}», que el PDF nombra en lugar del pajonal."}


def test_relacion_valida_se_acepta_como_revisar(temas):
    r = bp.consultar("pajonal", [rca_pajonal(temas)], temas, propuestas=[propuesta()])
    assert ids(r, bp.RELACION) == ["OBL-001"]
    fila = next(f for f in r["filas"] if f["categoria"] == bp.RELACION)
    assert fila["justificacion"].startswith("(propuesta en esta consulta)") and fila["justificacion"].endswith("(p. 1)")
    [aceptada] = r["relaciones_propuestas"]["aceptadas"]
    assert aceptada["estado"] == "revisar"
    assert "1 aceptadas (comprobadas por código, a revisar) y 0 rechazadas" in r["alcance_texto"][-1]


def test_relacion_dudosa_con_nota_se_muestra(temas):
    dudosa = {**propuesta(), "dudosa": True, "nota": "Dudosa hasta que Ignacio confirme la p. 1."}
    r = bp.consultar("pajonal", [rca_pajonal(temas)], temas, propuestas=[dudosa])
    fila = next(f for f in r["filas"] if f["categoria"] == bp.RELACION)
    assert fila["justificacion"].startswith("(propuesta en esta consulta) (dudosa) ")
    assert fila["justificacion"].endswith("(p. 1) [Dudosa hasta que Ignacio confirme la p. 1.]")


def test_relacion_con_palabras_que_no_estan_en_la_pagina_se_rechaza(temas):
    r = bp.consultar("pajonal", [rca_pajonal(temas)], temas, propuestas=[propuesta(palabras="bofedal altoandino")])
    assert ids(r, bp.RELACION) == []
    [rechazada] = r["relaciones_propuestas"]["rechazadas"]
    assert "no están en el texto de la p. 1" in rechazada["motivo"]


def test_relacion_en_otra_pagina_se_rechaza_y_lo_dice(temas):
    r = bp.consultar("pajonal", [rca_pajonal(temas)], temas, propuestas=[propuesta(pagina=2)])
    [rechazada] = r["relaciones_propuestas"]["rechazadas"]
    assert "(están en la p. 1)" in rechazada["motivo"]


def test_relacion_de_una_obligacion_literal_se_rechaza(temas):
    r = bp.consultar("pajonal", [rca_pajonal(temas)], temas,
                     propuestas=[propuesta(ident="OBL-002", palabras="aves", pagina=2)])
    assert ids(r, bp.LITERAL) == ["OBL-002"] and ids(r, bp.RELACION) == []
    assert "coincidencia literal" in r["relaciones_propuestas"]["rechazadas"][0]["motivo"]


def test_relacion_sin_justificacion_con_comillas_o_de_obligacion_inexistente_se_rechaza(temas):
    sin_comillas = {**propuesta(), "justificacion": "Porque protege vegetación azonal hídrica del sector."}
    r = bp.consultar("pajonal", [rca_pajonal(temas)], temas, propuestas=[sin_comillas, propuesta(ident="OBL-999")])
    motivos = [x["motivo"] for x in r["relaciones_propuestas"]["rechazadas"]]
    assert "« »" in motivos[0] and "no existe la obligación OBL-999" in motivos[1]


def test_relaciones_propuestas_no_se_aceptan_para_un_tema(temas):
    with pytest.raises(bp.ErrorConsulta, match="es un tema de config/temas.yaml"):
        bp.consultar("humedales", [rca_pajonal(temas)], temas, propuestas=[propuesta()])


def test_relaciones_por_linea_de_comandos_y_obligaciones_intactas(tmp_path, temas):
    salida = tmp_path / "salida"
    rca = rca_pajonal(temas)
    for carpeta, contenido in (("texto", rca["texto"]), ("obligaciones", {"obligaciones": rca["obligaciones"]})):
        (salida / carpeta).mkdir(parents=True)
        (salida / carpeta / "rca_x.json").write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    antes = (salida / "obligaciones" / "rca_x.json").read_bytes()
    relaciones = tmp_path / "relaciones.json"
    relaciones.write_text(json.dumps({"relaciones": [propuesta(), propuesta(ident="OBL-001", palabras="humedal")]},
                                     ensure_ascii=False), encoding="utf-8")
    assert bp.main(["--salida", str(salida), "consultar", "pajonal", "--relaciones", str(relaciones),
                    "--manifiesto", str(MANIFIESTO)]) == 0
    assert (salida / "obligaciones" / "rca_x.json").read_bytes() == antes  # decisión (a): solo en salida/consultas/
    [guardada] = consultas_guardadas(salida)
    datos = json.loads(guardada.read_text(encoding="utf-8"))
    assert len(datos["relaciones_propuestas"]["aceptadas"]) == 1
    assert len(datos["relaciones_propuestas"]["rechazadas"]) == 1


# ------------------------------------------------------------------ manifiesto de respaldo

def salida_sintetica(tmp_path, temas):
    salida = tmp_path / "salida"
    rca = rca_pajonal(temas)
    for carpeta, contenido in (("texto", rca["texto"]), ("obligaciones", {"obligaciones": rca["obligaciones"]})):
        (salida / carpeta).mkdir(parents=True)
        (salida / carpeta / "rca_x.json").write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    return salida


def test_sin_manifiesto_csv_usa_el_de_ejemplo_y_lo_avisa(tmp_path, temas, monkeypatch, capsys):
    # Caso del 2026-11-23: la consulta corrió con un manifiesto.csv inexistente y dejó todo como SIN UF ASIGNADA.
    salida = salida_sintetica(tmp_path, temas)
    monkeypatch.chdir(tmp_path)  # carpeta de trabajo sin manifiesto.csv ni ejemplos/
    assert bp.main(["--salida", str(salida), "consultar", "humedales"]) == 0
    [guardada] = consultas_guardadas(salida)
    datos = json.loads(guardada.read_text(encoding="utf-8"))
    assert Path(datos["filtro"]["manifiesto"]) == MANIFIESTO
    assert any("se usó el manifiesto de ejemplo" in a for a in datos["avisos"])
    assert not any("No se encontró el manifiesto" in a for a in datos["avisos"])
    assert "se usó el manifiesto de ejemplo" in capsys.readouterr().out


def test_sin_ningun_manifiesto_no_guarda_nada(tmp_path, temas, monkeypatch, capsys):
    salida = salida_sintetica(tmp_path, temas)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bp, "MANIFIESTOS_EJEMPLO", [tmp_path / "ejemplos" / "manifiesto_ejemplo.csv"])
    assert bp.main(["--salida", str(salida), "consultar", "humedales"]) == 2
    assert not (salida / "consultas").exists()
    assert "No se guardó la consulta" in capsys.readouterr().out


def test_manifiesto_indicado_inexistente_no_guarda_nada(tmp_path, temas, capsys):
    salida = salida_sintetica(tmp_path, temas)
    assert bp.main(["--salida", str(salida), "consultar", "humedales",
                    "--manifiesto", str(tmp_path / "no_hay.csv")]) == 2
    assert not (salida / "consultas").exists()
    assert "No existe el manifiesto indicado" in capsys.readouterr().out


# ------------------------------------------------------------------ las tres RCAs reales

requiere_tres = pytest.mark.skipif(
    not all((SALIDA / "obligaciones" / f"{b}.json").exists() for b in
            ("rca_151_2013_arqueros_atacama", "rca_202513001415_queltehue_rm", "rca_021_2016_albemarle_salar_atacama")),
    reason="Faltan las obligaciones de las tres RCAs de ejemplo en salida/",
)


@requiere_tres
def test_humedales_en_las_tres_rcas_sigue_igual(temas):
    rcas, errores = bp.cargar_varias(bp.archivos_a_buscar(SALIDA, None), SALIDA)
    assert errores == []
    r = bp.consultar("humedales", rcas, temas)
    assert r["conteo"][bp.LITERAL] == 3 and r["conteo"][bp.RELACION] == 15


def test_csv_para_excel_en_espanol(tmp_path):
    ruta = tmp_path / "x.csv"
    bp.guardar_csv([{"a": "Área protegida", "b": "vegas, bofedales"}], ["a", "b"], ruta)
    contenido = ruta.read_bytes()
    assert contenido.startswith(b"\xef\xbb\xbf")  # BOM: Excel lee bien las tildes
    assert contenido.decode("utf-8-sig").splitlines() == ["a;b", "Área protegida;vegas, bofedales"]


# ------------------------------------------------------------------ ID visible (mejora 2)

def test_consulta_muestra_el_id_visible(temas):
    texto = texto_sintetico("Se protegerán los humedales.")
    rca = rca_sintetica(texto, [obligacion("OBL-001", "Se protegerán los humedales.")])
    r = bp.consultar("humedales", [rca], temas, prefijos={"rca_x.pdf": "XYZ"})
    assert r["filas"][0]["id_visible"] == "XYZ-001" and r["filas"][0]["id_obligacion"] == "OBL-001"
    assert bp.buscar_obligacion("xyz 1", [rca], {"rca_x.pdf": "XYZ"})[0][1]["id_obligacion"] == "OBL-001"
    assert bp.buscar_obligacion("OBL-001", [rca], {})[0][1]["id_obligacion"] == "OBL-001"
    assert bp.buscar_obligacion("XYZ-002", [rca], {"rca_x.pdf": "XYZ"}) == []
