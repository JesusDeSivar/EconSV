#!/usr/bin/env python3
"""Arma los datos del sitio (sitio/datos/) desde el lago. No usa la red.

    python tuberias/sitio.py

El sitio es estático: sitio/index.html, app.js y estilo.css están en el repositorio, y este script
escribe lo que leen, que no se versiona (lo reconstruye GitHub Actions antes de publicar):

    sitio/datos/datos.js              indicadores (catalogo/indicadores.toml + lago/oro), series y calendario
    sitio/datos/noticias.js           las notas de las últimas ediciones
    sitio/datos/noticias/<día>.xlsx   el Excel de cada edición (y su .csv)
    sitio/datos/descargas/            cada serie del BCR en CSV (plata) y en Excel (una columna por variable)

Los datos van como archivos .js y no .json para que el sitio abra también desde el disco, sin servidor.
"""
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendario  # noqa: E402
import noticias  # noqa: E402
import rutas  # noqa: E402

SECCIONES = [("actividad", "Actividad"), ("precios", "Precios"), ("externo", "Sector externo"),
             ("turismo", "Turismo"), ("construccion", "Construcción")]
EDICIONES_EN_SITIO = 30
DATOS = rutas.SITIO / "datos"


def js(nombre, variable, obj):
    texto = f"window.{variable} = " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (DATOS / nombre).write_text(texto, encoding="utf-8")
    return len(texto)


def indicadores():
    oro = {}
    with open(rutas.ORO / "indicadores.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = oro.setdefault((r["indicador"], r["linea"], r["vista"]), {"p": [], "v": []})
            d["p"].append(r["periodo"])
            d["v"].append(float(r["valor"]))
    out = []
    for ind in rutas.catalogo("indicadores")["indicador"]:
        lineas = []
        for linea in ind["linea"]:
            vistas = {v: oro[(ind["clave"], linea["nombre"], v)] for v in linea.get("vistas", ind["vistas"])
                      if (ind["clave"], linea["nombre"], v) in oro}
            lineas.append({"nombre": linea["nombre"], "serie": linea["serie"], "id": linea["id"], "vistas": vistas})
        out.append({"clave": ind["clave"], "seccion": ind["seccion"], "titulo": ind["titulo"],
                    "nota": ind.get("nota", ""), "frecuencia": ind["frecuencia"], "naturaleza": ind["naturaleza"],
                    "unidad": ind["unidad"], "tipo": ind.get("tipo", "lineas"), "portada": ind.get("portada", False),
                    "vistas": ind["vistas"], "lineas": lineas,
                    "series": sorted({l["serie"] for l in ind["linea"]})})
    return out


def series(hoy):
    lock = json.loads(rutas.LOCK_BCR.read_text(encoding="utf-8"))["series"]
    estado = {e["clave"]: e for e in calendario.estado(hoy)}
    out = {}
    for s in rutas.series():
        l, e = lock.get(s["clave"], {}), estado[s["clave"]]
        out[s["clave"]] = {"nombre": s["nombre"], "frecuencia": s["frecuencia"], "url": l.get("url", ""),
                           "desde": l.get("desde", ""), "hasta": l.get("hasta", ""), "tomado": l.get("tomado", ""),
                           "variables": l.get("variables", 0), "proximo": e["proximo"], "esperado": e["esperado"],
                           "origen": e["origen"]}
    return out


def calendario_filas():
    with open(rutas.PLATA / "calendario.csv", encoding="utf-8", newline="") as fh:
        return [{"serie": r["serie"], "periodo": r["periodo"], "fecha": r["fecha_esperada"], "origen": r["origen"],
                 "en_lago": r["en_lago"] == "si"} for r in csv.DictReader(fh)]


def descargas():
    """Cada serie de plata en CSV y en un Excel ancho: una fila por período, una columna por variable."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    carpeta = DATOS / "descargas"
    carpeta.mkdir(parents=True, exist_ok=True)
    shutil.copy(rutas.ORO / "indicadores.csv", carpeta / "indicadores.csv")
    shutil.copy(rutas.PLATA / "bcr_variables.csv", carpeta / "bcr_variables.csv")
    with open(rutas.PLATA / "bcr_variables.csv", encoding="utf-8", newline="") as fh:
        dic = list(csv.DictReader(fh))
    for s in rutas.series():
        origen = rutas.PLATA / f"bcr_{s['clave']}.csv"
        shutil.copy(origen, carpeta / origen.name)
        with open(origen, encoding="utf-8", newline="") as fh:
            filas = list(csv.DictReader(fh))
        variables = [d for d in dic if d["serie"] == s["clave"] and int(d["observaciones"])]
        col = {d["variable_id"]: i + 2 for i, d in enumerate(variables)}
        periodos = sorted({r["periodo"] for r in filas})
        fila = {p: i + 4 for i, p in enumerate(periodos)}
        wb = Workbook()
        ws = wb.active
        ws.title = "Datos"
        ws["A1"] = s["nombre"]
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"] = (f"Fuente: Banco Central de Reserva de El Salvador · {variables[0]['unidad'] if variables else ''} · "
                    f"https://estadisticas.bcr.gob.sv/serie/{s['slug']}")
        ws.cell(row=3, column=1, value="Período").font = Font(bold=True)
        for d in variables:
            ws.cell(row=3, column=col[d["variable_id"]], value=d["ruta"]).font = Font(bold=True)
        for p, i in fila.items():
            ws.cell(row=i, column=1, value=p)
        for r in filas:
            if r["variable_id"] in col:
                ws.cell(row=fila[r["periodo"]], column=col[r["variable_id"]],
                        value=float(r["valor"]) if r["valor"] else r["marca"])
        ws.freeze_panes = "B4"
        ws.column_dimensions["A"].width = 12
        wb.save(carpeta / f"bcr_{s['clave']}.xlsx")


def notas():
    por = noticias.ediciones()
    cerradas = sorted(p.stem for p in (rutas.ORO / "noticias").glob("*.csv"))
    carpeta = DATOS / "noticias"
    carpeta.mkdir(parents=True, exist_ok=True)
    recientes = sorted(por)[-EDICIONES_EN_SITIO:]
    for ed in recientes:
        noticias.excel(por[ed], carpeta / f"{ed}.xlsx", f"Resumen de noticias · edición del {ed}")
        (carpeta / f"{ed}.csv").write_text(noticias.texto_csv(noticias.COL_EDICION, por[ed]), encoding="utf-8-sig", newline="")
    filas = [[n["edicion"], n["fecha_hora"], noticias.CATEGORIAS.index(n["categoria"]), n["fuente"], n["titular"],
              n["resumen"], n["url"]] for ed in recientes for n in por[ed]]
    return {"categorias": noticias.CATEGORIAS, "ediciones": recientes, "cerradas": [e for e in cerradas if e in recientes],
            "hora_de_corte": noticias.cfg()["general"]["hora_de_corte"], "notas": filas}


def main():
    ahora = dt.datetime.now(ZoneInfo("America/El_Salvador"))
    if DATOS.exists():
        shutil.rmtree(DATOS)
    DATOS.mkdir(parents=True)
    n1 = js("datos.js", "ECONSV", {
        "generado": ahora.strftime("%Y-%m-%dT%H:%M"),
        "secciones": [{"clave": c, "nombre": n} for c, n in SECCIONES],
        "indicadores": indicadores(), "series": series(ahora.date()), "calendario": calendario_filas()})
    n2 = js("noticias.js", "ECONSV_NOTICIAS", notas() if (rutas.PLATA / "noticias.csv").exists() else
            {"categorias": noticias.CATEGORIAS, "ediciones": [], "cerradas": [], "notas": []})
    descargas()
    print(f"  sitio/datos/: datos.js {n1 // 1024} KB, noticias.js {n2 // 1024} KB, "
          f"{len(list((DATOS / 'descargas').iterdir()))} descargas")


if __name__ == "__main__":
    main()
