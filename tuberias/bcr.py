"""Lector del portal de estadísticas del Banco Central de Reserva (https://estadisticas.bcr.gob.sv).

El portal es una aplicación Livewire: la página de una serie trae su estado inicial y, para cambiar el
rango o las variables, el navegador manda ese estado a /livewire/message/vista-serie con los cambios.
Este módulo hace lo mismo con pedidos HTTP, sin navegador.

Una serie viene en una de dos formas:

  «grafica»  el servidor entrega los datos de su gráfica (`graficaPredefinida` y `fechas_unicas`): un
             arreglo de valores por variable. Es la fuente. La tabla HTML que llega con ellos trae las
             mismas cifras pero recorridas por período y no por fila (cada tramo de n celdas es un
             período, en cualquier orden), así que solo sirve de contraste: el conjunto de cifras de
             cada período tiene que ser el mismo. La gráfica usa centinelas: -3000000 es «ND»,
             -6000000 es «C» (confidencial), y un 0 puede ser una celda vacía; la tabla lo aclara.
  «tabla»    no hay gráfica; la tabla HTML viene bien formada (una fila por variable) y es la fuente.

`leer()` devuelve lo que el servidor entregó, sin interpretarlo; `interpretar()` lo convierte en
observaciones y falla si la gráfica y la tabla no dicen lo mismo. Además, lo pedido se contrasta con
la vista que el portal muestra al abrir la página (los últimos períodos), que no pasa por el filtro.
"""
import html as _html
import json
import re
import time
from collections import Counter

import requests

BASE = "https://estadisticas.bcr.gob.sv"
AGENTE = "Mozilla/5.0 (compatible; lector-de-estadisticas-publicas)"
FRECUENCIA = {3: "M", 4: "A", 5: "T"}
CENTINELAS = {-3000000: "ND", -6000000: "C"}
LOTE = 30          # variables por pedido
MES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
       "oct": 10, "nov": 11, "dic": 12}
ROMANO = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


class ErrorPortal(Exception):
    pass


# ------------------------------------------------------------------ el HTML que sirve el portal
def limpio(x):
    x = re.sub(r"<[^>]+>", "", x)
    return re.sub(r"\s+", " ", _html.unescape(x).replace("\xa0", " ")).strip()


def tablas(h):
    """Cada <table> como filas de celdas {txt, span}."""
    out = []
    for t in re.findall(r"<table[\s\S]*?</table>", h):
        filas = []
        for fila in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", t):
            celdas = re.findall(r"<t[dh]\b([^>]*)>([\s\S]*?)</t[dh]>", fila)
            filas.append([{"txt": limpio(c), "span": int((re.search(r'colspan="?(\d+)', a) or [0, 1])[1])}
                          for a, c in celdas])
        out.append(filas)
    return out


def rotulo(x):
    """«1.1 Activos de Reserva [Matriz]» → («1.1», «Activos de Reserva»)."""
    x = re.sub(r"\s*\[Matriz\]\s*$", "", x).strip()
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$", x)
    return (m.group(1), m.group(2).strip()) if m else ("", x)


def _norma(x):
    return re.sub(r"[^a-z0-9]+", "", rotulo(x)[1].lower())


# ------------------------------------------------------------------ la conversación con el servidor
class Pagina:
    """La página de una serie abierta: su sesión, su estado y los mensajes que se le mandan."""

    def __init__(self, slug, pausa=0.7, reintentos=2):
        self.slug, self.pausa, self.reintentos = slug, pausa, reintentos
        self.url = f"{BASE}/serie/{slug}"
        self.s = requests.Session()
        self.s.headers["User-Agent"] = AGENTE
        self.ultimo = 0.0
        r = self._pedir("get", self.url)
        self.html = r.text
        m = re.search(r'name="csrf-token" content="([^"]+)"', self.html)
        if not m:
            raise ErrorPortal(f"{slug}: la página no trae su token")
        self.csrf = m.group(1)
        comp = None
        for x in re.finditer(r'wire:initial-data="([^"]+)"', self.html):
            d = json.loads(_html.unescape(x.group(1)))
            if d["fingerprint"]["name"] == "vista-serie":
                comp = d
        if comp is None:
            raise ErrorPortal(f"{slug}: la página no es la vista de una serie")
        self.huella, self.memo = comp["fingerprint"], comp["serverMemo"]
        self.n = 0

    @property
    def datos(self):
        return self.memo["data"]

    def _pedir(self, metodo, url, **kw):
        for intento in range(self.reintentos + 1):
            espera = self.pausa - (time.monotonic() - self.ultimo)
            if espera > 0:
                time.sleep(espera)
            self.ultimo = time.monotonic()
            try:
                r = self.s.request(metodo, url, timeout=300, **kw)
                if r.status_code == 200:
                    return r
                falla = f"HTTP {r.status_code}"
                if r.status_code not in (403, 429) and (r.status_code < 500 or metodo == "post"):
                    break
            except requests.RequestException as e:
                falla = type(e).__name__
            time.sleep(3 * (intento + 1))
        raise ErrorPortal(f"{self.slug}: {falla} en {url.replace(BASE, '')}")

    def mensaje(self, cambios, llamar):
        """Cambia propiedades y llama a un método del componente; devuelve (datos cambiados, html)."""
        ups = []
        for nombre, valor in cambios:
            self.n += 1
            ups.append({"type": "syncInput", "payload": {"id": f"e{self.n}", "name": nombre, "value": valor}})
        self.n += 1
        ups.append({"type": "callMethod", "payload": {"id": f"e{self.n}", "method": llamar, "params": []}})
        r = self._pedir("post", f"{BASE}/livewire/message/vista-serie",
                        json={"fingerprint": self.huella, "serverMemo": self.memo, "updates": ups},
                        headers={"X-CSRF-TOKEN": self.csrf, "X-Livewire": "true", "Referer": self.url,
                                 "Accept": "text/html, application/xhtml+xml"})
        j = r.json()
        nuevo = j["serverMemo"]
        cambiados = nuevo.get("data", {})
        self.memo = {**self.memo, **{k: v for k, v in nuevo.items() if k != "data"},
                     "data": {**self.memo["data"], **cambiados}}
        return cambiados, j.get("effects", {}).get("html") or ""


class Consulta:
    """Una página con sus variables ya elegidas, a la que se le piden rangos.

    El servidor responde 500 a ciertos rangos según lo que la misma página pidió antes (balanza de
    pagos: el último tramo falla si sigue a otro, y solo no). Ante un 5xx se abre una página nueva,
    se eligen las variables otra vez y el rango se pide de nuevo, una vez."""

    def __init__(self, slug, pausa, preparar, pagina=None):
        self.slug, self.pausa, self.preparar = slug, pausa, preparar
        self.p = pagina or Pagina(slug, pausa=pausa)
        self.fresca = True
        preparar(self.p)

    def rango(self, cambios):
        try:
            r = self.p.mensaje(cambios, "filtrar")
        except ErrorPortal as e:
            if "HTTP 5" not in str(e) or self.fresca:
                raise
            self.p = Pagina(self.slug, pausa=self.pausa)
            self.preparar(self.p)
            r = self.p.mensaje(cambios, "filtrar")
        self.fresca = False
        return r


def _tramos(d, tramo):
    a0, a1 = int(d["yearInicio"]), int(d["yearFin"])
    if not tramo:
        return [(a0, a1)]
    return [(a, min(a + tramo - 1, a1)) for a in range(a0, a1 + 1, tramo)]


def _rango(d, a0, a1):
    """Los cuatro campos del formulario de rango; el último período solo se limita en el último año."""
    c = [("yInicio", str(a0)), ("yFin", str(a1))]
    if d["tipoSerie"] != 4:
        ultimo = int(d["periodoFin"]) if a1 == int(d["yearFin"]) else int(d["pmax"])
        c += [("nInicio", str(int(d["pmin"]))), ("nFin", str(ultimo))]
    return c


def leer(slug, tramo=None, pausa=0.7):
    """Todo lo que el portal entrega de una serie: cada variable, de su primer período al último."""
    p = Pagina(slug, pausa=pausa)
    d = p.datos
    if d.get("mantenimiento"):
        raise ErrorPortal(f"{slug}: la serie está en mantenimiento")
    grafica = bool(d.get("variablesAGraficar")) and not d.get("tabular")
    out = {"slug": slug, "url": p.url, "nombre": d.get("nombreCuadro"), "unidades": d.get("unidadesCuadro"),
           "tipo_serie": d.get("tipoSerie"), "modo": "grafica" if grafica else "tabla",
           "decimales": d.get("defaultDecimal"), "notas": d.get("notas") or [],
           "documentos": d.get("documentos") or []}
    vista = _vista_inicial(p, grafica)
    if grafica:
        vag = d["variablesAGraficar"]
        out["variables"] = [{"id": int(v["graficar"]), "nombre": v.get("nombre_es") or "",
                             "nombre_en": v.get("nombre_en") or ""} for v in vag]
        out["fechas"], out["grafica"], out["tabla_celdas"] = None, [], []
        # el servidor se cae cuando la respuesta es muy grande: las variables se piden por lotes y los
        # años por tramos; cada lote abre su propia página
        for desde in range(0, len(vag), LOTE):
            lote = vag[desde:desde + LOTE]
            ids = [v["graficar"] for v in lote]
            q = Consulta(slug, pausa, lambda pag, ids=ids: pag.mensaje(
                [("filtroVariables", ids)], "filtrarVariablesGraficasPredefinidas"), None if desde else p)
            fechas, series, celdas = [], [[] for _ in ids], []
            for a0, a1 in _tramos(d, tramo):
                m, h = q.rango(_rango(d, a0, a1))
                gp, fu = m.get("graficaPredefinida"), m.get("fechas_unicas")
                if gp is None or fu is None:
                    raise ErrorPortal(f"{slug}: el servidor no devolvió la gráfica de {a0}–{a1}")
                if len(gp) != len(ids):
                    raise ErrorPortal(f"{slug}: se pidieron {len(ids)} variables y llegaron {len(gp)}")
                # los nombres son los rótulos de la tabla, que es lo que el portal muestra; el catálogo
                # de la gráfica (`variablesAGraficar`) puede traer un nombre viejo
                ts = tablas(h)
                if len(ts) < 2:
                    raise ErrorPortal(f"{slug}: el servidor no devolvió la tabla de {a0}–{a1}")
                rot = [f[0]["txt"] if f else "" for f in ts[-2][2:2 + len(ids)]]
                if len(rot) != len(ids):
                    raise ErrorPortal(f"{slug}: {len(ids)} variables pedidas y {len(rot)} rótulos en la tabla")
                for x, g in zip(rot, gp):
                    if _norma(x) != _norma(g["name"]):
                        raise ErrorPortal(f"{slug}: el rótulo «{x}» no es la variable «{g['name']}» de la gráfica")
                for v, x in zip(out["variables"][desde:desde + LOTE], rot):
                    v["nombre"] = re.sub(r"\s*\[Matriz\]\s*$", "", x)
                n = len(gp[0]["data"])
                if any(len(g["data"]) != n for g in gp) or len(fu) < n:
                    raise ErrorPortal(f"{slug}: las variables de {a0}–{a1} no tienen el mismo largo")
                fechas += fu[:n]
                for i, g in enumerate(gp):
                    series[i] += g["data"]
                valores = ts[-1][2:2 + len(ids)]          # después viene una fila de pie, que no es dato
                if len(valores) != len(ids) or any(len(f) != n for f in valores):
                    raise ErrorPortal(f"{slug}: la tabla de {a0}–{a1} no tiene {len(ids)} filas de {n} celdas")
                celdas += [c["txt"] for f in valores for c in f]
            if out["fechas"] is None:
                out["fechas"] = fechas
            elif fechas != out["fechas"]:
                raise ErrorPortal(f"{slug}: los lotes de variables no traen los mismos períodos")
            out["grafica"] += series
            out["tabla_celdas"].append(celdas)
    else:
        ids = re.findall(r'<input[^>]*name="variable\[\]"[^>]*value="(\d+)"', p.html)
        if not ids:
            raise ErrorPortal(f"{slug}: la página no lista variables")
        cab, rot, filas = [[], []], None, None
        q = Consulta(slug, pausa, lambda pag: None, p)
        for a0, a1 in _tramos(d, tramo):
            _, h = q.rango([("vars", ids)] + _rango(d, a0, a1))
            ts = tablas(h)
            if len(ts) < 2:
                raise ErrorPortal(f"{slug}: el servidor no devolvió la tabla de {a0}–{a1}")
            r = [f[0]["txt"] if f else "" for f in ts[-2][2:]]
            v = ts[-1][2:]
            while r and not r[-1] and (len(v) < len(r) or not any(c["txt"] for c in v[len(r) - 1])):
                r.pop()
            v = v[:len(r)]
            if len(r) != len(ids):
                raise ErrorPortal(f"{slug}: {len(ids)} variables pedidas, {len(r)} filas en la tabla")
            if rot is None:
                rot, filas = r, [[] for _ in r]
            elif r != rot:
                raise ErrorPortal(f"{slug}: los rótulos cambian entre tramos")
            cab[0] += [[c["txt"], c["span"]] for c in ts[-1][0]]
            cab[1] += [c["txt"] for c in ts[-1][1]]
            for i, f in enumerate(v):
                filas[i] += [c["txt"] for c in f]
        out["variables"] = [{"id": int(i), "nombre": re.sub(r"\s*\[Matriz\]\s*$", "", x), "nombre_en": ""}
                            for i, x in zip(ids, rot)]
        out["cabecera"] = cab
        out["filas"] = filas
    out["vista_inicial"] = vista
    return out


def _vista_inicial(p, grafica):
    """Lo que la página muestra al abrir, antes de cualquier filtro: sirve de testigo."""
    d = p.datos
    if grafica and d.get("graficaPredefinida"):
        gp = d["graficaPredefinida"]
        n = len(gp[0]["data"])
        return {"fechas": (d.get("fechas_unicas") or [])[:n],
                "series": [{"nombre": g["name"], "valores": g["data"]} for g in gp]}
    ts = tablas(p.html)
    if len(ts) >= 2 and len(ts[-1]) > 2:
        return {"cabecera": [[[c["txt"], c["span"]] for c in ts[-1][0]], [c["txt"] for c in ts[-1][1]]],
                "rotulos": [f[0]["txt"] if f else "" for f in ts[-2][2:]],
                "filas": [[c["txt"] for c in f] for f in ts[-1][2:]]}
    return {}


# ------------------------------------------------------------------ períodos
def periodo_grafica(x, frecuencia):
    """«2025-9(p)», «2005-01», «2020(r)» o 2021 → (año, subperíodo, estado)."""
    m = re.match(r"^\s*(\d{4})(?:-(\d{1,2}))?\s*(?:\(([a-zA-Z])\))?\s*$", str(x))
    if not m:
        raise ErrorPortal(f"período ilegible: {x!r}")
    return int(m.group(1)), int(m.group(2) or 1) if frecuencia != "A" else 1, (m.group(3) or "").lower()


def periodo_tabla(anio, per, frecuencia):
    """El año de la primera fila de cabecera y el rótulo de la segunda («Feb (p)», «II», «2024 (p)»)."""
    m = re.match(r"^\s*([^\s(]*)\s*(?:\(([a-zA-Z])\))?", per or "")
    base, estado = (m.group(1) or "").lower().rstrip("."), (m.group(2) or "").lower()
    ma = re.match(r"^\s*(\d{4})\s*(?:\(([a-zA-Z])\))?", str(anio))
    if not ma:
        raise ErrorPortal(f"año ilegible en la cabecera: {anio!r}")
    estado = estado or (ma.group(2) or "").lower()
    if frecuencia == "A":
        return int(ma.group(1)), 1, estado
    if frecuencia == "M":
        if base[:3] not in MES:
            raise ErrorPortal(f"mes ilegible en la cabecera: {per!r}")
        return int(ma.group(1)), MES[base[:3]], estado
    sub = ROMANO.get(base) or (int(re.sub(r"\D", "", base)) if re.sub(r"\D", "", base) else None)
    if sub not in (1, 2, 3, 4):
        raise ErrorPortal(f"trimestre ilegible en la cabecera: {per!r}")
    return int(ma.group(1)), sub, estado


def etiqueta(anio, sub, frecuencia):
    return str(anio) if frecuencia == "A" else f"{anio}-T{sub}" if frecuencia == "T" else f"{anio}-{sub:02d}"


def fecha(anio, sub, frecuencia):
    mes = 1 if frecuencia == "A" else (sub - 1) * 3 + 1 if frecuencia == "T" else sub
    return f"{anio}-{mes:02d}-01"


def numero(x):
    x = x.replace(",", "").strip()
    try:
        return float(x)
    except ValueError:
        return None


# ------------------------------------------------------------------ de lo servido a observaciones
def interpretar(b, frecuencia):
    """Lo que `leer()` guardó → (observaciones, resumen). Falla si las dos caras no coinciden.

    Cada observación es (año, subperíodo, estado, índice de variable, valor o None, marca)."""
    declarada = FRECUENCIA.get(b["tipo_serie"])
    if declarada != frecuencia:
        raise ErrorPortal(f"{b['slug']}: el catálogo dice frecuencia {frecuencia} y el portal {declarada}")
    obs, n = [], len(b["variables"])
    res = {"modo": b["modo"], "variables": n, "ambiguos": 0}
    if b["modo"] == "grafica":
        per = [periodo_grafica(x, frecuencia) for x in b["fechas"]]
        P = len(per)
        if sum(len(c) for c in b["tabla_celdas"]) != n * P:
            raise ErrorPortal(f"{b['slug']}: la tabla no trae las {n}×{P} celdas de la gráfica")
        siempre_cero = [all(v == 0 for v in s) for s in b["grafica"]]
        lotes, base = [], 0
        for celdas in b["tabla_celdas"]:
            lotes.append((base, len(celdas) // P, celdas))
            base += len(celdas) // P
        for (base, nl, celdas), (k, (a, sub, est)) in ((l, kp) for l in lotes for kp in enumerate(per)):
            tramo = celdas[k * nl:(k + 1) * nl]
            idx = range(base, base + nl)
            col = [b["grafica"][i][k] for i in idx]
            nums = sorted(x for x in (numero(c) for c in tramo) if x is not None)
            marcas = Counter(c for c in tramo if numero(c) is None)
            for v in col:
                if v in CENTINELAS:
                    marcas[CENTINELAS[v]] -= 1
                elif isinstance(v, (int, float)) and v <= -1000000 and v % 1000000 == 0:
                    raise ErrorPortal(f"{b['slug']}: centinela desconocido {v} en {etiqueta(a, sub, frecuencia)}")
            vacias = marcas.pop("", 0)
            if any(marcas.values()):
                raise ErrorPortal(f"{b['slug']} {etiqueta(a, sub, frecuencia)}: las marcas de la tabla "
                                  f"no son las de la gráfica ({dict(marcas)})")
            ceros = [i for i, v in zip(idx, col) if v == 0]
            if vacias > len(ceros):
                raise ErrorPortal(f"{b['slug']} {etiqueta(a, sub, frecuencia)}: {vacias} celdas vacías "
                                  f"y solo {len(ceros)} ceros en la gráfica")
            # qué ceros son celdas vacías: primero los rótulos sin dato (cero en toda la serie)
            vacios = set()
            if vacias == len(ceros):
                vacios = set(ceros)
            elif vacias:
                orden = sorted(ceros, key=lambda i: (not siempre_cero[i], i))
                vacios = set(orden[:vacias])
                if sum(siempre_cero[i] for i in ceros) != vacias:
                    res["ambiguos"] += 1
            esperados = sorted(v for i, v in zip(idx, col) if v not in CENTINELAS and i not in vacios)
            if len(esperados) != len(nums) or any(abs(x - y) > 0.0051 for x, y in zip(esperados, nums)):
                raise ErrorPortal(f"{b['slug']} {etiqueta(a, sub, frecuencia)}: las cifras de la tabla "
                                  f"no son las de la gráfica")
            for i, v in zip(idx, col):
                if v in CENTINELAS:
                    obs.append((a, sub, est, i, None, CENTINELAS[v]))
                elif i not in vacios:
                    obs.append((a, sub, est, i, float(v), ""))
    else:
        anios = [x for txt, span in b["cabecera"][0] for x in [txt] * span]
        pers = b["cabecera"][1]
        if frecuencia == "A" and len(pers) != len(anios):
            anios = pers
        if len(anios) != len(pers):
            raise ErrorPortal(f"{b['slug']}: la cabecera tiene {len(anios)} años y {len(pers)} períodos")
        per = [periodo_tabla(a, p, frecuencia) for a, p in zip(anios, pers)]
        for i, fila in enumerate(b["filas"]):
            if len(fila) != len(per):
                raise ErrorPortal(f"{b['slug']}: la fila {i} tiene {len(fila)} celdas y la cabecera {len(per)}")
            for (a, sub, est), c in zip(per, fila):
                v = numero(c)
                if v is not None:
                    obs.append((a, sub, est, i, v, ""))
                elif c.strip():
                    obs.append((a, sub, est, i, None, c.strip()))
    if len(set(per)) != len(per) or sorted(p[:2] for p in per) != [p[:2] for p in per]:
        raise ErrorPortal(f"{b['slug']}: los períodos no vienen en orden o se repiten")
    con_dato = [(a, s) for a, s, _, _, v, _ in obs if v is not None]
    if not con_dato:
        raise ErrorPortal(f"{b['slug']}: ninguna observación")
    res.update(periodos=len(per), observaciones=len(con_dato), desde=etiqueta(*min(con_dato), frecuencia),
               hasta=etiqueta(*max(con_dato), frecuencia))
    res["testigo"] = _contrastar_vista(b, obs, frecuencia)
    return obs, res


def _contrastar_vista(b, obs, frecuencia):
    """Las cifras de la vista inicial de la página tienen que estar, iguales, en lo pedido."""
    v = b.get("vista_inicial") or {}
    por = {}
    for a, sub, _, i, val, _ in obs:
        por[(i, a, sub)] = val
    nombres = {}
    for i, x in enumerate(b["variables"]):
        nombres.setdefault(_norma(x["nombre"]), []).append(i)
    vistos = distintos = 0
    if "series" in v:
        per = [periodo_grafica(x, frecuencia) for x in v["fechas"]]
        for s in v["series"]:
            cand = nombres.get(_norma(s["nombre"]), [])
            for (a, sub, _), val in zip(per, s["valores"]):
                if val in CENTINELAS or val == 0:
                    continue
                vistos += 1
                if not any(por.get((i, a, sub)) is not None and abs(por[(i, a, sub)] - val) < 1e-9 for i in cand):
                    distintos += 1
    elif "filas" in v:
        anios = [x for txt, span in v["cabecera"][0] for x in [txt] * span]
        pers = v["cabecera"][1]
        if frecuencia == "A" and len(pers) != len(anios):
            anios = pers
        per = [periodo_tabla(a, p, frecuencia) for a, p in zip(anios, pers)]
        for rot, fila in zip(v["rotulos"], v["filas"]):
            cand = nombres.get(_norma(rot), [])
            if len(fila) != len(per):
                continue
            for (a, sub, _), c in zip(per, fila):
                val = numero(c)
                if val is None:
                    continue
                vistos += 1
                if not any(por.get((i, a, sub)) is not None and abs(por[(i, a, sub)] - val) < 0.0051 for i in cand):
                    distintos += 1
    if distintos:
        raise ErrorPortal(f"{b['slug']}: {distintos} de {vistos} cifras de la vista inicial de la página "
                          f"no están en lo pedido")
    return vistos


def volcar(obj, nivel=0):
    """JSON legible en un diff: los arreglos de valores en una línea, lo demás con sangría."""
    sang = " " * nivel
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        partes = [f'{sang} {json.dumps(k, ensure_ascii=False)}: {volcar(v, nivel + 1)}' for k, v in obj.items()]
        return "{\n" + ",\n".join(partes) + f"\n{sang}}}"
    if isinstance(obj, list):
        if not obj or all(not isinstance(x, (dict, list)) for x in obj):
            return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return "[\n" + ",\n".join(f"{sang} {volcar(x, nivel + 1)}" for x in obj) + f"\n{sang}]"
    return json.dumps(obj, ensure_ascii=False)
