#!/usr/bin/env python3
"""El resumen de noticias de cada mañana, en cinco categorías.

    python tuberias/noticias.py                       trae los feeds y actualiza el lago
    python tuberias/noticias.py --seco                los trae y muestra el reparto, sin escribir
    python tuberias/noticias.py --sin-red             no lee ningún feed: vuelve a pasar la base por el catálogo
                                                      (después de cambiar una lista, un peso o un tema)
    python tuberias/noticias.py excel                 escribe el Excel de la última edición
    python tuberias/noticias.py excel --edicion 2026-11-12 --destino resumen.xlsx

Las fuentes y las palabras están en catalogo/noticias_fuentes.toml. De cada nota se guarda solo lo que
su medio publica en su feed —titular, extracto, fecha y enlace—, nunca el texto completo.

  lago/plata/noticias.csv            todas las notas de los últimos `conservar_dias`, una por fila
  lago/oro/noticias/AAAA-MM-DD.csv   la edición de cada día: lo publicado de las 7:00 del día anterior
                                     a las 7:00 de ese día (hora de El Salvador), ordenado por categoría

Tres columnas dicen la prioridad de cada nota, y se recalculan enteras en cada corrida (dependen del
catálogo, de las otras notas de su edición y del calendario del BCR, no de cuándo entró la nota):

  puntaje   cuánto merece estar entre las elegidas de su subsección (palabras, peso del medio, dato del
            BCR recién publicado); 0 o menos si repite una historia que ya trae un medio de más peso
  tema      en las dos subsecciones nacionales, su tema («Deuda pública», «Sector externo»…)
  orden     su lugar en la subsección: 1 es la primera. El sitio y la hoja de Google ordenan por aquí

Una noticia es contexto, nunca la fuente de una cifra.
"""
import argparse
import csv
import datetime as dt
import email.utils
import hashlib
import html
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rutas  # noqa: E402

SV = ZoneInfo("America/El_Salvador")
CATEGORIAS = ["Internacional – EUA", "Internacional – LATAM", "Internacional – Resto del mundo",
              "El Salvador – Nacionales", "El Salvador – Fiscales"]
NACIONALES = ("El Salvador – Nacionales", "El Salvador – Fiscales")
# Las columnas son un contrato con quien lee el lago desde fuera: las nuevas van al final.
COLUMNAS = ["id", "edicion", "fecha_hora", "categoria", "fuente", "titular", "resumen", "url", "idioma", "puntaje",
            "tema", "orden"]
COL_EDICION = ["fecha_hora", "categoria", "fuente", "titular", "resumen", "url", "puntaje", "tema", "orden"]
VIA_GOOGLE = " (vía Google News)"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

_CFG = None


def cfg():
    global _CFG
    if _CFG is None:
        _CFG = rutas.catalogo("noticias_fuentes")
    return _CFG


LARGO_RESUMEN = 300


# ------------------------------------------------------------------ palabras
def plano(x):
    x = unicodedata.normalize("NFD", (x or "").lower())
    return "".join(c for c in x if unicodedata.category(c) != "Mn")


_REGEX = {}


CIFRA = r"\$\s?\d[\d.,]*|\d[\d.,]*\s(?:mil\s|millones\sde\s)?dolares"     # «$cifra»: un monto en dólares


def _patron(terminos):
    """La expresión que encuentra cualquiera de los términos, por palabra entera. Un * vale por el resto
    de la palabra, también en medio del término: «obra* publica*» encuentra «obras públicas»."""
    partes = [r"\w*".join(re.escape(x) for x in t.split("*")) for t in map(plano, terminos) if t != "$cifra"]
    patron = r"(?<![\w])(?:" + "|".join(partes) + r")(?![\w])"
    return re.compile(patron + "|" + CIFRA if "$cifra" in terminos else patron)


def _regex(lista):
    if lista not in _REGEX:
        _REGEX[lista] = _patron(cfg()["palabras"][lista])
    return _REGEX[lista]


def cuenta(lista, texto):
    return len(_regex(lista).findall(plano(texto)))


def cumple(exige, texto):
    """¿La nota trae lo que se le exige? `exige` nombra una lista de [palabras] (trae alguna) o una de
    las [reglas] (cumple alguna de sus vías, y una vía, con palabras de todas sus listas); si son
    varios nombres, todos."""
    if not isinstance(exige, str):
        return all(cumple(e, texto) for e in exige)
    vias = cfg().get("reglas", {}).get(exige)
    if vias is None:
        return cuenta(exige, texto) > 0
    return any(all(cuenta(lista, texto) for lista in via) for via in vias)


def menciona_sv(texto):
    return cuenta("el_salvador", texto) > 0


def sin_figuras(texto):
    """El texto, ya sin mayúsculas ni tildes, y sin los giros en que una palabra fiscal no lo es («una
    deuda con la justicia», «déficit de lluvias»)."""
    return _regex("figurado").sub(" ", plano(texto))


# ------------------------------------------------------------------ medios
def medio_de(fuente):
    """El medio que publica, llegue por su feed o por Google News."""
    return fuente[:-len(VIA_GOOGLE)] if fuente.endswith(VIA_GOOGLE) else fuente


def fuera(fuente):
    """¿Es un medio de los que no entran ([medios] fuera)?"""
    if "·fuera" not in _REGEX:
        _REGEX["·fuera"] = _patron(cfg()["medios"]["fuera"])
    return bool(_REGEX["·fuera"].search(plano(fuente)))


def peso_de(fuente, categoria):
    """Lo que pesa un medio en lo nacional o en lo internacional; 0 es «otra fuente»."""
    return cfg()["pesos"]["nacional" if categoria in NACIONALES else "internacional"].get(medio_de(fuente), 0)


def cripto_ajena(texto):
    """Una nota de una criptomoneda que no interesa: nombra otra y no al bitcoin, una moneda estable o
    una casa de cambio."""
    return cuenta("cripto_otras", texto) > 0 and cuenta("cripto_si", texto) == 0


# ------------------------------------------------------------------ categoría, puntaje y tema
def _de_aqui(texto, titular):
    """En un medio salvadoreño, ¿la nota es del país? Lo es si no nombra otra región, o si la nombra pero
    habla de algo de aquí (la cooperación alemana, el MOP, una alcaldía), o si es de combustibles o de
    petróleo y eso manda en el titular: es lo primero de «Fiscales»."""
    if cuenta("ancla_sv", texto) or not any(cuenta(r, texto) for r in ("eua", "latam", "resto")):
        return True
    c = cuenta("combustibles", titular)
    return c > 0 and c >= max(cuenta(r, titular) for r in ("eua", "latam", "resto"))


def es_fiscal(texto, titular):
    """¿Una nota salvadoreña es «Fiscales»? La regla `fiscales`, y manda el titular: si solo se cumple
    contando el extracto, no basta una única palabra de la lista `fiscal` («…ingresos tributarios»)."""
    if cumple("fiscales", titular):
        return True
    otras = [v for v in cfg()["reglas"]["fiscales"] if v != ["fiscal"]]
    return any(all(cuenta(lista, texto) for lista in v) for v in otras) or cuenta("fiscal", texto) >= 2


def clasificar(texto, defecto, titular=None):
    """La categoría de una nota por sus palabras; `defecto` es la de su fuente."""
    texto, titular = sin_figuras(texto), sin_figuras(texto if titular is None else titular)
    if menciona_sv(texto) or (defecto.startswith("El Salvador") and _de_aqui(texto, titular)):
        # «Fiscales» lo dicen las palabras de la nota, no la sección de donde vino
        return "El Salvador – Fiscales" if es_fiscal(texto, titular) else "El Salvador – Nacionales"
    if cumple("precio_btc", titular):
        return "El Salvador – Nacionales"       # el precio del bitcoin va en lo nacional, venga de donde venga
    n = {"Internacional – EUA": cuenta("eua", texto), "Internacional – LATAM": cuenta("latam", texto),
         "Internacional – Resto del mundo": cuenta("resto", texto)}
    mejor = max(n.values())
    if mejor == 0:
        return defecto if defecto.startswith("Internacional") else "Internacional – Resto del mundo"
    ganan = [c for c, v in n.items() if v == mejor]
    return defecto if defecto in ganan else ganan[0]


def puntaje(n, publicado=None):
    """Cuánto merece una nota estar entre las elegidas de su subsección: 2 por cada palabra preferida de
    su categoría en el titular y 1 en el extracto, menos 3 por cada palabra de las que se evitan. En
    Fiscales, las palabras de inversión pública suman aparte: 3 y 1. Una nota nacional que recoge un dato
    que el BCR acaba de publicar (`publicado`, de `publicaciones()`) suma el bono. Si con eso queda en
    positivo, suma el peso de su medio. No compara categorías entre sí."""
    g = cfg().get("gusto", {}).get(n["categoria"])
    if not g:
        return 0
    titular, resumen = sin_figuras(n["titular"]), sin_figuras(n["resumen"])
    p = 2 * cuenta(g["prefiere"], titular) + cuenta(g["prefiere"], resumen)
    if n["categoria"] == "El Salvador – Fiscales":
        # un proyecto de inversión pública (quién lo financia, quién lo ejecuta) es lo que más se busca
        p += 3 * cuenta("inversion_publica", titular) + cuenta("inversion_publica", resumen)
    p -= 3 * cuenta(g["evita"], n["titular"] + " " + n["resumen"])
    if plano(n["titular"]).lstrip("«\"'“ ").startswith(tuple(plano(x) for x in cfg()["gusto_listas"]["titular_de_servicio"])):
        p -= 3
    if publicado and n["categoria"] in NACIONALES and dato_reciente(n, publicado):
        p += cfg()["general"]["bono_dato_bcr"]
    # el peso del medio ordena entre notas que ya dicen algo: no rescata a la que no trae nada
    return p + peso_de(n["fuente"], n["categoria"]) if p > 0 else p


def publicaciones(filas=None):
    """{serie: fechas} de lo que el BCR anunció en su calendario (lago/plata/calendario.csv)."""
    if filas is None:
        p = rutas.PLATA / "calendario.csv"
        if not p.exists():
            return {}
        with open(p, encoding="utf-8", newline="") as fh:
            filas = list(csv.DictReader(fh))
    out = {}
    for r in filas:
        if r["origen"] == "bcr":
            out.setdefault(r["serie"], set()).add(dt.date.fromisoformat(r["fecha_esperada"]))
    return out


def dato_reciente(n, publicado):
    """¿La nota recoge una serie que el BCR publicó en los días previos a su edición?"""
    dia = dt.date.fromisoformat(n["edicion"])
    desde = dia - dt.timedelta(days=cfg()["general"]["dias_dato_bcr"])
    texto = plano(n["titular"] + " " + n["resumen"])
    for i, d in enumerate(cfg().get("dato_bcr", [])):
        if any(desde <= f <= dia for s in d["series"] for f in publicado.get(s, ())):
            if f"·dato{i}" not in _REGEX:
                _REGEX[f"·dato{i}"] = _patron(d["palabras"])
            if _REGEX[f"·dato{i}"].search(texto):
                return True
    return False


_TEMAS = {}


def temas_de(categoria):
    if categoria not in _TEMAS:
        _TEMAS[categoria] = [t for t in cfg().get("tema", []) if t["categoria"] == categoria]
    return _TEMAS[categoria]


def tema(n):
    """(lugar, nombre) del tema de una nota en su subsección; (0, "") si su categoría no tiene temas.
    Gana el tema con más palabras suyas en la nota (el titular vale doble); si empatan, el que va
    antes; sin ninguna, el tema `resto`. Un tema con `regla` se queda la nota si el titular la cumple."""
    ts = temas_de(n["categoria"])
    if not ts:
        return 0, ""
    titular, resumen = sin_figuras(n["titular"]), sin_figuras(n["resumen"])
    mejor, puntos = None, 0
    for i, t in enumerate(ts):
        if t.get("regla") and cumple(t["regla"], titular):
            return i, t["nombre"]
        if t.get("palabras"):
            p = 2 * cuenta(t["palabras"], titular) + cuenta(t["palabras"], resumen)
            if p > puntos:
                mejor, puntos = i, p
    if mejor is None:
        mejor = next(i for i, t in enumerate(ts) if t.get("resto"))
    return mejor, ts[mejor]["nombre"]


# ------------------------------------------------------------------ una historia, una nota
VACIAS = frozenset("""que con por los las del una uno unos unas sus son fue han hay mas muy sin ser the and
    para como tras entre sobre desde hasta este esta estos estas pero porque segun ante mientras donde
    cuando tiene tienen sera seran sido estan esto menos nuevo nueva nuevos nuevas ano anos dice dijo
    salvador""".split())


def fichas(titular):
    """Lo que dice de qué trata un titular: sus palabras de tres letras o más, recortadas a cinco para que
    «aporte» y «aportar» sean la misma, y sus cifras."""
    return frozenset(w if w[0].isdigit() else w[:5]
                     for w in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", plano(titular))
                     if (len(w) >= 3 or w[0].isdigit()) and w not in VACIAS)


def misma_historia(a, b):
    """Dos juegos de fichas son la misma historia si comparten al menos tres y la parte `misma_historia`
    de las del titular más corto."""
    comunes = len(a & b)
    return comunes >= 3 and comunes >= cfg()["general"]["misma_historia"] * min(len(a), len(b))


def priorizar(notas, publicado=None):
    """Pone en cada nota su `puntaje`, su `tema` y su `orden` dentro de (edición, categoría).

    Principales son las notas que traen algo de lo que se busca (puntaje sobre 0) y cuentan una historia
    por primera vez —de varias con la misma, la del medio que más pesa—, sin pasar de
    `otras_por_subseccion` notas de medios sin peso en cada subsección ni del `maximo` de su tema. Van primero, por tema y dentro del tema por puntaje; la segunda
    de un tema pierde `paso_mismo_tema` puntos y la tercera el doble, para que las de más puntaje cubran
    todos los temas. Las demás bajan al final con puntaje 0 o menos, y nadie las elige sin mirarlas:
    en cada subsección, las de puntaje sobre 0 son las principales y van juntas arriba."""
    g_ = cfg()["general"]
    ambitos, grupos = {}, {}
    for n in notas:
        n["puntaje"] = puntaje(n, publicado)
        n["_tema"], n["tema"] = tema(n)
        ambitos.setdefault((n["edicion"], n["categoria"] in NACIONALES), []).append(n)
        grupos.setdefault((n["edicion"], n["categoria"]), []).append(n)
    reciente = lambda n: [-ord(c) for c in n["fecha_hora"]]
    bajan = {n["id"] for n in notas if n["puntaje"] <= 0}        # la que no trae nada de lo que se busca
    for g in ambitos.values():          # la misma historia en otro medio, esté en la subsección que esté
        cabezas = []
        for n in sorted(g, key=lambda n: (n["id"] in bajan, -peso_de(n["fuente"], n["categoria"]), -n["puntaje"],
                                          reciente(n), n["id"])):
            f = fichas(n["titular"])
            if n["id"] in bajan:
                continue
            if any(misma_historia(f, c) for c in cabezas):
                bajan.add(n["id"])
            else:
                cabezas.append(f)
    for (_, categoria), g in grupos.items():
        mejores = sorted((n for n in g if n["id"] not in bajan), key=lambda n: (-n["puntaje"], reciente(n), n["id"]))
        otras = [n for n in mejores if peso_de(n["fuente"], categoria) == 0]      # de otras fuentes, solo unas pocas
        bajan.update(n["id"] for n in otras[g_["otras_por_subseccion"]:])
        for i, t in enumerate(temas_de(categoria)):
            suyas = [n for n in mejores if n["_tema"] == i and n["id"] not in bajan]
            if t.get("maximo"):                                  # de un tema, no más de su máximo
                bajan.update(n["id"] for n in suyas[t["maximo"]:])
                suyas = suyas[:t["maximo"]]
            for k, n in enumerate(suyas):                        # y cada nota más del mismo tema vale menos
                n["_puesto"] = k
        clave = lambda n: (n["id"] in bajan, n["_tema"], n.get("_puesto", 0), -n["puntaje"], reciente(n), n["id"])
        for lugar, n in enumerate(sorted(g, key=clave), 1):
            n["orden"] = lugar
        for n in g:
            if n["id"] in bajan:
                n["puntaje"] = min(n["puntaje"], 0)
            elif n["puntaje"] > 0:                               # nunca por debajo de 1: sigue siendo principal
                n["puntaje"] = max(n["puntaje"] - g_["paso_mismo_tema"] * n.get("_puesto", 0), 1)
    for n in notas:
        n.pop("_puesto", None)
        del n["_tema"]
    return notas


# ------------------------------------------------------------------ texto
def sin_html(x):
    x = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", x or "", flags=re.I)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", html.unescape(html.unescape(x)).replace("\xa0", " ")).strip()


def extracto(x, titular=""):
    x = sin_html(x)
    x = re.sub(r"\s*(La entrada|The post) .{0,200}(se publicó primero en|appeared first on).*$", "", x)
    x = re.sub(r"\s*\[(?:…|\.\.\.|&hellip;)\]\s*$", "…", x)
    if plano(x) == plano(titular):
        return ""
    if len(x) <= LARGO_RESUMEN:
        return x
    corte = x[:LARGO_RESUMEN - 1]
    corte = corte[:corte.rfind(" ")] if " " in corte[-40:] else corte
    return corte.rstrip(" ,;:.") + "…"


def url_limpia(u):
    p = urllib.parse.urlsplit((u or "").strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))


def fecha_de(x):
    """Una fecha de feed (RFC 822 o ISO 8601) → datetime con zona; None si no se entiende."""
    x = (x or "").strip()
    if not x:
        return None
    try:
        d = email.utils.parsedate_to_datetime(x)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def edicion_de(momento):
    """El día de la edición a la que pertenece una nota publicada en `momento` (hora de El Salvador)."""
    corte = cfg()["general"]["hora_de_corte"]
    return (momento.date() + dt.timedelta(days=1 if momento.hour >= corte else 0)).isoformat()


# ------------------------------------------------------------------ red
class Red:
    def __init__(self):
        import requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = cfg()["general"]["agente"]
        self.pausa, self.ultimo = cfg()["general"]["pausa"], 0.0

    def get(self, url):
        import requests
        for intento in range(2):
            # Google News corta con 503 a quien pide seguido: sus búsquedas van más espaciadas
            pausa = self.pausa * (5 if "news.google.com" in url else 1) * (intento + 1)
            espera = pausa - (time.monotonic() - self.ultimo)
            if espera > 0:
                time.sleep(espera)
            self.ultimo = time.monotonic()
            try:
                r = self.s.get(url, timeout=40)
                if r.status_code == 200:
                    return r
                falla = f"HTTP {r.status_code}"
                if r.status_code < 500 and r.status_code != 429:
                    break
            except requests.RequestException as e:
                falla = type(e).__name__
        raise IOError(falla)


def _txt(nodo, *nombres):
    for n in nombres:
        x = nodo.find(n)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""


def leer_rss(f, red):
    """Notas crudas de un feed RSS 2.0, RSS 1.0 (RDF) o Atom."""
    raiz = ET.fromstring(red.get(f["url"]).content)
    items = raiz.findall(".//item") or raiz.findall(f".//{RSS1}item") or raiz.findall(f".//{ATOM}entry")
    for it in items:
        enlace = _txt(it, "link", f"{RSS1}link")
        if not enlace:
            for l in it.findall(f"{ATOM}link"):
                if l.get("rel", "alternate") == "alternate":
                    enlace = l.get("href", "")
        fuente = it.find("source")
        yield {"titular": sin_html(_txt(it, "title", f"{RSS1}title", f"{ATOM}title")),
               "url": enlace,
               "fecha": fecha_de(_txt(it, "pubDate", f"{DC}date", f"{ATOM}published", f"{ATOM}updated")),
               "resumen": _txt(it, "description", f"{RSS1}description", f"{ATOM}summary", f"{CONTENT}encoded"),
               "medio": (fuente.text or "").strip() if fuente is not None else ""}


def leer_wp(f, red, desde):
    base = f["url"].rstrip("/") + "/wp-json/wp/v2"
    q = {"per_page": 50, "orderby": "date", "order": "desc", "after": desde.strftime("%Y-%m-%dT%H:%M:%S"),
         "_fields": "id,date_gmt,link,title,excerpt"}
    if f.get("secciones"):
        r = red.get(f"{base}/categories?" + urllib.parse.urlencode(
            {"slug": ",".join(f["secciones"]), "_fields": "id,slug", "per_page": 100}))
        ids = [str(c["id"]) for c in r.json()]
        if len(ids) != len(f["secciones"]):
            raise IOError(f"el sitio ya no tiene las secciones {f['secciones']}")
        q["categories"] = ",".join(ids)
    r = red.get(f"{base}/posts?" + urllib.parse.urlencode(q))
    if "json" not in (r.headers.get("Content-Type") or ""):
        raise IOError("la API no respondió JSON")
    for it in r.json():
        yield {"titular": sin_html(it["title"]["rendered"]), "url": it["link"],
               "fecha": fecha_de(it["date_gmt"] + "+00:00"), "resumen": it.get("excerpt", {}).get("rendered", ""),
               "medio": ""}


def fecha_elmundo(x):
    """«jueves 12, noviembre 2026 - 5:47 p. m.» → datetime en hora de El Salvador; None si no se entiende."""
    m = re.search(r"(\d{1,2}),\s*([a-záéíóú]+)\s+(\d{4})\s*-\s*(\d{1,2}):(\d{2})\s*([ap])", plano(x))
    if not m or m.group(2) not in MESES:
        return None
    hora = int(m.group(4)) % 12 + (12 if m.group(6) == "p" else 0)
    return dt.datetime(int(m.group(3)), MESES.index(m.group(2)) + 1, int(m.group(1)), hora, int(m.group(5)), tzinfo=SV)


def portada_elmundo(pagina):
    """Las notas que lista una sección de diario.elmundo.sv: (url, titular, fecha)."""
    out = []
    for art in re.findall(r"<article[\s\S]*?</article>", pagina):
        m = re.search(r'class="article-title">\s*<a\s+href="([^"]+)"\s+title="([^"]*)"', art)
        d = re.search(r'class="article-date">\s*([^<]+?)\s*<', art)
        if m:
            out.append((m.group(1), sin_html(m.group(2)), fecha_elmundo(d.group(1)) if d else None))
    return out


def meta(pagina, nombre):
    """El contenido de una etiqueta <meta> de la cabecera de una página."""
    m = (re.search(r'<meta[^>]+(?:property|name)="' + re.escape(nombre) + r'"[^>]+content="([^"]*)"', pagina)
         or re.search(r'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="' + re.escape(nombre) + '"', pagina))
    return html.unescape(m.group(1)).strip() if m else ""


def leer_elmundo(f, red, desde, conocidas):
    """Diario El Mundo no tiene feed: se lee la portada de la sección (título, fecha y enlace) y, de
    cada nota que el lago no tiene, su página, solo por el extracto y la fecha que el propio medio
    publica en sus etiquetas <meta>. El texto de la nota no se lee ni se guarda."""
    for pag in range(1, f.get("paginas", 2) + 1):
        lista = portada_elmundo(red.get(f["url"] + (f"?page={pag}" if pag > 1 else "")).text)
        if not lista:
            if pag == 1:
                raise IOError("la portada no lista notas: cambió su forma")
            return
        for url, titular, fecha in lista:
            if fecha is None or fecha < desde:
                continue
            if hashlib.sha1(url_limpia(url).encode("utf-8")).hexdigest()[:12] in conocidas:
                continue
            nota = red.get(url).text
            yield {"titular": titular, "url": url, "fecha": fecha_de(meta(nota, "article:published_time")) or fecha,
                   "resumen": meta(nota, "og:description") or meta(nota, "description"), "medio": ""}
        if all(fecha is not None and fecha < desde for _, _, fecha in lista):
            return


def notas_de(f, red, ahora, conocidas=frozenset()):
    """Las notas de una fuente dentro de la ventana, ya limpias y clasificadas. `conocidas` son los id
    que el lago ya tiene: sirve para no volver a pedir la página de una nota ya guardada."""
    desde = ahora - dt.timedelta(days=cfg()["general"]["dias"])
    if f["metodo"] == "wp_api":
        crudas = leer_wp(f, red, desde.astimezone(dt.timezone.utc))
    elif f["metodo"] == "elmundo":
        crudas = leer_elmundo(f, red, desde, conocidas)
    else:
        crudas = leer_rss(f, red)
    out = []
    for c in crudas:
        if not c["titular"] or not c["url"] or c["fecha"] is None:
            continue
        momento = c["fecha"].astimezone(SV)
        if momento < desde or momento > ahora + dt.timedelta(hours=1):
            continue
        titular, fuente, resumen = c["titular"], f["nombre"], extracto(c["resumen"], c["titular"])
        if f["metodo"] == "gnews":
            # Google News escribe «Titular - Medio» y no da extracto propio del medio
            medio = c["medio"] or titular.rpartition(" - ")[2]
            if medio and titular.endswith(" - " + medio):
                titular = titular[:-len(medio) - 3].strip()
            fuente, resumen = f.get("medio") or (medio + VIA_GOOGLE if medio else "Google News"), ""
        texto = titular + " " + resumen
        if fuera(fuente) or cripto_ajena(texto):
            continue
        if f.get("filtro") and not cuenta("economia", texto):
            continue
        if f.get("exige") and not cumple(f["exige"], texto):
            continue
        url = c["url"] if f["metodo"] == "gnews" else url_limpia(c["url"])
        out.append({"id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:12], "edicion": edicion_de(momento),
                    "fecha_hora": momento.strftime("%Y-%m-%dT%H:%M"), "categoria": clasificar(texto, f["categoria"], titular),
                    "fuente": fuente, "titular": titular, "resumen": resumen, "url": url,
                    "idioma": f.get("idioma", "es")})
        if len(out) >= f.get("maximo", 200):
            break
    return out


# ------------------------------------------------------------------ el lago
def leer_plata():
    p = rutas.PLATA / "noticias.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _salio_de(n, f):
    """¿Esta nota guardada salió de esa fuente? Se sabe por su dirección, donde va la sección del diario."""
    if f["metodo"] == "elmundo":
        return n["url"].startswith(f["url"].rstrip("/") + "/")
    if f["metodo"] == "wp_api":
        return n["url"].startswith(f["url"]) and any(f"/{s}/" in n["url"] for s in f.get("secciones", []))
    return False


def al_dia(notas):
    """La base, puesta al día con el catálogo de hoy: se va la nota de un medio que ya no entra, la de
    una criptomoneda que no interesa y la que su sección ya no admitiría (su `exige`), y cada una vuelve
    a repartirse en su categoría. Así una regla que se afina vale también para lo ya guardado, igual que
    el puntaje. De una nota cuya fuente no se reconoce por la dirección, la categoría que tiene hace de
    categoría de la fuente: sin cambios en las listas, queda donde estaba."""
    con_seccion = [f for f in cfg()["fuente"] if f["metodo"] in ("elmundo", "wp_api")]
    out = []
    for n in notas:
        texto = n["titular"] + " " + n["resumen"]
        if fuera(n["fuente"]) or cripto_ajena(texto):
            continue
        f = next((f for f in con_seccion if _salio_de(n, f)), None)
        if f and f.get("exige") and not cumple(f["exige"], texto):
            continue
        n["categoria"] = clasificar(texto, f["categoria"] if f else n["categoria"], n["titular"])
        out.append(n)
    return out


def clave_titular(n):
    return re.sub(r"[^a-z0-9]+", "", plano(n["titular"]))[:90]


def orden_edicion(n):
    """Dentro de una edición: por categoría y, en cada una, por su `orden` (una base anterior a esa
    columna se ordena por puntaje)."""
    return (CATEGORIAS.index(n["categoria"]), int(n.get("orden") or 10 ** 6), -int(n.get("puntaje") or 0),
            [-ord(c) for c in n["fecha_hora"]])


def orden(n):
    return (n["edicion"],) + orden_edicion(n) + (n["id"],)


def texto_csv(cols, filas):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(filas)
    return buf.getvalue()


def escribir_ediciones(notas, ahora):
    """lago/oro/noticias/<día>.csv de cada edición ya cerrada; las viejas se retiran."""
    carpeta = rutas.ORO / "noticias"
    carpeta.mkdir(parents=True, exist_ok=True)
    cerrada = edicion_de(ahora - dt.timedelta(days=1))          # la última cuyo corte ya pasó
    por = {}
    for n in notas:
        if n["edicion"] <= cerrada:
            por.setdefault(n["edicion"], []).append(n)
    for ed, filas in por.items():
        filas.sort(key=orden_edicion)
        texto = texto_csv(COL_EDICION, filas)
        p = carpeta / f"{ed}.csv"
        if not p.exists() or p.read_text(encoding="utf-8") != texto:
            p.write_text(texto, encoding="utf-8", newline="")
    for p in carpeta.glob("*.csv"):
        if p.stem not in por:
            p.unlink()
    return cerrada, por


def traer(seco=False, ahora=None, sin_red=False):
    global LARGO_RESUMEN
    LARGO_RESUMEN = cfg()["general"]["largo_resumen"]
    ahora = ahora or dt.datetime.now(SV)
    limite = (ahora.date() - dt.timedelta(days=cfg()["general"]["conservar_dias"])).isoformat()
    previas = al_dia([n for n in leer_plata() if n["edicion"] >= limite])
    red, nuevas, estado = None if sin_red else Red(), [], []
    for f in [] if sin_red else cfg()["fuente"]:
        try:
            ns = notas_de(f, red, ahora, frozenset(n["id"] for n in previas))
            nuevas += ns
            estado.append((f["clave"], len(ns), ""))
        except (IOError, ET.ParseError, KeyError, ValueError) as e:
            estado.append((f["clave"], 0, f"{'opcional, ' if f.get('opcional') else ''}no respondió: {e}"))
    for clave, n, falla in estado:
        print(f"  {clave:<20} {n:>4} notas{'  — ' + falla if falla else ''}")
    if not nuevas and not sin_red:
        print("noticias: ninguna fuente entregó notas")
        return 1
    ids = {n["id"] for n in previas}
    titulares = {(n["edicion"], clave_titular(n)) for n in previas}
    agregadas = []
    for n in nuevas:                                   # el orden del catálogo decide cuál queda de dos iguales
        k = clave_titular(n)
        if n["id"] in ids or any((e, k) in titulares for e in _vecinas(n["edicion"])):
            continue
        ids.add(n["id"])
        titulares.add((n["edicion"], k))
        agregadas.append(n)
    todas = priorizar(previas + agregadas, publicaciones())      # puntaje, tema y orden, de nuevo para todas
    todas.sort(key=orden)
    por_cat = {c: sum(1 for n in agregadas if n["categoria"] == c) for c in CATEGORIAS}
    print(f"noticias: {len(agregadas)} nuevas de {len(nuevas)} leídas — " + " · ".join(f"{c}: {v}" for c, v in por_cat.items()))
    fallidas = [c for c, _, falla in estado if falla and "opcional" not in falla]
    if seco:
        for c in CATEGORIAS:
            print(f"\n{c}")
            for n in sorted((n for n in agregadas if n["categoria"] == c), key=orden)[:10]:
                print(f"   {n['puntaje']:>3}  {n['edicion'][5:]} {n['orden']:>3}  {n['tema'][:16]:<16} {medio_de(n['fuente'])[:20]:<20} {n['titular'][:80]}")
        return 0
    rutas.PLATA.mkdir(parents=True, exist_ok=True)
    (rutas.PLATA / "noticias.csv").write_text(texto_csv(COLUMNAS, todas), encoding="utf-8", newline="")
    cerrada, por = escribir_ediciones(todas, ahora)
    print(f"  lago/plata/noticias.csv: {len(todas)} notas; última edición cerrada, {cerrada}: {len(por.get(cerrada, []))} notas")
    if len(fallidas) > len(cfg()["fuente"]) // 2:
        print(f"noticias: fallaron {len(fallidas)} fuentes: {', '.join(fallidas)}")
        return 1
    return 0


def _vecinas(ed):
    d = dt.date.fromisoformat(ed)
    return [(d + dt.timedelta(days=k)).isoformat() for k in (-1, 0, 1)]


# ------------------------------------------------------------------ Excel
def excel(notas, destino, titulo):
    """Un libro con la hoja «Todas» y una por categoría."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    cab = ["Fecha y hora", "Categoría", "Fuente", "Titular", "Resumen", "Enlace", "Tema"]
    anchos = [17, 30, 28, 70, 90, 50, 28]
    hojas = [("Todas", notas)] + [(c.replace(" – ", " - ")[:31], [n for n in notas if n["categoria"] == c]) for c in CATEGORIAS]
    for i, (nombre, filas) in enumerate(hojas):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = nombre
        ws.append([titulo])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append(cab)
        for c in ws[2]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3A5F")
        for n in filas:
            ws.append([n["fecha_hora"].replace("T", " "), n["categoria"], n["fuente"], n["titular"], n["resumen"], n["url"],
                       n.get("tema") or ""])
            celda = ws.cell(row=ws.max_row, column=6)
            celda.hyperlink, celda.font = n["url"], Font(color="1155CC", underline="single")
            for col in (4, 5):
                ws.cell(row=ws.max_row, column=col).alignment = Alignment(wrap_text=True, vertical="top")
        for j, a in enumerate(anchos):
            ws.column_dimensions["ABCDEFG"[j]].width = a
        ws.freeze_panes = "A3"
        ws.auto_filter.ref = f"A2:G{max(ws.max_row, 2)}"
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


def ediciones():
    por = {}
    for n in leer_plata():
        por.setdefault(n["edicion"], []).append(n)
    for filas in por.values():
        filas.sort(key=orden_edicion)
    return por


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("orden", nargs="?", choices=["excel"])
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--sin-red", action="store_true")
    ap.add_argument("--edicion")
    ap.add_argument("--destino")
    a = ap.parse_args()
    if a.orden == "excel":
        por = ediciones()
        cerradas = sorted(p.stem for p in (rutas.ORO / "noticias").glob("*.csv"))
        ed = a.edicion or (cerradas[-1] if cerradas else max(por))
        if ed not in por:
            raise SystemExit(f"no hay edición {ed}; están {', '.join(sorted(por)[-5:])}")
        destino = a.destino or f"noticias_{ed}.xlsx"
        excel(por[ed], destino, f"Resumen de noticias · edición del {ed}")
        print(f"  {destino}: {len(por[ed])} notas")
        return
    sys.exit(traer(seco=a.seco, sin_red=a.sin_red))


if __name__ == "__main__":
    main()
