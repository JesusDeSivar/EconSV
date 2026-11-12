#!/usr/bin/env python3
"""El calendario interno: cuándo se espera cada dato, y qué toca traer hoy.

    python tuberias/calendario.py                    la tabla de hoy
    python tuberias/calendario.py --hoy 2026-11-24   como si hoy fuera esa fecha
    python tuberias/calendario.py toca               solo las claves que tocan, separadas por coma
    python tuberias/calendario.py toca --json        lo mismo con su detalle, para otra herramienta
    python tuberias/calendario.py sincronizar        baja el calendario de divulgación del BCR

De dónde sale la fecha esperada de un período:

  bcr      el BCR la anuncia en su calendario de divulgación (/api/calendario-api), con el período al
           que corresponde («Oct.26», «T3-26», «2025»). Cada serie de catalogo/series.toml dice con qué
           título la anuncia el BCR.
  rezago   el calendario del BCR todavía no anuncia el período que sigue al corte del lago: se estima
           con el fin de ese período más `rezago_dias` de la serie.

Una serie «toca» desde la fecha esperada del primer período que el lago no tiene, y sigue tocando en
cada corrida hasta que ese período llega; pasados DIAS_ATRASO días está «atrasada», que es cuando
conviene mirar si el BCR cambió la fecha, la dirección o la forma del cuadro. El corte del lago se lee
de lago/bronce/bcr/fuentes.lock.json. GitHub Actions corre este archivo como latido: el cron no decide
qué se trae, lo decide el calendario.

lago/bronce/calendario_bcr.json guarda los anuncios del BCR, acumulados por su id; lago/plata/
calendario.csv es la tabla que lee el sitio: serie, período, fecha esperada, origen y si ya está en el lago.
"""
import argparse
import calendar
import csv
import datetime as dt
import io
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rutas  # noqa: E402

API = "https://estadisticas.bcr.gob.sv/api/calendario-api"
AGENTE = "Mozilla/5.0 (compatible; lector-de-estadisticas-publicas)"
DIAS_ATRASO = 10
MES3 = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
        "oct": 10, "nov": 11, "dic": 12}
PASO = {"M": 12, "T": 4, "A": 1}
COLUMNAS = ["serie", "nombre", "frecuencia", "periodo", "fecha_esperada", "origen", "en_lago"]


def hoy_sv():
    return dt.datetime.now(ZoneInfo("America/El_Salvador")).date()


def norma(x):
    return re.sub(r"[^a-z0-9]+", "", (x or "").lower())


# ------------------------------------------------------------------ períodos
def periodo_evento(x):
    """«Oct.26» → («M», 2026, 10) · «T3-26» → («T», 2026, 3) · «2025» → («A», 2025, 1)."""
    x = (x or "").strip()
    m = re.match(r"^([A-Za-z]{3})\.?\s*(\d{2})$", x)
    if m and m.group(1).lower() in MES3:
        return "M", 2000 + int(m.group(2)), MES3[m.group(1).lower()]
    m = re.match(r"^T([1-4])-(\d{2})$", x)
    if m:
        return "T", 2000 + int(m.group(2)), int(m.group(1))
    m = re.match(r"^(\d{4})$", x)
    if m:
        return "A", int(m.group(1)), 1
    return None


def periodo_lago(x):
    """«2026-10» · «2026-T2» · «2025» → (año, subperíodo)."""
    m = re.match(r"^(\d{4})(?:-T(\d)|-(\d{2}))?$", x)
    return int(m.group(1)), int(m.group(2) or m.group(3) or 1)


def etiqueta(a, sub, fr):
    return str(a) if fr == "A" else f"{a}-T{sub}" if fr == "T" else f"{a}-{sub:02d}"


def siguiente(a, sub, fr):
    i = a * PASO[fr] + sub
    return i // PASO[fr], i % PASO[fr] + 1


def fin_de_periodo(a, sub, fr):
    mes = 12 if fr == "A" else sub * 3 if fr == "T" else sub
    return dt.date(a, mes, calendar.monthrange(a, mes)[1])


# ------------------------------------------------------------------ el calendario del BCR
def leer_bronce():
    if rutas.BRONCE_CALENDARIO.exists():
        return json.loads(rutas.BRONCE_CALENDARIO.read_text(encoding="utf-8"))
    return {"fuente": API, "eventos": []}


def sincronizar(hoy=None):
    """Baja los anuncios de −60 a +240 días y los suma a los ya guardados (por id)."""
    import requests
    hoy = hoy or hoy_sv()
    r = requests.get(API, params={"lang": "es", "start": (hoy - dt.timedelta(days=60)).isoformat(),
                                  "end": (hoy + dt.timedelta(days=240)).isoformat()},
                     headers={"User-Agent": AGENTE}, timeout=(20, 120))
    r.raise_for_status()
    nuevos = r.json()
    if not isinstance(nuevos, list) or not nuevos or not all("start" in e and "title" in e for e in nuevos):
        raise SystemExit("calendario: la API del BCR no devolvió una lista de anuncios")
    b = leer_bronce()
    por_id = {e["id"]: e for e in b["eventos"]}
    antes = json.dumps(por_id, sort_keys=True)
    for e in nuevos:
        por_id[e["id"]] = {"id": e["id"], "title": e["title"], "start": e["start"], "url": e.get("url")}
    cambio = json.dumps(por_id, sort_keys=True) != antes
    if cambio:
        b["eventos"] = sorted(por_id.values(), key=lambda e: (e["start"], e["id"]))
        rutas.BRONCE_CALENDARIO.parent.mkdir(parents=True, exist_ok=True)
        rutas.BRONCE_CALENDARIO.write_text(
            "{\n \"fuente\": " + json.dumps(API) + ",\n \"eventos\": [\n" +
            ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in b["eventos"]) + "\n ]\n}\n", encoding="utf-8")
    print(f"  calendario del BCR: {len(nuevos)} anuncios en la ventana, {len(por_id)} guardados"
          f"{'' if cambio else ' (sin cambios)'}")
    escribir_plata()
    return 0


def cortes():
    """El último período con cifras que el lago tiene de cada serie."""
    if not rutas.LOCK_BCR.exists():
        return {}
    lock = json.loads(rutas.LOCK_BCR.read_text(encoding="utf-8"))
    return {k: periodo_lago(v["hasta"]) for k, v in lock["series"].items()}


def esperados():
    """Por serie: [(año, sub, fecha esperada, origen)], en orden; lo que el BCR anuncia y, si no
    anuncia el período que sigue al corte, la estimación por rezago."""
    eventos = {}
    for e in leer_bronce()["eventos"]:
        p = periodo_evento(e.get("url"))
        if p:
            eventos.setdefault(norma(e["title"]), []).append((p, dt.date.fromisoformat(e["start"][:10])))
    corte, out = cortes(), {}
    for s in rutas.series():
        fr, filas = s["frecuencia"], {}
        for (fe, a, sub), f in eventos.get(norma(s.get("calendario")), []):
            if fe == fr:
                k = (a, sub)
            elif fr == "A" and fe == "T" and sub == 4:
                k = (a, 1)                    # el dato anual sale con el cuarto trimestre de su año
            else:
                continue
            if k not in filas or f < filas[k][0]:
                filas[k] = (f, "bcr")
        c = corte.get(s["clave"])
        if c:
            prox = siguiente(*c, fr)
            if prox not in filas:
                filas[prox] = (fin_de_periodo(*prox, fr) + dt.timedelta(days=s["rezago_dias"]), "rezago")
        out[s["clave"]] = [(a, sub, f, o) for (a, sub), (f, o) in sorted(filas.items())]
    return out


def escribir_plata():
    corte, esp = cortes(), esperados()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNAS)
    for s in rutas.series():
        c = corte.get(s["clave"])
        for a, sub, f, o in esp[s["clave"]]:
            w.writerow([s["clave"], s["nombre"], s["frecuencia"], etiqueta(a, sub, s["frecuencia"]), f.isoformat(), o,
                        "si" if c and (a, sub) <= c else "no"])
    destino = rutas.PLATA / "calendario.csv"
    if not destino.exists() or destino.read_text(encoding="utf-8") != buf.getvalue():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(buf.getvalue(), encoding="utf-8", newline="")
        print(f"  {rutas.rel(destino)}: {buf.getvalue().count(chr(10)) - 1} filas")


# ------------------------------------------------------------------ qué toca
def estado(hoy):
    corte, esp, out = cortes(), esperados(), []
    for s in rutas.series():
        clave, fr = s["clave"], s["frecuencia"]
        c = corte.get(clave)
        if c is None:
            out.append({"clave": clave, "nombre": s["nombre"], "frecuencia": fr, "corte": "", "proximo": "",
                        "esperado": "", "origen": "", "situacion": "toca", "dias": None})
            continue
        pend = [(a, sub, f, o) for a, sub, f, o in esp[clave] if (a, sub) > c]
        a, sub, f, o = pend[0]
        dias = (hoy - f).days
        situacion = "al día" if dias < 0 else "toca" if dias <= DIAS_ATRASO else "atrasada"
        out.append({"clave": clave, "nombre": s["nombre"], "frecuencia": fr, "corte": etiqueta(*c, fr),
                    "proximo": etiqueta(a, sub, fr), "esperado": f.isoformat(), "origen": o,
                    "situacion": situacion, "dias": dias})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("orden", nargs="?", choices=["toca", "sincronizar", "plata"])
    ap.add_argument("--hoy", type=dt.date.fromisoformat)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    hoy = a.hoy or hoy_sv()
    if a.orden == "sincronizar":
        sys.exit(sincronizar(hoy))
    if a.orden == "plata":
        escribir_plata()
        return
    es = estado(hoy)
    tocan = [e for e in es if e["situacion"] != "al día"]
    if a.orden == "toca":
        if a.json:
            print(json.dumps({"hoy": hoy.isoformat(), "tocan": tocan}, ensure_ascii=False, indent=1))
        else:
            print(",".join(e["clave"] for e in tocan))
        salida = os.environ.get("GITHUB_OUTPUT")
        if salida:
            with open(salida, "a", encoding="utf-8") as fh:
                fh.write(f"claves={','.join(e['clave'] for e in tocan)}\n")
                fh.write(f"atrasadas={','.join(e['clave'] for e in tocan if e['situacion'] == 'atrasada')}\n")
        return
    print(f"Calendario al {hoy.isoformat()} (hora de El Salvador)\n")
    print(f"  {'serie':<26} {'el lago llega a':<16} {'próximo':<9} {'se espera':<11} {'origen':<7} situación")
    for e in es:
        print(f"  {e['clave']:<26} {e['corte']:<16} {e['proximo']:<9} {e['esperado']:<11} {e['origen']:<7} {e['situacion']}")
    print(f"\n{len(tocan)} de {len(es)} series tocan" + (": " + ", ".join(e["clave"] for e in tocan) if tocan else "."))


if __name__ == "__main__":
    main()
