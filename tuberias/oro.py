#!/usr/bin/env python3
"""De plata a oro: lo que EconSV calcula sobre las cifras del BCR.

    python tuberias/oro.py            escribe lago/oro/indicadores.csv y su catálogo
    python tuberias/oro.py --check    sin escribir: falla si oro no es lo que da plata

Lee catalogo/indicadores.toml y, para cada línea de cada indicador, calcula sus vistas:

    nivel              la cifra como la publica el BCR
    var_anual          % contra el mismo período del año anterior
    var_periodo        % contra el período anterior
    suma_anual         suma de los últimos 12 meses o 4 trimestres, solo con la ventana completa
    pct_pib            % del PIB nominal de los últimos cuatro trimestres (ver `pct_pib`)
    meses_importacion  saldo ÷ promedio mensual de importaciones de mercancías (CIF) de 12 meses

Todo sale de una sola cuenta, la del BCR: ninguna vista mezcla otra fuente. Columnas:
indicador, linea, vista, fecha, periodo, valor.

lago/oro/indicadores_catalogo.csv dice qué es cada serie de esa tabla, una fila por (indicador, línea,
vista): su título, sección, frecuencia y unidad de la vista, de qué variable del BCR sale, el tramo
que cubre y su último valor. Es lo que necesita quien lee oro desde fuera (una hoja de cálculo, R,
Python) para rotular sin abrir catalogo/indicadores.toml.
"""
import argparse
import csv
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rutas  # noqa: E402

PASO = {"M": 12, "T": 4, "A": 1}
COLUMNAS = ["indicador", "linea", "vista", "fecha", "periodo", "valor"]
COL_CATALOGO = ["indicador", "linea", "vista", "seccion", "titulo", "frecuencia", "unidad", "naturaleza", "tipo",
                "serie_bcr", "variable_id", "desde", "hasta", "ultimo_valor", "nota"]
PIB_TRIMESTRAL = ("pib_trimestral", 17322)          # PIB nominal trimestral, enfoque de la producción
IMPORTACIONES = ("balanza_comercial", 8628)         # importaciones de mercancías, CIF
VISTAS = ["nivel", "var_anual", "var_periodo", "suma_anual", "pct_pib", "meses_importacion"]


class Plata:
    """Las tablas de plata, leídas una vez: valores por (serie, variable_id) y por (año, subperíodo)."""

    def __init__(self):
        self._series, self._nombres = {}, {}

    def _cargar(self, serie):
        if serie in self._series:
            return
        fr = rutas.serie(serie)["frecuencia"]
        datos = {}
        with open(rutas.PLATA / f"bcr_{serie}.csv", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                vid = int(r["variable_id"])
                self._nombres[(serie, vid)] = r["variable"]
                if r["valor"] == "":
                    continue
                a = int(r["periodo"][:4])
                sub = 1 if fr == "A" else int(r["periodo"][6:] if fr == "T" else r["periodo"][5:])
                datos.setdefault(vid, {})[(a, sub)] = float(r["valor"])
        self._series[serie] = (fr, datos)

    def valores(self, serie, vid):
        self._cargar(serie)
        fr, datos = self._series[serie]
        if vid not in datos:
            raise SystemExit(f"oro: la serie «{serie}» no tiene cifras de la variable {vid}")
        return fr, datos[vid]

    def nombre(self, serie, vid):
        self._cargar(serie)
        return self._nombres.get((serie, vid))


def atras(a, sub, fr, k):
    n = PASO[fr]
    i = a * n + (sub - 1) - k
    return i // n, i % n + 1


def etiqueta(a, sub, fr):
    return str(a) if fr == "A" else f"{a}-T{sub}" if fr == "T" else f"{a}-{sub:02d}"


def fecha(a, sub, fr):
    mes = 1 if fr == "A" else (sub - 1) * 3 + 1 if fr == "T" else sub
    return f"{a}-{mes:02d}-01"


def variacion(v, fr, k):
    out = {}
    for (a, sub), x in v.items():
        y = v.get(atras(a, sub, fr, k))
        if y is not None and y > 0 and x is not None:
            out[(a, sub)] = (x / y - 1) * 100
    return out


def suma_anual(v, fr):
    n, out = PASO[fr], {}
    for (a, sub) in v:
        ventana = [v.get(atras(a, sub, fr, k)) for k in range(n)]
        if all(x is not None for x in ventana):
            out[(a, sub)] = sum(ventana)
    return out


def pct_pib(v, fr, naturaleza, pib4):
    """(valores, frecuencia de la vista). El denominador es siempre el PIB nominal de cuatro
    trimestres que terminan en el trimestre del dato. Un flujo se anualiza antes (12 meses o 4
    trimestres); un saldo se toma a fin de trimestre. De una serie mensual sale un punto por trimestre."""
    base = suma_anual(v, fr) if naturaleza == "flujo" else v
    out = {}
    for (a, sub), x in base.items():
        if fr == "M":
            if sub % 3:
                continue
            q = (a, sub // 3)
        else:
            q = (a, sub)
        d = pib4.get(q)
        if d:
            out[q] = x / d * 100
    return out, "T"


def meses_importacion(v, fr, imp12):
    return {k: x / (imp12[k] / 12) for k, x in v.items() if imp12.get(k)}


def unidad_de(ind, vista, fr):
    """La unidad en que queda una vista."""
    if vista in ("var_anual", "var_periodo"):
        return "%"
    if vista == "pct_pib":
        return "% del PIB"
    if vista == "meses_importacion":
        return "Meses de importación de mercancías"
    if vista == "suma_anual":
        return ind["unidad"] + (", suma de 12 meses" if fr == "M" else ", suma de 4 trimestres")
    return ind["unidad"]


def cifra(x):
    return f"{x:.4f}".rstrip("0").rstrip(".")


def norma(x):
    return re.sub(r"[^a-z0-9]+", "", x.lower())


def construir():
    plata = Plata()
    _, pib = plata.valores(*PIB_TRIMESTRAL)
    pib4 = suma_anual(pib, "T")
    _, imp = plata.valores(*IMPORTACIONES)
    imp12 = suma_anual(imp, "M")
    filas, cat, vistos = [], [], set()
    for ind in rutas.catalogo("indicadores")["indicador"]:
        if ind["clave"] in vistos:
            raise SystemExit(f"oro: el indicador «{ind['clave']}» está dos veces en el catálogo")
        vistos.add(ind["clave"])
        for v in ind["vistas"]:
            if v not in VISTAS:
                raise SystemExit(f"oro: {ind['clave']}: vista desconocida «{v}»")
        for linea in ind["linea"]:
            fr, v = plata.valores(linea["serie"], linea["id"])
            if fr != ind["frecuencia"]:
                raise SystemExit(f"oro: {ind['clave']}: la serie «{linea['serie']}» es {fr}, no {ind['frecuencia']}")
            real = plata.nombre(linea["serie"], linea["id"]) or ""
            if norma(linea["rotulo"]) not in norma(real):
                raise SystemExit(f"oro: {ind['clave']}: la variable {linea['id']} de «{linea['serie']}» se llama "
                                 f"«{real}», no «{linea['rotulo']}»: el BCR cambió el cuadro")
            for vista in linea.get("vistas", ind["vistas"]):
                frv = fr
                if vista == "nivel":
                    r = v
                elif vista == "var_anual":
                    r = variacion(v, fr, PASO[fr])
                elif vista == "var_periodo":
                    r = variacion(v, fr, 1)
                elif vista == "suma_anual":
                    if ind["naturaleza"] != "flujo" or fr == "A":
                        raise SystemExit(f"oro: {ind['clave']}: suma_anual solo vale para un flujo mensual o trimestral")
                    r = suma_anual(v, fr)
                elif vista == "pct_pib":
                    if ind["naturaleza"] == "indice" or fr == "A":
                        raise SystemExit(f"oro: {ind['clave']}: pct_pib no vale para un índice ni para una serie anual")
                    r, frv = pct_pib(v, fr, ind["naturaleza"], pib4)
                else:
                    r = meses_importacion(v, fr, imp12)
                for (a, sub) in sorted(r):
                    filas.append([ind["clave"], linea["nombre"], vista, fecha(a, sub, frv), etiqueta(a, sub, frv),
                                  cifra(r[(a, sub)])])
                if r:
                    k0, k1 = min(r), max(r)
                    cat.append([ind["clave"], linea["nombre"], vista, ind["seccion"], ind["titulo"], frv,
                                unidad_de(ind, vista, fr), ind["naturaleza"], ind.get("tipo", "lineas"),
                                linea["serie"], linea["id"], etiqueta(*k0, frv), etiqueta(*k1, frv), cifra(r[k1]),
                                ind.get("nota", "")])
    return texto_csv(COLUMNAS, filas), texto_csv(COL_CATALOGO, cat)


def texto_csv(columnas, filas):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columnas)
    w.writerows(filas)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    viejos = 0
    for nombre, texto in zip(("indicadores.csv", "indicadores_catalogo.csv"), construir()):
        destino = rutas.ORO / nombre
        igual = destino.exists() and destino.read_text(encoding="utf-8") == texto
        if args.check:
            if not igual:
                print(f"  {rutas.rel(destino)} no es lo que da plata")
                viejos += 1
            continue
        if not igual:
            rutas.ORO.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding="utf-8", newline="")
        print(f"  {rutas.rel(destino)}: {texto.count(chr(10)) - 1} filas{'' if not igual else ' (sin cambios)'}")
    if args.check:
        print(f"oro --check: {'al día' if not viejos else str(viejos) + ' archivos por reconstruir'}")
        sys.exit(1 if viejos else 0)


if __name__ == "__main__":
    main()
