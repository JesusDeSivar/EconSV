#!/usr/bin/env python3
"""El resumen de noticias de cada mañana, en cinco categorías.

    python tuberias/noticias.py                       trae los feeds y actualiza el lago
    python tuberias/noticias.py --seco                los trae y muestra el reparto, sin escribir
    python tuberias/noticias.py excel                 escribe el Excel de la última edición
    python tuberias/noticias.py excel --edicion 2026-11-12 --destino resumen.xlsx

Las fuentes y las palabras están en catalogo/noticias_fuentes.toml. De cada nota se guarda solo lo que
su medio publica en su feed —titular, extracto, fecha y enlace—, nunca el texto completo.

  lago/plata/noticias.csv            todas las notas de los últimos `conservar_dias`, una por fila
                                     (`puntaje`: cuánto se parece la nota a lo que el dueño pone en sus
                                     reportes; sale de las listas [gusto] del catálogo y se recalcula entero
                                     en cada corrida, así que cambiar una lista cambia todos los puntajes)
  lago/oro/noticias/AAAA-MM-DD.csv   la edición de cada día: lo publicado de las 7:00 del día anterior
                                     a las 7:00 de ese día (hora de El Salvador), ordenado por categoría

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
COLUMNAS = ["id", "edicion", "fecha_hora", "categoria", "fuente", "titular", "resumen", "url", "idioma", "puntaje"]
COL_EDICION = ["fecha_hora", "categoria", "fuente", "titular", "resumen", "url", "puntaje"]
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


def _regex(lista):
    if lista not in _REGEX:
        partes = []
        for t in cfg()["palabras"][lista]:
            t = plano(t)
            partes.append(re.escape(t[:-1]) + r"\w*" if t.endswith("*") else re.escape(t))
        _REGEX[lista] = re.compile(r"(?<![\w])(?:" + "|".join(partes) + r")(?![\w])")
    return _REGEX[lista]


def cuenta(lista, texto):
    return len(_regex(lista).findall(plano(texto)))


def menciona_sv(texto):
    return cuenta("el_salvador", texto) > 0


def clasificar(texto, defecto):
    """La categoría de una nota por sus palabras; `defecto` es la de su fuente."""
    if menciona_sv(texto) or (defecto.startswith("El Salvador") and not any(
            cuenta(r, texto) for r in ("eua", "latam", "resto"))):
        return "El Salvador – Fiscales" if cuenta("fiscal", texto) or defecto == "El Salvador – Fiscales" \
            else "El Salvador – Nacionales"
    n = {"Internacional – EUA": cuenta("eua", texto), "Internacional – LATAM": cuenta("latam", texto),
         "Internacional – Resto del mundo": cuenta("resto", texto)}
    mejor = max(n.values())
    if mejor == 0:
        return defecto if defecto.startswith("Internacional") else "Internacional – Resto del mundo"
    ganan = [c for c, v in n.items() if v == mejor]
    return defecto if defecto in ganan else ganan[0]


def puntaje(n):
    """Cuánto se parece una nota a lo que entra en los reportes: 2 por cada palabra preferida de su
    categoría en el titular y 1 en el extracto, más el peso de su fuente, menos 3 por cada palabra de
    las que se evitan. Ordena dentro de una categoría; no compara categorías entre sí."""
    g = cfg().get("gusto", {}).get(n["categoria"])
    if not g:
        return 0
    p = 2 * cuenta(g["prefiere"], n["titular"]) + cuenta(g["prefiere"], n["resumen"])
    p -= 3 * cuenta(g["evita"], n["titular"] + " " + n["resumen"])
    if plano(n["titular"]).lstrip("«\"'“ ").startswith(tuple(plano(x) for x in cfg()["gusto_listas"]["titular_de_servicio"])):
        p -= 3
    return p + _pesos().get(n["fuente"], 0)


_PESOS = None


def _pesos():
    global _PESOS
    if _PESOS is None:
        _PESOS = {f["nombre"]: f.get("peso", 0) for f in cfg()["fuente"] if f.get("peso")}
    return _PESOS


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
            fuente, resumen = f"{medio} (vía Google News)" if medio else "Google News", ""
        texto = titular + " " + resumen
        if f.get("filtro") and not cuenta("economia", texto):
            continue
        if f.get("exige") and not cuenta(f["exige"], texto):
            continue
        url = c["url"] if f["metodo"] == "gnews" else url_limpia(c["url"])
        out.append({"id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:12], "edicion": edicion_de(momento),
                    "fecha_hora": momento.strftime("%Y-%m-%dT%H:%M"), "categoria": clasificar(texto, f["categoria"]),
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


def clave_titular(n):
    return re.sub(r"[^a-z0-9]+", "", plano(n["titular"]))[:90]


def orden(n):
    return (n["edicion"], CATEGORIAS.index(n["categoria"]), -int(n["puntaje"]), n["fecha_hora"], n["id"])


def orden_edicion(n):
    """Dentro de una edición: por categoría, lo más afín primero, y a igual puntaje lo más reciente."""
    return (CATEGORIAS.index(n["categoria"]), -int(n["puntaje"]), [-ord(c) for c in n["fecha_hora"]])


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


def traer(seco=False, ahora=None):
    global LARGO_RESUMEN
    LARGO_RESUMEN = cfg()["general"]["largo_resumen"]
    ahora = ahora or dt.datetime.now(SV)
    limite = (ahora.date() - dt.timedelta(days=cfg()["general"]["conservar_dias"])).isoformat()
    previas = [n for n in leer_plata() if n["edicion"] >= limite]
    red, nuevas, estado = Red(), [], []
    for f in cfg()["fuente"]:
        try:
            ns = notas_de(f, red, ahora, frozenset(n["id"] for n in previas))
            nuevas += ns
            estado.append((f["clave"], len(ns), ""))
        except (IOError, ET.ParseError, KeyError, ValueError) as e:
            estado.append((f["clave"], 0, f"{'opcional, ' if f.get('opcional') else ''}no respondió: {e}"))
    for clave, n, falla in estado:
        print(f"  {clave:<20} {n:>4} notas{'  — ' + falla if falla else ''}")
    if not nuevas:
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
    todas = previas + agregadas
    for n in todas:
        n["puntaje"] = puntaje(n)               # entero y de nuevo: depende solo del catálogo
    todas.sort(key=orden)
    por_cat = {c: sum(1 for n in agregadas if n["categoria"] == c) for c in CATEGORIAS}
    print(f"noticias: {len(agregadas)} nuevas de {len(nuevas)} leídas — " + " · ".join(f"{c}: {v}" for c, v in por_cat.items()))
    fallidas = [c for c, _, falla in estado if falla and "opcional" not in falla]
    if seco:
        for c in CATEGORIAS:
            print(f"\n{c}")
            for n in sorted((n for n in agregadas if n["categoria"] == c), key=orden_edicion)[:8]:
                print(f"   {n['puntaje']:>3}  {n['fecha_hora'][5:]}  {n['fuente'][:24]:<24} {n['titular'][:92]}")
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
    cab = ["Fecha y hora", "Categoría", "Fuente", "Titular", "Resumen", "Enlace"]
    anchos = [17, 30, 28, 70, 90, 50]
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
            ws.append([n["fecha_hora"].replace("T", " "), n["categoria"], n["fuente"], n["titular"], n["resumen"], n["url"]])
            celda = ws.cell(row=ws.max_row, column=6)
            celda.hyperlink, celda.font = n["url"], Font(color="1155CC", underline="single")
            for col in (4, 5):
                ws.cell(row=ws.max_row, column=col).alignment = Alignment(wrap_text=True, vertical="top")
        for j, a in enumerate(anchos):
            ws.column_dimensions["ABCDEF"[j]].width = a
        ws.freeze_panes = "A3"
        ws.auto_filter.ref = f"A2:F{max(ws.max_row, 2)}"
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)


def ediciones():
    por = {}
    for n in leer_plata():
        por.setdefault(n["edicion"], []).append(n)
    for filas in por.values():
        for n in filas:
            n["puntaje"] = n.get("puntaje") or 0
        filas.sort(key=orden_edicion)
    return por


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("orden", nargs="?", choices=["excel"])
    ap.add_argument("--seco", action="store_true")
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
    sys.exit(traer(seco=a.seco))


if __name__ == "__main__":
    main()
