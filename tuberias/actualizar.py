#!/usr/bin/env python3
"""La cadena completa de los datos del BCR, en una orden. Sirve igual a mano, en un runner propio o
en una tarea programada: es lo mismo que hace .github/workflows/datos.yml.

    python tuberias/actualizar.py           trae lo que toca según el calendario
    python tuberias/actualizar.py --todo    trae las 18 series, toquen o no (para captar revisiones)

Pasos: calendario del BCR → qué toca → traer → plata → oro → calendario → compuerta. No hace commit:
si la compuerta pasa y `git status` muestra cambios en lago/, se guardan con git. Termina con error si
la compuerta falla, y entonces lo traído no debe guardarse.
"""
import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def correr(*orden, obligatorio=True):
    print("→ python " + " ".join(orden), flush=True)
    r = subprocess.run([sys.executable, *orden], cwd=RAIZ)
    if r.returncode and obligatorio:
        sys.exit(r.returncode)
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--todo", action="store_true")
    a = ap.parse_args()
    # sin calendario nuevo se decide con el que ya está en el lago
    sin_calendario = correr("tuberias/traer.py", "calendario", obligatorio=False)
    toca = subprocess.run([sys.executable, "tuberias/calendario.py", "toca"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    correr("tuberias/calendario.py")
    fallo = 0
    if a.todo:
        fallo = correr("tuberias/traer.py", "bcr", obligatorio=False)
    elif toca:
        fallo = correr("tuberias/traer.py", "bcr", "--solo", toca, obligatorio=False)
    else:
        print("Nada toca hoy.")
    correr("tuberias/plata.py")
    correr("tuberias/oro.py")
    correr("tuberias/calendario.py", "plata")
    correr("tuberias/verificar.py")
    cambios = subprocess.run(["git", "status", "--short", "lago"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    print("\nLa compuerta pasa. " + ("Hay cambios en lago/ por guardar:\n" + cambios if cambios else "El lago no cambió."))
    if sin_calendario or fallo:
        print("OJO: " + ("el calendario del BCR no respondió; " if sin_calendario else "") + ("alguna serie no llegó (ver arriba)." if fallo else ""))
        sys.exit(2)


if __name__ == "__main__":
    main()
