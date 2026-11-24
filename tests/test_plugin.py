"""Pruebas mínimas de los archivos del plugin (.claude-plugin/): que sean JSON válido y tengan los campos requeridos."""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / ".claude-plugin"


def leer(nombre):
    return json.loads((CARPETA / nombre).read_text(encoding="utf-8"))


def test_plugin_json():
    plugin = leer("plugin.json")
    assert plugin["name"] == "asistente-compliance-ambiental" and " " not in plugin["name"]
    assert plugin["version"] == "0.1.0" and plugin["author"]["name"] == "Ignacio Figueroa Moya"
    assert "abogado" in plugin["description"]


def test_catalogo_local_apunta_al_plugin():
    catalogo = leer("marketplace.json")
    assert catalogo["owner"]["name"] and catalogo["name"] != "claude-plugins-official"
    [entrada] = catalogo["plugins"]
    assert entrada["name"] == leer("plugin.json")["name"]
    assert (RAIZ / entrada["source"] / ".claude-plugin" / "plugin.json").exists()


def test_cada_skill_tiene_nombre_y_descripcion():
    for skill in (RAIZ / "skills").iterdir():
        if not skill.is_dir() or not (skill / "SKILL.md").exists():
            continue
        cabecera = (skill / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        assert f"name: {skill.name}" in cabecera and "description:" in cabecera, skill.name
