"""Dónde vive cada cosa del repositorio. Todo script pregunta aquí; nadie arma una ruta a mano."""
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = RAIZ / "catalogo"
LAGO = RAIZ / "lago"
BRONCE = LAGO / "bronce"
PLATA = LAGO / "plata"
ORO = LAGO / "oro"
SITIO = RAIZ / "sitio"

BRONCE_BCR = BRONCE / "bcr"
LOCK_BCR = BRONCE_BCR / "fuentes.lock.json"
BRONCE_CALENDARIO = BRONCE / "calendario_bcr.json"
BRONCE_NOTICIAS = BRONCE / "noticias"


def catalogo(nombre):
    """Un archivo de catalogo/ ya leído: «series», «indicadores», «calendario», «noticias_fuentes»."""
    with open(CATALOGO / f"{nombre}.toml", "rb") as fh:
        return tomllib.load(fh)


def series():
    return catalogo("series")["serie"]


def serie(clave):
    for s in series():
        if s["clave"] == clave:
            return s
    raise SystemExit(f"catalogo/series.toml no tiene la serie «{clave}»")


def rel(p):
    return Path(p).resolve().relative_to(RAIZ).as_posix()
