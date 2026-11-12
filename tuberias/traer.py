#!/usr/bin/env python3
"""Trae las fuentes a lago/bronce/, tal como las sirve quien las publica.

    python tuberias/traer.py bcr                      todas las series de catalogo/series.toml
    python tuberias/traer.py bcr --solo reservas,ipc  algunas
    python tuberias/traer.py bcr --seco               las pide y las contrasta, sin escribir
    python tuberias/traer.py calendario               el calendario de divulgación del BCR
    python tuberias/traer.py noticias                 los feeds de catalogo/noticias_fuentes.toml
    python tuberias/traer.py verificar                sin red: cada archivo de bronce contra su sha256

Una serie se escribe solo si pasa sus contrastes (bcr.interpretar): las dos caras que entrega el
servidor dicen lo mismo y la vista inicial de la página está contenida en lo pedido. Una que falla no
se escribe y se nombra; el proceso termina con error para que el workflow no publique a medias.
lago/bronce/bcr/fuentes.lock.json fija cada archivo con su sha256, su último período y el día en que
cambió por última vez.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bcr  # noqa: E402
import rutas  # noqa: E402


TRAMO = {"M": 4, "T": 10, "A": 0}     # años por pedido, según la frecuencia; 0 es todo de una vez


def sha(b):
    return hashlib.sha256(b).hexdigest()


def leer_lock():
    if rutas.LOCK_BCR.exists():
        return json.loads(rutas.LOCK_BCR.read_text(encoding="utf-8"))
    return {"generado_por": "tuberias/traer.py", "series": {}}


def escribir_lock(lock):
    lock["series"] = dict(sorted(lock["series"].items()))
    rutas.LOCK_BCR.write_text(json.dumps(lock, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def traer_bcr(args):
    pedidas = [s for s in rutas.series() if not args.solo or s["clave"] in args.solo]
    faltan = set(args.solo or []) - {s["clave"] for s in pedidas}
    if faltan:
        raise SystemExit(f"no hay serie {sorted(faltan)} en catalogo/series.toml")
    rutas.BRONCE_BCR.mkdir(parents=True, exist_ok=True)
    lock, hoy, fallas, cambios = leer_lock(), dt.date.today().isoformat(), [], []
    for s in pedidas:
        clave = s["clave"]
        b, res, error = None, None, None
        # el servidor responde 500 a algunos rangos largos: se pide por tramos de años, y si un
        # tramo falla se reintenta una vez con tramos de la mitad
        tramo = s.get("tramo", TRAMO[s["frecuencia"]])
        for intento in (tramo, max(1, tramo // 2) if tramo else 5):
            try:
                b = bcr.leer(s["slug"], tramo=intento)
                _, res = bcr.interpretar(b, s["frecuencia"])
                error = None
                break
            except (bcr.ErrorPortal, KeyError, ValueError, IndexError) as e:
                error = e
                if "HTTP 5" not in str(e):
                    break
        if error is not None:
            fallas.append(clave)
            print(f"  NO SE ESCRIBE {clave}: {error}")
            continue
        texto = (bcr.volcar(b) + "\n").encode("utf-8")
        destino = rutas.BRONCE_BCR / f"{clave}.json"
        igual = destino.exists() and destino.read_bytes() == texto
        previo = lock["series"].get(clave, {})
        print(f"  {clave}: {res['modo']}, {res['variables']} variables, {res['desde']} a {res['hasta']}, "
              f"{res['observaciones']} cifras, testigo {res['testigo']}"
              f"{', ambiguos ' + str(res['ambiguos']) if res['ambiguos'] else ''}; {'igual' if igual else 'cambia'}")
        if args.seco:
            continue
        if not igual:
            destino.write_bytes(texto)
            cambios.append(clave)
        lock["series"][clave] = {
            "url": b["url"], "archivo": destino.name, "sha256": sha(texto), "bytes": len(texto),
            "modo": res["modo"], "variables": res["variables"], "periodos": res["periodos"],
            "observaciones": res["observaciones"], "desde": res["desde"], "hasta": res["hasta"],
            "tomado": previo.get("tomado", hoy) if igual else hoy}
    if not args.seco:
        escribir_lock(lock)
    print(f"{len(pedidas) - len(fallas)} de {len(pedidas)} series"
          f"{'; cambiaron: ' + ', '.join(cambios) if cambios else ''}"
          f"{'; sin escribir: ' + ', '.join(fallas) if fallas else ''}")
    return 1 if fallas else 0


def verificar(_args):
    lock, malos = leer_lock(), 0
    for clave, s in lock["series"].items():
        p = rutas.BRONCE_BCR / s["archivo"]
        if not p.exists():
            print("  FALTA", s["archivo"])
            malos += 1
        elif sha(p.read_bytes()) != s["sha256"]:
            print("  CAMBIÓ", s["archivo"])
            malos += 1
    sueltos = {p.name for p in rutas.BRONCE_BCR.glob("*.json")} - {s["archivo"] for s in lock["series"].values()} \
        - {rutas.LOCK_BCR.name}
    for x in sorted(sueltos):
        print("  SIN FIJAR", x)
    print(f"verificar: {len(lock['series'])} series del BCR, {malos + len(sueltos)} con problemas")
    return 1 if malos or sueltos else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="que", required=True)
    b = sub.add_parser("bcr")
    b.add_argument("--solo", type=lambda x: [y for y in x.split(",") if y])
    b.add_argument("--seco", action="store_true")
    sub.add_parser("calendario")
    n = sub.add_parser("noticias")
    n.add_argument("--seco", action="store_true")
    sub.add_parser("verificar")
    args = ap.parse_args()
    if args.que == "bcr":
        sys.exit(traer_bcr(args))
    if args.que == "verificar":
        sys.exit(verificar(args))
    if args.que == "calendario":
        import calendario
        sys.exit(calendario.sincronizar())
    if args.que == "noticias":
        import noticias
        sys.exit(noticias.traer(seco=args.seco))


if __name__ == "__main__":
    main()
