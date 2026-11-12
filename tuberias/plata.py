#!/usr/bin/env python3
"""De bronce a plata: lo que el BCR publicó, en tablas largas y ordenadas.

    python tuberias/plata.py                    todas las series
    python tuberias/plata.py --solo reservas    algunas
    python tuberias/plata.py --check            sin escribir: falla si plata no es lo que da bronce

Por cada serie de catalogo/series.toml escribe lago/plata/bcr_<clave>.csv:

    fecha        primer día del período (2026-10-01; un trimestre, su primer mes; un año, enero)
    periodo      2026-10 · 2026-T2 · 2025
    variable_id  el número de la variable en el portal: es la llave estable
    codigo       la numeración del cuadro («1.1.2»), si la trae
    variable     el rótulo como lo muestra el portal
    valor        la cifra; vacío si el BCR marca la celda
    estado       p preliminar · e estimado · r revisado, como lo marca el BCR en el período
    marca        ND (no disponible) · C (confidencial), cuando no hay cifra

y lago/plata/bcr_variables.csv, el diccionario: cada variable con su serie, su lugar en el cuadro
(`ruta`: los rótulos de arriba hacia abajo), su unidad y el tramo que cubre.

Si una cifra de un período que ya estaba cambia, queda anotada en lago/plata/revisiones.csv.
Aquí no se calcula nada: eso es oro.py.
"""
import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bcr  # noqa: E402
import rutas  # noqa: E402

COLUMNAS = ["fecha", "periodo", "variable_id", "codigo", "variable", "valor", "estado", "marca"]
COL_VARIABLES = ["serie", "orden", "variable_id", "codigo", "variable", "ruta", "unidad", "frecuencia",
                 "desde", "hasta", "observaciones"]
COL_REVISIONES = ["detectado", "serie", "variable_id", "variable", "periodo", "antes", "despues"]


def cifra(v):
    return f"{v:.6f}".rstrip("0").rstrip(".") if v is not None else ""


def rutas_de(variables):
    """El lugar de cada rótulo en el cuadro. Una fila numerada cuelga de la fila cuyo código es su
    prefijo; una sin número («Crédito», «Débito»), de la última numerada."""
    por_codigo, ultima, out = {}, None, []
    for v in variables:
        cod, nombre = bcr.rotulo(v["nombre"])
        if cod:
            padre = por_codigo.get(cod.rpartition(".")[0])
            ruta = (padre + " › " if padre else "") + nombre
            por_codigo[cod] = ruta
            ultima = ruta
        else:
            ruta = (ultima + " › " if ultima else "") + nombre
        out.append((cod, nombre, ruta))
    return out


def construir(s):
    """(texto del CSV, filas del diccionario) de una serie, desde su bronce."""
    b = json.loads((rutas.BRONCE_BCR / f"{s['clave']}.json").read_text(encoding="utf-8"))
    obs, _ = bcr.interpretar(b, s["frecuencia"])
    fr = s["frecuencia"]
    nombres = rutas_de(b["variables"])
    obs.sort(key=lambda o: (o[3], o[0], o[1]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNAS)
    tramo = {}
    for a, sub, est, i, val, marca in obs:
        cod, nombre, _ = nombres[i]
        w.writerow([bcr.fecha(a, sub, fr), bcr.etiqueta(a, sub, fr), b["variables"][i]["id"], cod, nombre,
                    cifra(val), est, marca])
        if val is not None:
            t = tramo.setdefault(i, [bcr.etiqueta(a, sub, fr), "", 0])
            t[1], t[2] = bcr.etiqueta(a, sub, fr), t[2] + 1
    dic = []
    for i, v in enumerate(b["variables"]):
        cod, nombre, ruta = nombres[i]
        d, h, n = tramo.get(i, ["", "", 0])
        dic.append([s["clave"], i + 1, v["id"], cod, nombre, ruta, b.get("unidades") or "", fr, d, h, n])
    return buf.getvalue(), dic


def revisiones(clave, antes, despues):
    """Las cifras de períodos que ya estaban y cambiaron."""
    def leer(texto):
        return {(r["variable_id"], r["periodo"]): r for r in csv.DictReader(io.StringIO(texto))}
    a, d = leer(antes), leer(despues)
    hoy = dt.date.today().isoformat()
    return [[hoy, clave, k[0], d[k]["variable"], k[1], a[k]["valor"] or a[k]["marca"], d[k]["valor"] or d[k]["marca"]]
            for k in a if k in d and (a[k]["valor"], a[k]["marca"]) != (d[k]["valor"], d[k]["marca"])]


def csv_texto(cols, filas):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    w.writerows(filas)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--solo", type=lambda x: [y for y in x.split(",") if y])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rutas.PLATA.mkdir(parents=True, exist_ok=True)
    viejos, nuevas_rev, dic = 0, [], []
    p_dic = rutas.PLATA / "bcr_variables.csv"
    previo = {}
    if p_dic.exists():
        for r in csv.DictReader(io.StringIO(p_dic.read_text(encoding="utf-8"))):
            previo.setdefault(r["serie"], []).append([r[c] for c in COL_VARIABLES])
    for s in rutas.series():
        clave = s["clave"]
        if args.solo and clave not in args.solo:
            dic += previo.get(clave, [])
            continue
        if not (rutas.BRONCE_BCR / f"{clave}.json").exists():
            print(f"  {clave}: no está en bronce (python tuberias/traer.py bcr --solo {clave})")
            viejos += 1
            continue
        texto, d = construir(s)
        dic += d
        destino = rutas.PLATA / f"bcr_{clave}.csv"
        antes = destino.read_text(encoding="utf-8") if destino.exists() else None
        if antes == texto:
            continue
        if args.check:
            print(f"  {rutas.rel(destino)}: no es lo que da bronce")
            viejos += 1
            continue
        if antes is not None:
            rev = revisiones(clave, antes, texto)
            nuevas_rev += rev
            print(f"  {clave}: {texto.count(chr(10)) - 1} filas ({len(rev)} cifras revisadas)")
        else:
            print(f"  {clave}: {texto.count(chr(10)) - 1} filas (nueva)")
        destino.write_text(texto, encoding="utf-8", newline="")
    texto_dic = csv_texto(COL_VARIABLES, [[str(x) for x in f] for f in dic])
    if not p_dic.exists() or p_dic.read_text(encoding="utf-8") != texto_dic:
        if args.check:
            print(f"  {rutas.rel(p_dic)}: no es lo que da bronce")
            viejos += 1
        else:
            p_dic.write_text(texto_dic, encoding="utf-8", newline="")
    if nuevas_rev and not args.check:
        p_rev = rutas.PLATA / "revisiones.csv"
        nuevo = not p_rev.exists()
        with open(p_rev, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            if nuevo:
                w.writerow(COL_REVISIONES)
            w.writerows(nuevas_rev)
        print(f"  {len(nuevas_rev)} revisiones anotadas en {rutas.rel(p_rev)}")
    if args.check:
        print(f"plata --check: {viejos} archivos por reconstruir")
        sys.exit(1 if viejos else 0)
    sys.exit(1 if viejos else 0)


if __name__ == "__main__":
    main()
