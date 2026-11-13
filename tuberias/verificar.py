#!/usr/bin/env python3
"""La compuerta: nada se publica si esto no pasa. No usa la red.

    python tuberias/verificar.py

Qué revisa:

  bronce      cada archivo del BCR contra el sha256 de su lock
  plata       es exactamente lo que da bronce (plata.py --check), y cada serie viene sin huecos
  identidades las sumas que el propio BCR imprime (un total contra sus partes), en cada período
  oro         es exactamente lo que da plata (oro.py --check); eso incluye que cada variable de
              catalogo/indicadores.toml siga llamándose como el catálogo espera
  calendario  cada serie tiene un próximo período con fecha esperada
  noticias    categorías válidas, sin texto largo, y ninguna nota que mencione El Salvador en una
              categoría internacional; ningún medio de
              [medios] fuera, y `orden` de 1 en adelante en cada (edición, categoría)

Las cifras del BCR vienen redondeadas, así que una suma de n de ellas puede diferir medio último
decimal por cada una solo por redondeo: la tolerancia de una identidad es (n + 1) medios decimales.
Casi todo viene a dos decimales (0.005 n + 0.005); las reservas anteriores a 2015 se publicaron a
uno, y su tolerancia es 0.05 n + 0.05. Dos períodos de las reservas no suman en el propio cuadro del
BCR: quedan fijados en FIJADAS con la diferencia publicada, y si el BCR los corrige la compuerta avisa.
"""
import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rutas  # noqa: E402

# (serie, total, [(signo, variable_id), ...], qué es[, decimales con que se publicó])
IDENTIDADES = [
    ("reservas", 18089, [(1, 18090), (-1, 18096)], "RIN = activos de reserva − pasivos de corto plazo", 1),
    ("reservas", 18090, [(1, 18091), (1, 18092), (1, 18093), (1, 18094), (1, 18095)], "activos de reserva = sus componentes", 1),
    ("reservas", 18096, [(1, 18097), (1, 18098), (1, 18099)], "pasivos de corto plazo = sus componentes", 1),
    ("balanza_comercial", 8632, [(1, 8618), (-1, 8628)], "saldo comercial = exportaciones − importaciones"),
    ("pib_trimestral", 17320, [(1, i) for i in range(17301, 17320)], "valor agregado bruto = suma de actividades"),
    ("pib_trimestral", 17322, [(1, 17320), (1, 17321)], "PIB = valor agregado + impuestos netos"),
    ("pib_trimestral", 18965, [(1, 17324), (1, 17327), (1, 17329), (-1, 17330)], "PIB por el gasto = C + FBK + X − M"),
    ("pib_trimestral", 17322, [(1, 18965)], "PIB por la producción = PIB por el gasto"),
    ("pib_anual", 16789, [(1, 16802)], "PIB anual por la producción = por el gasto"),
    ("pib_anual", 16789, [(1, 16809)], "PIB anual por la producción = por el ingreso"),
    ("pii", 8763, [(1, 8764), (-1, 8784)], "PII neta = activos − pasivos"),
    ("balanza_pagos", 15167, [(1, 15168), (-1, 15169)], "cuenta corriente = crédito − débito"),
    ("balanza_pagos", 15194, [(1, 15195), (-1, 15196)], "viajes = crédito − débito"),
]
# (serie, total, período) → total − suma de partes, tal como lo publica el BCR
FIJADAS = {
    ("reservas", 18090, "2003-05"): -1.0,     # los componentes suman 1,674.9 y el cuadro dice 1,673.9
    ("reservas", 18096, "2020-06"): -1.42,    # «otros pasivos» repite el total y deja fuera los intereses
}
CATEGORIAS = ["Internacional – EUA", "Internacional – LATAM", "Internacional – Resto del mundo",
              "El Salvador – Nacionales", "El Salvador – Fiscales"]
PASO = {"M": 12, "T": 4, "A": 1}


def leer(serie):
    with open(rutas.PLATA / f"bcr_{serie}.csv", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def indice(periodo, fr):
    a = int(periodo[:4])
    sub = 1 if fr == "A" else int(periodo[6:] if fr == "T" else periodo[5:])
    return a * PASO[fr] + sub - 1


def correr(orden):
    r = subprocess.run([sys.executable] + orden, capture_output=True, text=True, cwd=rutas.RAIZ)
    return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()


def main():
    fallas, n = [], 0

    def paso(nombre, ok, detalle=""):
        nonlocal n
        n += 1
        print(f"  {'ok   ' if ok else 'FALLA'} {nombre}{' — ' + detalle if detalle else ''}")
        if not ok:
            fallas.append(nombre)

    for nombre, orden in [("bronce: cada archivo es el de su lock", ["tuberias/traer.py", "verificar"]),
                          ("plata es lo que da bronce", ["tuberias/plata.py", "--check"]),
                          ("oro es lo que da plata", ["tuberias/oro.py", "--check"])]:
        ok, lineas = correr(orden)
        paso(nombre, ok, "" if ok else "; ".join(lineas[-3:]))

    # sin huecos: entre el primer y el último período de cada serie están todos
    for s in rutas.series():
        p = rutas.PLATA / f"bcr_{s['clave']}.csv"
        if not p.exists():
            paso(f"{s['clave']}: está en plata", False)
            continue
        idx = sorted({indice(r["periodo"], s["frecuencia"]) for r in leer(s["clave"]) if r["valor"]})
        huecos = idx[-1] - idx[0] + 1 - len(idx)
        if huecos:
            paso(f"{s['clave']}: sin huecos", False, f"faltan {huecos} períodos entre el primero y el último")
    paso("series sin huecos de períodos", not any("sin huecos" in f for f in fallas))

    for serie, total, partes, que, *resto in IDENTIDADES:
        dec = resto[0] if resto else 2
        v = {}
        for r in leer(serie):
            if r["valor"]:
                v.setdefault(int(r["variable_id"]), {})[r["periodo"]] = float(r["valor"])
        tol = 0.5 * 10 ** -dec * (len(partes) + 2) + 1e-9
        vistos, malos, peor = 0, 0, (0, "")
        for per, t in v.get(total, {}).items():
            xs = [v.get(i, {}).get(per) for _, i in partes]
            if any(x is None for x in xs):
                continue
            vistos += 1
            d = t - sum(sg * x for (sg, _), x in zip(partes, xs))
            fijada = FIJADAS.get((serie, total, per))
            if fijada is not None:
                d -= fijada              # tiene que seguir siendo la diferencia publicada
            if abs(d) > tol:
                malos += 1
                peor = max(peor, (abs(d), per))
        paso(f"{serie}: {que}", vistos > 0 and malos == 0,
             f"{vistos} períodos" if not malos else f"{malos} de {vistos} períodos fuera de ±{tol:.3f}; el peor, {peor[1]}: {peor[0]:.2f}")

    sys.path.insert(0, str(rutas.RAIZ / "tuberias"))
    import calendario
    es = calendario.estado(calendario.hoy_sv())
    sin = [e["clave"] for e in es if not e["esperado"]]
    paso("calendario: cada serie tiene su próxima fecha esperada", not sin, ", ".join(sin))

    p = rutas.PLATA / "noticias.csv"
    if p.exists():
        import noticias
        with open(p, encoding="utf-8", newline="") as fh:
            notas = list(csv.DictReader(fh))
        mal_cat = [r for r in notas if r["categoria"] not in CATEGORIAS]
        largas = [r for r in notas if len(r["resumen"]) > noticias.LARGO_RESUMEN]
        sv = [r for r in notas if r["categoria"].startswith("Internacional") and noticias.menciona_sv(r["titular"] + " " + r["resumen"])]
        paso("noticias: categorías, largo del extracto y El Salvador fuera de lo internacional",
             not (mal_cat or largas or sv),
             f"{len(notas)} notas" if not (mal_cat or largas or sv)
             else f"{len(mal_cat)} sin categoría válida, {len(largas)} extractos largos, {len(sv)} salvadoreñas en internacional")
        vetadas = sorted({r["fuente"] for r in notas if noticias.fuera(r["fuente"])})
        lugares = {}
        for r in notas:
            lugares.setdefault((r["edicion"], r["categoria"]), []).append(int(r.get("orden") or 0))
        mal_orden = [f"{ed} {cat}" for (ed, cat), ls in lugares.items() if sorted(ls) != list(range(1, len(ls) + 1))]
        paso("noticias: ningún medio de los que no entran, y cada subsección numerada de 1 en adelante",
             not (vetadas or mal_orden),
             f"{len(lugares)} subsecciones" if not (vetadas or mal_orden)
             else "; ".join(filter(None, [", ".join(vetadas), "orden roto en " + ", ".join(mal_orden[:4]) if mal_orden else ""])))

    print(f"\n{n - len(fallas)} de {n} revisiones pasan" + ("" if not fallas else "; fallan: " + "; ".join(fallas)))
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
