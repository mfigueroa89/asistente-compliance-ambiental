"""Elige al azar, con una semilla fija, una muestra de obligaciones para que un abogado las audite contra el PDF (sin IA).

Uso:
    python scripts/muestra_auditoria.py OBLIGACIONES_JSON [OBLIGACIONES_JSON ...] [--semilla 20261123] [--cantidad 20]
                                        [--salida salida]

Cómo funciona:
    - junta todas las filas de los archivos, en el orden en que se entregan los archivos y, dentro de cada uno,
      en el orden de sus ID;
    - sortea la cantidad pedida con la semilla indicada. La misma semilla, los mismos archivos en el mismo orden
      y el mismo contenido entregan siempre la misma muestra;
    - ordena la muestra por archivo (en el orden de entrada) y por ID, para que sea fácil seguirla en el PDF.

Muestra de la Etapa 4 (semilla 20261123), en este orden:
    python scripts/muestra_auditoria.py salida/obligaciones/rca_202513001415_queltehue_rm.json \
        salida/obligaciones/rca_151_2013_arqueros_atacama.json \
        salida/obligaciones/rca_021_2016_albemarle_salar_atacama.json

Resultado: una tabla en pantalla y salida/verificacion/muestra_auditoria_<semilla>.csv (se abre en Excel).
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

AVISO = "Herramienta de apoyo. Requiere revisión de un abogado."
SEMILLA = 20261123
CANTIDAD = 20
COLUMNAS = ["RCA", "ID", "Página", "Tipo", "Descripción", "Plazo", "Autoridad", "Cita textual"]


def cargar_filas(rutas):
    """Lista de (orden_archivo, rca, obligacion) en el orden de entrada."""
    filas = []
    for orden, ruta in enumerate(rutas):
        ruta = Path(ruta)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        rca = ruta.stem
        for obligacion in sorted(datos["obligaciones"], key=lambda o: o["id_obligacion"]):
            filas.append((orden, rca, obligacion))
    return filas


def elegir_muestra(filas, semilla=SEMILLA, cantidad=CANTIDAD):
    elegidas = random.Random(semilla).sample(filas, min(cantidad, len(filas)))
    return sorted(elegidas, key=lambda f: (f[0], f[2]["id_obligacion"]))


def a_fila(rca, obligacion):
    return {
        "RCA": rca,
        "ID": obligacion["id_obligacion"],
        "Página": obligacion["pagina_pdf"],
        "Tipo": obligacion["tipo"],
        "Descripción": obligacion["descripcion"],
        "Plazo": obligacion["plazo_o_frecuencia"],
        "Autoridad": obligacion["autoridad_destinataria"],
        "Cita textual": obligacion["cita_textual"],
    }


def tabla_markdown(filas):
    limpiar = lambda valor: str(valor).replace("|", "/").replace("\n", " ")
    lineas = ["| " + " | ".join(COLUMNAS) + " |", "|" + "---|" * len(COLUMNAS)]
    lineas += ["| " + " | ".join(limpiar(f[c]) for c in COLUMNAS) + " |" for f in filas]
    return "\n".join(lineas)


def guardar_csv(filas, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Muestra al azar de obligaciones para auditoría.")
    parser.add_argument("obligaciones", nargs="+", help="JSON de salida/obligaciones/ (el orden importa)")
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--cantidad", type=int, default=CANTIDAD)
    parser.add_argument("--salida", default="salida")
    opciones = parser.parse_args(argumentos)
    filas = cargar_filas(opciones.obligaciones)
    muestra = [a_fila(rca, o) for _, rca, o in elegir_muestra(filas, opciones.semilla, opciones.cantidad)]
    ruta = Path(opciones.salida) / "verificacion" / f"muestra_auditoria_{opciones.semilla}.csv"
    guardar_csv(muestra, ruta)
    print(f"Muestra de {len(muestra)} de {len(filas)} obligaciones (semilla {opciones.semilla}).\n")
    print(tabla_markdown(muestra))
    print(f"\nGuardada en {ruta}")
    print(AVISO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
