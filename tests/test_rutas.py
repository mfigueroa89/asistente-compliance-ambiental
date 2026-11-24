"""Pruebas de rutas: las skills del proyecto (.claude/skills/) son enlaces a skills/, y los scripts encuentran
config/ y las plantillas aunque se ejecuten desde otra carpeta (como cuando la skill viene de un plugin instalado)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = [s.name for s in (RAIZ / "skills").iterdir() if (s / "SKILL.md").exists()]


@pytest.mark.parametrize("nombre", SKILLS)
def test_skill_del_proyecto_es_un_enlace_a_skills(nombre):
    enlace = RAIZ / ".claude" / "skills" / nombre
    if os.name == "nt" and not enlace.is_symlink():
        pytest.skip("En Windows, Git puede bajar los enlaces como archivos de texto (core.symlinks).")
    assert enlace.is_symlink(), f".claude/skills/{nombre} debe ser un enlace (una sola copia en skills/)"
    assert enlace.resolve() == (RAIZ / "skills" / nombre).resolve()
    assert (enlace / "SKILL.md").exists()


@pytest.mark.parametrize("nombre", SKILLS)
def test_la_raiz_se_ubica_desde_la_carpeta_de_la_skill(nombre):
    # Regla de la sección "Rutas": la raíz está dos niveles arriba de la carpeta de la skill, resolviendo enlaces.
    for carpeta in (RAIZ / "skills" / nombre, RAIZ / ".claude" / "skills" / nombre):
        raiz = Path(os.path.realpath(carpeta)).parent.parent
        assert (raiz / "scripts" / "buscar_palabras.py").exists() and (raiz / "config" / "temas.yaml").exists()


@pytest.mark.parametrize("nombre", SKILLS)
def test_cada_skill_explica_sus_rutas(nombre):
    texto = (RAIZ / "skills" / nombre / "SKILL.md").read_text(encoding="utf-8")
    assert "## Rutas" in texto and "CLAUDE_PLUGIN_ROOT" not in texto
    assert texto.index("## Rutas") < texto.index("## Pasos")


def test_script_desde_otra_carpeta_encuentra_config(tmp_path):
    # Simula el modo plugin: se trabaja en otra carpeta y el script se llama por su ruta absoluta.
    salida = tmp_path / "salida"
    texto = {"archivo": "x.pdf", "sha256": "a", "paginas": [
        {"numero_pdf": 1, "numero_impreso": None, "texto": "Se protegerán los humedales.", "estado": "texto",
         "origen_texto": "digital"}]}
    obligaciones = {"obligaciones": [{"id_obligacion": "OBL-001", "cita_textual": "Se protegerán los humedales.",
                                      "pagina_pdf": 1, "descripcion": "", "posible_duplicado": []}]}
    for carpeta, contenido in (("texto", texto), ("obligaciones", obligaciones)):
        (salida / carpeta).mkdir(parents=True)
        (salida / carpeta / "x.json").write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "buscar_palabras.py"), "consultar", "humedales"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "tema «humedales» (humedal, bofedal" in resultado.stdout  # leyó config/temas.yaml de la raíz
    assert list((salida / "consultas").glob("consulta_humedales_*.json"))  # escribió en la carpeta de trabajo


@pytest.mark.parametrize("nombre", SKILLS)
def test_cada_skill_exige_respaldo_antes_de_modificar_salida(nombre):
    texto = (RAIZ / "skills" / nombre / "SKILL.md").read_text(encoding="utf-8")
    assert "scripts/respaldar_salida.py" in texto and "espera el OK de Ignacio" in texto


@pytest.mark.parametrize("nombre", SKILLS)
def test_cada_skill_ofrece_preparar_el_entorno_con_ok(nombre):
    texto = (RAIZ / "skills" / nombre / "SKILL.md").read_text(encoding="utf-8")
    assert "requirements.txt" in texto and "solo con el OK del usuario" in texto
