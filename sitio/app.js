/* EconSV — el sitio. Lee window.ECONSV y window.ECONSV_NOTICIAS (sitio/datos/, que escribe
 * tuberias/sitio.py) y dibuja todo con SVG propio: no hay bibliotecas ni pedidos a otros servidores.
 * Todo texto que viene de los datos entra con textContent. Los colores están en estilo.css. */
"use strict";
(function () {
  const D = window.ECONSV, N = window.ECONSV_NOTICIAS || { categorias: [], ediciones: [], cerradas: [], notas: [] };
  const vista = document.getElementById("vista"), tip = document.getElementById("tip");
  if (!D) { vista.textContent = "Faltan los datos del sitio: corre «python tuberias/sitio.py»."; return; }

  const NS = "http://www.w3.org/2000/svg";
  const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  const MES3 = MESES.map((m) => m.slice(0, 3));
  const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const ORDINAL = ["primer", "segundo", "tercer", "cuarto"];
  const PAGINAS = [["inicio", "Inicio"]].concat(D.secciones.map((s) => [s.clave, s.nombre]),
    [["calendario", "Calendario"], ["noticias", "Noticias"], ["datos", "Datos"]]);
  const NOMBRE_VISTA = { nivel: () => "Nivel", var_anual: () => "Var. anual",
    var_periodo: (f) => (f === "M" ? "Var. mensual" : f === "T" ? "Var. trimestral" : "Var. anual"),
    suma_anual: (f) => (f === "M" ? "12 meses" : "4 trimestres"), pct_pib: () => "% del PIB",
    meses_importacion: () => "Meses de importación" };
  const estado = { rango: 10, vistas: {}, tablas: {}, noticias: { edicion: null, categoria: -1, texto: "" } };

  // ------------------------------------------------------------------ utilidades
  function h(tag, attrs, ...hijos) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "class") e.className = attrs[k];
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== false && attrs[k] != null) e.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    }
    for (const c of hijos.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  }
  const poner = (padre, ...hijos) => padre.replaceChildren(...hijos.flat().filter((c) => c != null && c !== false));
  function s(tag, attrs, padre) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (padre) padre.appendChild(e);
    return e;
  }
  const fmt = {};
  function num(v, d) {
    if (!fmt[d]) fmt[d] = new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
    return fmt[d].format(v).replace("-", "−");
  }
  function per(p) {
    const a = +p.slice(0, 4);
    if (p.length === 4) return { t: Date.UTC(a, 0, 1), corto: p, nombre: p, f: "A" };
    if (p[5] === "T") { const q = +p[6]; return { t: Date.UTC(a, (q - 1) * 3, 1), corto: "T" + q + " " + a, nombre: ORDINAL[q - 1] + " trimestre de " + a, f: "T" }; }
    const m = +p.slice(5, 7);
    return { t: Date.UTC(a, m - 1, 1), corto: MES3[m - 1] + " " + a, nombre: MESES[m - 1] + " de " + a, f: "M" };
  }
  const enP = (x) => (x.f === "T" ? "en el " : "en ") + x.nombre;
  const aP = (x) => (x.f === "T" ? "al " : "a ") + x.nombre;
  const finP = (x) => (x.f === "T" ? "al cierre del " : x.f === "M" ? "a fin de " : "al cierre de ") + x.nombre;
  function fechaCorta(iso, conAnio) {
    const d = new Date(iso + "T12:00:00Z");
    return DIAS[d.getUTCDay()] + " " + d.getUTCDate() + " " + MES3[d.getUTCMonth()] + (conAnio ? " " + d.getUTCFullYear() : "");
  }
  function hoySV() { return new Date(Date.now() - 6 * 3600e3).toISOString().slice(0, 10); }
  function diasEntre(a, b) { return Math.round((Date.parse(b) - Date.parse(a)) / 864e5); }
  const esTasa = (v) => v === "var_anual" || v === "var_periodo";

  /* Cómo se escribe una cifra según la vista y la unidad del indicador: {cifra, unidad}. */
  function partes(v, vistaK, ind) {
    if (esTasa(vistaK)) return { cifra: (v > 0 ? "+" : "") + num(v, 1) + " %", unidad: "" };
    if (vistaK === "pct_pib") return { cifra: num(v, 1) + " %", unidad: "del PIB" };
    if (vistaK === "meses_importacion") return { cifra: num(v, 1), unidad: "meses de importación" };
    const u = ind.unidad, a = Math.abs(v);
    if (u === "Millones de US$") return { cifra: "US$ " + num(v, a >= 1000 ? 0 : 1), unidad: "millones" };
    if (u === "Personas") return a >= 1e6 ? { cifra: num(v / 1e6, 2), unidad: "millones de personas" } : { cifra: num(v, 0), unidad: "personas" };
    if (u.startsWith("Miles de bolsas")) return a >= 1000 ? { cifra: num(v / 1000, 1), unidad: "millones de bolsas" } : { cifra: num(v, 0), unidad: "mil bolsas" };
    return { cifra: num(v, 1), unidad: "" };
  }
  function texto(v, vistaK, ind) { const p = partes(v, vistaK, ind); return p.cifra + (p.unidad ? " " + p.unidad : ""); }
  function unidadEje(vistaK, ind) {
    if (esTasa(vistaK)) return "Variación, %";
    if (vistaK === "pct_pib") return "% del PIB";
    if (vistaK === "meses_importacion") return "Meses de importación de mercancías";
    return ind.unidad + (vistaK === "suma_anual" ? (ind.frecuencia === "M" ? ", suma de 12 meses" : ", suma de 4 trimestres") : "");
  }
  function contexto(vistaK, ind, p) {
    const f = ind.frecuencia;
    if (vistaK === "var_anual") return (f === "A" ? "" : "anual ") + enP(p);
    if (vistaK === "var_periodo") return (f === "M" ? "frente al mes anterior, " : "frente al trimestre anterior, ") + enP(p);
    if (vistaK === "suma_anual") return (f === "M" ? "en los 12 meses " : "en los cuatro trimestres ") + aP(p);
    if (vistaK === "pct_pib") return ind.naturaleza === "saldo" ? finP(p) : "en los cuatro trimestres " + aP(p);
    if (vistaK === "meses_importacion") return enP(p);
    return ind.naturaleza === "saldo" ? finP(p) : enP(p);
  }
  function ultimo(d) { const i = d.p.length - 1; return { p: d.p[i], v: d.v[i] }; }
  function vistasDe(ind) { return ind.vistas.filter((v) => ind.lineas.some((l) => l.vistas[v] && l.vistas[v].p.length)); }
  function vistaActual(ind) { const vs = vistasDe(ind); return vs.includes(estado.vistas[ind.clave]) ? estado.vistas[ind.clave] : vs[0]; }
  function proxima(ind) {
    let mejor = null;
    for (const k of ind.series) { const x = D.series[k]; if (x && x.esperado && (!mejor || x.esperado < mejor.esperado)) mejor = x; }
    return mejor;
  }
  function corte(ind) { return ind.series.map((k) => D.series[k].hasta).sort()[0]; }

  // ------------------------------------------------------------------ tooltip
  function mostrarTip(x, y, cab, filas) {
    poner(tip, h("div", { class: "t-per" }, cab),
      filas.map((f) => h("div", { class: "t-fila" }, f.k != null ? h("span", { class: "llave" + (f.k ? " k2" : "") }) : null, h("b", {}, f.valor), h("span", { class: "nom" }, f.nombre))));
    tip.hidden = false;
    const r = tip.getBoundingClientRect(), W = window.innerWidth, H = window.innerHeight;
    let px = x + 14, py = y - r.height - 12;
    if (px + r.width > W - 8) px = x - r.width - 14;
    if (px < 8) px = 8;
    if (py < 8) py = Math.min(y + 16, H - r.height - 8);
    tip.style.left = px + "px"; tip.style.top = py + "px";
  }
  function ocultarTip() { tip.hidden = true; }

  // ------------------------------------------------------------------ ejes
  function pasos(min, max, n) {
    if (min === max) { min -= 1; max += 1; }
    const bruto = (max - min) / n, mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const paso = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => (max - min) / p <= n) || 10 * mag;
    const lo = Math.floor(min / paso) * paso, hi = Math.ceil(max / paso) * paso, t = [];
    for (let v = lo; v <= hi + paso / 2; v += paso) t.push(Math.abs(v) < paso / 1e6 ? 0 : +v.toFixed(10));
    return t;
  }
  function eje(v, maxAbs, paso) {
    if (maxAbs >= 1e6) return num(v / 1e6, Number.isInteger(paso / 1e6) ? 0 : 1) + " M";
    if (maxAbs >= 1e4) return num(v / 1e3, Number.isInteger(paso / 1e3) ? 0 : 1) + " mil";
    return num(v, Number.isInteger(paso) ? 0 : paso >= 0.1 ? 1 : 2);
  }
  function barra(x, w, y0, y1) {
    const r = Math.min(4, w / 2, Math.abs(y1 - y0)), sg = y1 < y0 ? 1 : -1;
    return "M" + x + "," + y0 + "V" + (y1 + sg * r) + "Q" + x + "," + y1 + " " + (x + r) + "," + y1 + "H" + (x + w - r) +
      "Q" + (x + w) + "," + y1 + " " + (x + w) + "," + (y1 + sg * r) + "V" + y0 + "Z";
  }

  /* Una serie de tiempo: líneas (una o dos) o barras (una sola). `lineas` = [{nombre, pts:[{t,v,p}]}]. */
  function dibujarTiempo(lienzo, ind, vistaK, lineas, enBarras) {
    lienzo.replaceChildren();
    const W = Math.max(280, lienzo.clientWidth), H = W < 420 ? 220 : 260;
    const todos = lineas.flatMap((l) => l.pts);
    if (!todos.length) { lienzo.append(h("p", { class: "vacio" }, "Sin datos en este rango.")); return; }
    let vmin = Math.min(...todos.map((d) => d.v)), vmax = Math.max(...todos.map((d) => d.v));
    if (enBarras || esTasa(vistaK) || (vmin > 0 && vmin < vmax * 0.35)) { vmin = Math.min(vmin, 0); vmax = Math.max(vmax, 0); }
    const holgura = (vmax - vmin) * 0.06 || 1;
    const ticks = pasos(vmin - (vmin < 0 ? holgura : 0), vmax + (vmax > 0 ? holgura : 0), 5);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1], paso = ticks[1] - ticks[0], maxAbs = Math.max(Math.abs(y0), Math.abs(y1));
    const rot = ticks.map((t) => eje(t, maxAbs, paso));
    const fin = !enBarras && lineas.length === 1 ? partes(lineas[0].pts[lineas[0].pts.length - 1].v, vistaK, ind).cifra.replace("US$ ", "") : "";
    const m = { l: Math.max(...rot.map((r) => r.length)) * 6.6 + 12, r: fin ? fin.length * 6.8 + 16 : 14, t: 8, b: 26 };
    const ts = [...new Set(todos.map((d) => d.t))].sort((a, b) => a - b);
    const banda = ts.length > 1 ? (W - m.l - m.r) / (enBarras ? ts.length : ts.length - 1) : W - m.l - m.r;
    const t0 = ts[0], t1 = ts[ts.length - 1];
    const X = enBarras ? (t) => m.l + (ts.indexOf(t) + 0.5) * banda : (t) => (t1 === t0 ? (m.l + W - m.r) / 2 : m.l + ((t - t0) / (t1 - t0)) * (W - m.l - m.r));
    const Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const svg = s("svg", { viewBox: "0 0 " + W + " " + H, height: H, role: "img", tabindex: 0 });
    svg.setAttribute("aria-label", ind.titulo + ", " + NOMBRE_VISTA[vistaK](ind.frecuencia) + ". Con las flechas se recorre período por período; la tabla tiene todas las cifras.");
    ticks.forEach((t, i) => {
      s("line", { class: t === 0 ? "g-cero" : "g-rej", x1: m.l, x2: W - m.r, y1: Math.round(Y(t)) + 0.5, y2: Math.round(Y(t)) + 0.5 }, svg);
      const e = s("text", { class: "g-txt", x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg); e.textContent = rot[i];
    });
    // el eje del tiempo: años, tantos como quepan
    const a0 = new Date(t0).getUTCFullYear(), a1 = new Date(t1).getUTCFullYear();
    const cada = [1, 2, 5, 10, 20].find((c) => (a1 - a0 + 1) / c <= Math.max(2, Math.floor((W - m.l - m.r) / 56))) || 20;
    for (let a = Math.ceil(a0 / cada) * cada; a <= a1; a += cada) {
      const t = Date.UTC(a, 0, 1), x = enBarras ? (ts.includes(t) ? X(t) : null) : (t >= t0 && t <= t1 ? X(t) : null);
      if (x == null) continue;
      const e = s("text", { class: "g-txt", x: x, y: H - 6, "text-anchor": "middle" }, svg); e.textContent = String(a);
    }
    const marcas = [];
    if (enBarras) {
      const w = Math.max(2, Math.min(24, banda - 2));
      lineas[0].pts.forEach((d) => marcas.push(s("path", { class: "g-barra", d: barra(X(d.t) - w / 2, w, Y(0), Y(d.v)) }, svg)));
    } else {
      const salto = { M: 32, T: 93, A: 367 }[ind.frecuencia === "M" && vistaK === "pct_pib" ? "T" : ind.frecuencia] * 864e5 * 1.5;
      lineas.forEach((l, k) => {
        let d = "", ant = null;
        l.pts.forEach((p) => { d += (ant == null || p.t - ant > salto ? "M" : "L") + X(p.t).toFixed(1) + "," + Y(p.v).toFixed(1); ant = p.t; });
        s("path", { class: "g-linea" + (k ? " k2" : ""), d: d }, svg);
        const u = l.pts[l.pts.length - 1];
        s("circle", { class: "g-punto" + (k ? " k2" : ""), cx: X(u.t), cy: Y(u.v), r: 4 }, svg);
      });
      if (fin) { const u = lineas[0].pts[lineas[0].pts.length - 1]; const e = s("text", { class: "g-fin", x: X(u.t) + 9, y: Y(u.v) + 4 }, svg); e.textContent = fin; }
    }
    // la mira: sigue al puntero y se queda en el período más cercano; con el teclado, flechas
    const mira = s("line", { class: "g-mira", y1: m.t, y2: H - m.b, visibility: "hidden" }, svg);
    const puntos = lineas.map((l, k) => s("circle", { class: "g-punto" + (k ? " k2" : ""), r: 4.5, visibility: "hidden" }, svg));
    const por = lineas.map((l) => new Map(l.pts.map((d) => [d.t, d])));
    let actual = -1;
    function ir(i, cx, cy) {
      actual = Math.max(0, Math.min(ts.length - 1, i));
      const t = ts[actual], x = X(t), filas = [];
      let etiqueta = "";
      lineas.forEach((l, k) => {
        const d = por[k].get(t);
        if (!enBarras) puntos[k].setAttribute("visibility", d ? "visible" : "hidden");
        if (!d) return;
        etiqueta = d.p;
        if (!enBarras) { puntos[k].setAttribute("cx", x); puntos[k].setAttribute("cy", Y(d.v)); }
        filas.push({ k: lineas.length > 1 ? k : null, valor: texto(d.v, vistaK, ind), nombre: lineas.length > 1 ? l.nombre : "" });
      });
      if (enBarras) marcas.forEach((b, j) => b.classList.toggle("tenue", j !== actual));
      else { mira.setAttribute("x1", Math.round(x) + 0.5); mira.setAttribute("x2", Math.round(x) + 0.5); mira.setAttribute("visibility", "visible"); }
      const caja = svg.getBoundingClientRect();
      mostrarTip(cx != null ? cx : caja.left + x * (caja.width / W), cy != null ? cy : caja.top + m.t + 24, per(etiqueta).corto, filas);
    }
    function salir() {
      actual = -1; ocultarTip(); mira.setAttribute("visibility", "hidden");
      puntos.forEach((p) => p.setAttribute("visibility", "hidden")); marcas.forEach((b) => b.classList.remove("tenue"));
    }
    svg.addEventListener("pointermove", (ev) => {
      const caja = svg.getBoundingClientRect(), px = (ev.clientX - caja.left) * (W / caja.width);
      let i = 0, mejor = Infinity;
      ts.forEach((t, j) => { const dd = Math.abs(X(t) - px); if (dd < mejor) { mejor = dd; i = j; } });
      ir(i, ev.clientX, ev.clientY);
    });
    svg.addEventListener("pointerleave", salir);
    svg.addEventListener("blur", salir);
    svg.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") { ev.preventDefault(); ir(actual < 0 ? ts.length - 1 : actual + (ev.key === "ArrowLeft" ? -1 : 1)); }
      else if (ev.key === "Home") { ev.preventDefault(); ir(0); } else if (ev.key === "End") { ev.preventDefault(); ir(ts.length - 1); }
      else if (ev.key === "Escape") salir();
    });
    lienzo.append(svg);
  }

  /* El último dato de cada línea, ordenado: una barra por categoría, un solo color, la cifra al lado. */
  function dibujarRanking(lienzo, ind, vistaK) {
    lienzo.replaceChildren();
    const filas = ind.lineas.filter((l) => l.vistas[vistaK] && l.vistas[vistaK].p.length).map((l) => ({ nombre: l.nombre, ...ultimo(l.vistas[vistaK]) }));
    const ult = filas.map((f) => f.p).sort().pop();
    const vig = filas.filter((f) => f.p === ult).sort((a, b) => b.v - a.v);
    const lo = Math.min(0, ...vig.map((f) => f.v)), hi = Math.max(0, ...vig.map((f) => f.v)), an = hi - lo || 1;
    const caja = h("div", { class: "rank", role: "list" });
    vig.forEach((f) => {
      const pista = h("div", { class: "r-pista" }, h("span", { class: "r-cero", style: "left:" + ((0 - lo) / an) * 100 + "%" }),
        h("span", { class: "r-bar" + (f.v < 0 ? " neg" : ""), style: "left:" + ((Math.min(0, f.v) - lo) / an) * 100 + "%;width:" + (Math.abs(f.v) / an) * 100 + "%" }));
      caja.append(h("div", { class: "r-nom", role: "listitem" }, f.nombre), pista, h("div", { class: "r-val" }, partes(f.v, vistaK, ind).cifra));
      pista.addEventListener("pointermove", (ev) => mostrarTip(ev.clientX, ev.clientY, per(f.p).corto, [{ valor: texto(f.v, vistaK, ind), nombre: f.nombre }]));
      pista.addEventListener("pointerleave", ocultarTip);
    });
    lienzo.append(caja);
    return { periodo: ult, filas: vig };
  }

  function chispa(d) {
    const n = Math.min(d.v.length, 36), v = d.v.slice(-n), W = 96, H = 30, lo = Math.min(...v), hi = Math.max(...v);
    const X = (i) => 3 + (i / (n - 1 || 1)) * (W - 8), Y = (x) => 4 + (1 - (x - lo) / (hi - lo || 1)) * (H - 8);
    const svg = s("svg", { class: "chispa", viewBox: "0 0 " + W + " " + H, width: W, height: H, "aria-hidden": "true" });
    s("path", { d: v.map((x, i) => (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(x).toFixed(1)).join("") }, svg);
    s("circle", { cx: X(n - 1), cy: Y(v[n - 1]), r: 3.5 }, svg);
    return svg;
  }

  // ------------------------------------------------------------------ tarjeta de un indicador
  function recorte(d) {
    const pts = d.p.map((p, i) => ({ p: p, t: per(p).t, v: d.v[i] }));
    if (!estado.rango || !pts.length) return pts;
    const u = new Date(pts[pts.length - 1].t), desde = Date.UTC(u.getUTCFullYear() - estado.rango, u.getUTCMonth(), 1);
    return pts.filter((x) => x.t >= desde);
  }
  function descargar(nombre, filas) {
    const csv = "﻿" + filas.map((f) => f.map((c) => (/[",\n]/.test(String(c)) ? '"' + String(c).replace(/"/g, '""') + '"' : c)).join(",")).join("\r\n");
    const a = h("a", { href: URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })), download: nombre });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function matriz(ind, vistaK) {
    const ls = ind.lineas.filter((l) => l.vistas[vistaK]), ps = [...new Set(ls.flatMap((l) => l.vistas[vistaK].p))].sort();
    const por = ls.map((l) => new Map(l.vistas[vistaK].p.map((p, i) => [p, l.vistas[vistaK].v[i]])));
    return { ls: ls, filas: ps.map((p) => [p].concat(por.map((m) => (m.has(p) ? m.get(p) : "")))) };
  }

  function tarjeta(ind) {
    const fig = h("figure", { class: "tarjeta", id: "ind-" + ind.clave });
    const lienzo = h("div", { class: "lienzo" });
    function pintar() {
      const vk = vistaActual(ind), vs = vistasDe(ind), ls = ind.lineas.filter((l) => l.vistas[vk] && l.vistas[vk].p.length);
      const cab = h("div", { class: "t-top" }, h("h3", {}, ind.titulo));
      if (vs.length > 1) {
        cab.append(h("div", { class: "seg", role: "group", "aria-label": "Qué se mide" }, vs.map((v) =>
          h("button", { type: "button", "aria-pressed": String(v === vk), onclick: () => { estado.vistas[ind.clave] = v; pintar(); } }, NOMBRE_VISTA[v](ind.frecuencia)))));
      }
      const hall = h("p", { class: "hallazgo" }), tablaAbierta = !!estado.tablas[ind.clave];
      let leyenda = null, cuerpo;
      if (ind.tipo === "ranking") {
        const r = dibujarRanking(lienzo, ind, vk), top = r.filas[0], pp = partes(top.v, vk, ind);
        hall.append(h("strong", {}, pp.cifra), top.nombre + ", la mayor " + (esTasa(vk) ? "variación" : "cifra") + " · " + contexto(vk, ind, per(r.periodo)));
      } else {
        const u = ultimo(ls[0].vistas[vk]), pp = partes(u.v, vk, ind);
        hall.append(h("strong", {}, pp.cifra), (pp.unidad ? pp.unidad + " " : "") + contexto(vk, ind, per(u.p)));
        if (ls.length > 1) {
          leyenda = h("ul", { class: "leyenda" }, ls.map((l, k) => { const x = ultimo(l.vistas[vk]); return h("li", {}, h("span", { class: "llave" + (k ? " k2" : "") }), l.nombre, h("b", {}, partes(x.v, vk, ind).cifra)); }));
        }
      }
      const mt = matriz(ind, vk);
      const tabla = h("div", { class: "tabla-vista", hidden: !tablaAbierta }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Período"), mt.ls.map((l) => h("th", { class: "n" }, l.nombre)))),
        h("tbody", {}, mt.filas.slice().reverse().map((f) => h("tr", {}, h("td", { class: "fijo" }, per(f[0]).corto), f.slice(1).map((v) => h("td", { class: "n" }, v === "" ? "" : partes(v, vk, ind).cifra)))))));
      const px = proxima(ind), fuente = D.series[ind.series[0]];
      const pie = h("div", { class: "pie-t" },
        h("p", {}, "Fuente: ", h("a", { href: fuente.url, rel: "noopener" }, "BCR"), " · dato a " + per(corte(ind)).corto,
          px ? " · próximo: " + per(px.proximo).corto + ", " + fechaCorta(px.esperado) + (px.origen === "rezago" ? " (estimada)" : "") : ""),
        h("div", { class: "acc" },
          h("button", { class: "boton quieto", type: "button", "aria-expanded": String(tablaAbierta), onclick: () => { estado.tablas[ind.clave] = !tablaAbierta; pintar(); } }, tablaAbierta ? "Ocultar tabla" : "Ver tabla"),
          h("button", { class: "boton quieto", type: "button", onclick: () => descargar("econsv_" + ind.clave + "_" + vk + ".csv", [["periodo"].concat(mt.ls.map((l) => l.nombre))].concat(mt.filas)) }, "CSV")));
      poner(fig, cab, hall, leyenda, ind.tipo === "ranking" ? null : h("p", { class: "unidad" }, unidadEje(vk, ind)), lienzo, tabla, pie, ind.nota ? h("p", { class: "nota" }, ind.nota) : null);
      if (ind.tipo !== "ranking") {
        cuerpo = ls.map((l) => ({ nombre: l.nombre, pts: recorte(l.vistas[vk]) }));
        dibujarTiempo(lienzo, ind, vk, cuerpo, ind.tipo === "barras" && ls.length === 1);
      }
    }
    fig._pintar = pintar;
    return fig;
  }

  // ------------------------------------------------------------------ páginas
  function controlRango() {
    return h("div", { class: "filtros" }, h("span", { class: "rot", id: "rot-rango" }, "Rango"),
      h("div", { class: "seg", role: "group", "aria-labelledby": "rot-rango" }, [[5, "5 años"], [10, "10 años"], [20, "20 años"], [0, "Todo"]].map(([n, t]) =>
        h("button", { type: "button", "aria-pressed": String(estado.rango === n), onclick: () => { estado.rango = n; render(); } }, t))));
  }
  function paginaSeccion(sec, ancla) {
    const inds = D.indicadores.filter((i) => i.seccion === sec.clave), rej = h("div", { class: "rejilla" }, inds.map(tarjeta));
    poner(vista, h("h1", {}, sec.nombre), h("p", { class: "bajada" }, BAJADAS[sec.clave]), controlRango(), rej);
    rej.querySelectorAll(".tarjeta").forEach((f) => f._pintar());
    if (ancla) { const e = document.getElementById("ind-" + ancla); if (e) e.scrollIntoView(); }
  }
  const BAJADAS = {
    actividad: "Cuánto produce la economía y a qué ritmo: el PIB anual y trimestral y el IVAE, el indicador mensual de la producción.",
    precios: "Cuánto suben los precios al consumidor y al productor, y en qué divisiones del gasto.",
    externo: "Lo que entra y sale del país: remesas, comercio de mercancías, inversión extranjera, posición de inversión internacional y reservas.",
    turismo: "Lo que el BCR publica sobre el turismo: los ingresos por viajes de la balanza de pagos, el movimiento de pasajeros y el valor agregado de alojamiento y comidas.",
    construccion: "La construcción en el IVAE y en el PIB trimestral, y el consumo aparente de cemento. La inversión extranjera en construcción es confidencial en casi todos los trimestres y no se grafica.",
  };

  function ficha(ind) {
    const vk = vistasDe(ind)[0], l = ind.lineas.find((x) => x.vistas[vk]), d = l.vistas[vk], u = ultimo(d), pp = partes(u.v, vk, ind);
    let delta = "";
    if (esTasa(vk) || vk === "pct_pib") {
      if (d.v.length > 1) { const dif = u.v - d.v[d.v.length - 2]; delta = (dif >= 0 ? "▲ " : "▼ ") + num(Math.abs(dif), 1) + " pp frente a " + per(d.p[d.p.length - 2]).corto; }
    } else {
      const antes = String(+u.p.slice(0, 4) - 1) + u.p.slice(4), j = d.p.indexOf(antes);
      if (j >= 0 && d.v[j] > 0) { const c = (u.v / d.v[j] - 1) * 100; delta = (c >= 0 ? "▲ " : "▼ ") + num(Math.abs(c), 1) + " % en un año"; }
    }
    const px = proxima(ind);
    return h("a", { class: "ficha", href: "#/" + ind.seccion + "/" + ind.clave },
      h("span", { class: "f-rot" }, ind.titulo),
      h("span", { class: "f-val" }, pp.cifra, pp.unidad ? h("small", {}, pp.unidad) : null),
      h("span", { class: "f-sub" }, contexto(vk, ind, per(u.p))),
      h("span", { class: "f-pie" }, h("span", { class: "f-delta" }, delta), chispa(d)),
      px ? h("span", { class: "f-prox" }, "Próximo dato: " + per(px.proximo).corto + " · " + fechaCorta(px.esperado) + (px.origen === "rezago" ? " (estimada)" : "")) : null);
  }
  function proximas(n) {
    const hoy = hoySV(), grupos = new Map();
    D.calendario.filter((c) => !c.en_lago).forEach((c) => {
      const k = c.fecha + "|" + c.periodo; if (!grupos.has(k)) grupos.set(k, { fecha: c.fecha, periodo: c.periodo, origen: c.origen, series: [] });
      grupos.get(k).series.push(D.series[c.serie].nombre);
    });
    return [...grupos.values()].sort((a, b) => (a.fecha < b.fecha ? -1 : a.fecha > b.fecha ? 1 : 0)).slice(0, n).map((g) => ({ ...g, dias: diasEntre(hoy, g.fecha) }));
  }
  function cuandoTexto(g) {
    if (g.dias > 1) return "en " + g.dias + " días";
    if (g.dias === 1) return "mañana";
    if (g.dias === 0) return "hoy";
    return g.dias >= -10 ? "toca desde hace " + -g.dias + (g.dias === -1 ? " día" : " días") : "atrasada " + -g.dias + " días";
  }
  function paginaInicio() {
    const ed = N.cerradas[N.cerradas.length - 1] || N.ediciones[N.ediciones.length - 1];
    const titulares = N.notas.filter((n) => n[0] === ed && n[2] >= 3).sort((a, b) => (b[7] || 0) - (a[7] || 0) || (a[1] < b[1] ? 1 : -1)).slice(0, 6);
    poner(vista, 
      h("h1", {}, "Signos vitales de la economía salvadoreña"),
      h("p", { class: "bajada" }, "Los indicadores que publica el Banco Central de Reserva, puestos al día según su calendario de divulgación, y un resumen de noticias cada mañana."),
      h("div", { class: "fichas" }, D.indicadores.filter((i) => i.portada).map(ficha)),
      h("div", { class: "dos" },
        h("section", {}, h("h2", {}, "Próximas publicaciones"),
          h("div", { class: "caja" }, h("ul", { class: "lista" }, proximas(6).map((g) => h("li", {}, h("span", { class: "cuando" }, fechaCorta(g.fecha)),
            h("span", {}, h("strong", {}, per(g.periodo).corto + " · "), g.series.join("; "), " ", h("span", { class: "chip" }, cuandoTexto(g))))))),
          h("a", { class: "mas", href: "#/calendario" }, "Ver el calendario completo")),
        h("section", {}, h("h2", {}, "El Salvador en las noticias"),
          h("div", { class: "caja" }, titulares.length ? h("ul", { class: "lista" }, titulares.map((n) => h("li", {}, h("span", { class: "cuando" }, n[1].slice(11) + " · " + fechaCorta(n[1].slice(0, 10)).split(" ").slice(1).join(" ")),
            h("span", {}, h("a", { class: "titular", href: n[6], rel: "noopener" }, n[4]), h("span", { class: "resumen" }, n[3]))))) : h("p", { class: "vacio" }, "Todavía no hay edición de noticias.")),
          h("a", { class: "mas", href: "#/noticias" }, "Ver y descargar el resumen de noticias"))));
  }

  function paginaCalendario() {
    const hoy = hoySV(), pend = proximas(200);
    const hechas = D.calendario.filter((c) => c.en_lago && c.origen === "bcr").sort((a, b) => (a.fecha < b.fecha ? 1 : -1)).slice(0, 18);
    poner(vista, 
      h("h1", {}, "Calendario de actualización"),
      h("p", { class: "bajada" }, "La fecha en que se espera cada dato. Casi todas vienen del calendario de divulgación del BCR; donde el BCR aún no anuncia el período que sigue, la fecha es una estimación con el rezago habitual de la serie. Dos veces al día, de lunes a sábado, el sitio revisa este calendario y trae solo lo que toca."),
      h("h2", {}, "Lo que viene"),
      h("div", { class: "caja desliza" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Se espera"), h("th", {}, "Período"), h("th", {}, "Qué se publica"), h("th", {}, "Fecha"), h("th", {}, "Estado"))),
        h("tbody", {}, pend.map((g) => h("tr", {}, h("td", { class: "fijo" }, fechaCorta(g.fecha, true)), h("td", { class: "fijo" }, per(g.periodo).corto), h("td", {}, g.series.join("; ")),
          h("td", {}, h("span", { class: "chip" }, g.origen === "bcr" ? "anunciada por el BCR" : "estimada")), h("td", { class: "fijo" }, h("span", { class: "chip" + (g.dias <= 0 ? " fuerte" : "") }, cuandoTexto(g)))))))),
      h("h2", {}, "Hasta dónde llega cada serie"),
      h("div", { class: "caja desliza" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Serie"), h("th", {}, "Frecuencia"), h("th", {}, "Llega a"), h("th", {}, "Última vez que cambió"), h("th", {}, "Próximo dato"))),
        h("tbody", {}, Object.entries(D.series).map(([k, x]) => h("tr", {}, h("td", {}, h("a", { href: x.url, rel: "noopener" }, x.nombre)), h("td", {}, { M: "mensual", T: "trimestral", A: "anual" }[x.frecuencia]),
          h("td", { class: "fijo" }, per(x.hasta).corto), h("td", { class: "fijo" }, fechaCorta(x.tomado, true)), h("td", { class: "fijo" }, per(x.proximo).corto + " · " + fechaCorta(x.esperado, true))))))),
      h("h2", {}, "Lo último que llegó"),
      h("div", { class: "caja" }, h("ul", { class: "lista" }, hechas.map((c) => h("li", {}, h("span", { class: "cuando" }, fechaCorta(c.fecha)), h("span", {}, h("strong", {}, per(c.periodo).corto + " · "), D.series[c.serie].nombre))))),
      h("p", { class: "nota" }, "Hoy es " + fechaCorta(hoy, true) + " en El Salvador."));
  }

  function paginaNoticias() {
    const st = estado.noticias;
    if (!N.ediciones.length) { poner(vista, h("h1", {}, "Resumen de noticias"), h("p", { class: "vacio" }, "Todavía no hay ediciones.")); return; }
    if (!st.edicion || (st.edicion !== "todas" && !N.ediciones.includes(st.edicion))) st.edicion = N.cerradas[N.cerradas.length - 1] || N.ediciones[N.ediciones.length - 1];
    const q = st.texto.trim().toLowerCase();
    const filas = N.notas.filter((n) => (st.edicion === "todas" || n[0] === st.edicion) && (st.categoria < 0 || n[2] === st.categoria) &&
      (!q || (n[4] + " " + n[5] + " " + n[3]).toLowerCase().includes(q))).sort((a, b) => a[2] - b[2] || (b[7] || 0) - (a[7] || 0) || (a[1] < b[1] ? 1 : -1));
    const corteH = N.hora_de_corte || 7;
    const cuerpo = filas.length ? h("div", { class: "caja desliza" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Publicada"), h("th", {}, "Categoría"), h("th", { class: "oculta-movil" }, "Fuente"), h("th", {}, "Titular y extracto"))),
      h("tbody", {}, filas.map((n) => h("tr", {}, h("td", { class: "fijo" }, fechaCorta(n[1].slice(0, 10)).split(" ").slice(1).join(" ") + " " + n[1].slice(11)), h("td", {}, h("span", { class: "chip" }, N.categorias[n[2]])), h("td", { class: "oculta-movil" }, n[3]),
        h("td", {}, h("a", { class: "titular", href: n[6], rel: "noopener" }, n[4]), n[5] ? h("span", { class: "resumen" }, n[5]) : null)))))) : h("p", { class: "vacio" }, "Ninguna nota con ese filtro.");
    const buscar = h("input", { type: "search", id: "buscar", placeholder: "Buscar en titulares", value: st.texto, "aria-label": "Buscar en titulares" });
    buscar.addEventListener("input", () => { st.texto = buscar.value; paginaNoticias(); const b = document.getElementById("buscar"); b.focus(); b.setSelectionRange(b.value.length, b.value.length); });
    poner(vista, 
      h("h1", {}, "Resumen de noticias"),
      h("p", { class: "bajada" }, "Cada mañana a las 7:15, los titulares de economía en cinco categorías. La edición de un día reúne lo publicado desde las " + corteH + ":00 del día anterior hasta las " + corteH + ":00 de ese día, hora de El Salvador. Dentro de cada categoría van primero las notas de mercados, finanzas públicas y economía, que son las que entran en el reporte diario. De cada nota hay solo titular, extracto y enlace a su medio."),
      h("div", { class: "filtros" },
        h("label", { for: "edicion" }, "Edición"),
        h("select", { id: "edicion", onchange: (ev) => { st.edicion = ev.target.value; paginaNoticias(); } },
          N.ediciones.slice().reverse().map((e) => h("option", { value: e, selected: e === st.edicion }, fechaCorta(e, true) + (N.cerradas.includes(e) ? "" : " (en curso)"))), h("option", { value: "todas", selected: st.edicion === "todas" }, "Todas las ediciones")),
        h("div", { class: "seg", role: "group", "aria-label": "Categoría" }, [["Todas", -1]].concat(N.categorias.map((c, i) => [c, i])).map(([c, i]) =>
          h("button", { type: "button", "aria-pressed": String(st.categoria === i), onclick: () => { st.categoria = i; paginaNoticias(); } }, c))),
        buscar),
      h("div", { class: "filtros" },
        h("button", { class: "boton", type: "button", onclick: () => descargar("noticias_" + st.edicion + ".csv", [["fecha_hora", "categoria", "fuente", "titular", "resumen", "url"]].concat(filas.map((n) => [n[1].replace("T", " "), N.categorias[n[2]], n[3], n[4], n[5], n[6]]))) }, "Descargar esta tabla (CSV)"),
        st.edicion !== "todas" ? h("a", { class: "boton", href: "datos/noticias/" + st.edicion + ".xlsx", download: true }, "Descargar la edición (Excel)") : null,
        h("span", { class: "cuenta" }, filas.length + (filas.length === 1 ? " nota" : " notas"))),
      cuerpo);
  }

  function paginaDatos() {
    poner(vista, 
      h("h1", {}, "Datos"),
      h("p", { class: "bajada" }, "Cada serie tal como la publica el BCR, con todas sus variables y toda su historia. El CSV es una tabla larga (una fila por variable y período); el Excel pone una columna por variable."),
      h("div", { class: "caja desliza" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Serie"), h("th", {}, "Frecuencia"), h("th", {}, "Cubre"), h("th", { class: "n" }, "Variables"), h("th", {}, "Descargar"))),
        h("tbody", {}, Object.entries(D.series).map(([k, x]) => h("tr", {}, h("td", {}, h("a", { href: x.url, rel: "noopener" }, x.nombre)), h("td", {}, { M: "mensual", T: "trimestral", A: "anual" }[x.frecuencia]),
          h("td", { class: "fijo" }, per(x.desde).corto + " – " + per(x.hasta).corto), h("td", { class: "n" }, x.variables),
          h("td", { class: "fijo" }, h("a", { href: "datos/descargas/bcr_" + k + ".csv", download: true }, "CSV"), " · ", h("a", { href: "datos/descargas/bcr_" + k + ".xlsx", download: true }, "Excel"))))))),
      h("h2", {}, "Lo que calcula EconSV"),
      h("p", { class: "bajada" }, h("a", { href: "datos/descargas/indicadores.csv", download: true }, "indicadores.csv"), " tiene cada gráfica de este sitio con todas sus vistas: nivel, variación anual y del período, suma de 12 meses o 4 trimestres, porcentaje del PIB y meses de importación. ",
        h("a", { href: "datos/descargas/indicadores_catalogo.csv", download: true }, "indicadores_catalogo.csv"), " dice qué es cada serie de esa tabla: título, unidad, frecuencia y último valor. ",
        h("a", { href: "datos/descargas/bcr_variables.csv", download: true }, "bcr_variables.csv"), " es el diccionario de las variables del BCR."),
      h("h2", {}, "En Google Sheets"),
      h("p", { class: "bajada" }, "Un script de Apps Script trae todo esto a una hoja de cálculo y la mantiene al día: una hoja mensual, una trimestral y una anual con una columna por serie, la tabla larga, el diccionario, el calendario y las noticias. ",
        h("a", { href: "https://github.com/JesusDeSivar/EconSV/tree/main/integraciones/google_sheets", rel: "noopener" }, "Cómo instalarlo"), "."),
      h("h2", {}, "Cómo se arma"),
      h("p", { class: "bajada" }, "Tres capas. Bronce guarda lo que el portal del BCR sirve, con su huella sha256. Plata lo ordena en tablas sin calcular nada, y anota cada cifra que el BCR revisa. Oro es lo que este sitio calcula. Antes de publicar, una compuerta revisa que las sumas que el propio BCR imprime cuadren y que ninguna serie tenga huecos."));
  }

  // ------------------------------------------------------------------ rutas
  function render() {
    ocultarTip();
    const [pag, ancla] = (location.hash.replace(/^#\/?/, "") || "inicio").split("/");
    const actual = PAGINAS.some((p) => p[0] === pag) ? pag : "inicio";
    document.getElementById("nav").replaceChildren(...PAGINAS.map(([k, n]) => h("a", { href: "#/" + k, "aria-current": k === actual ? "page" : false }, n)));
    const sec = D.secciones.find((x) => x.clave === actual);
    if (sec) paginaSeccion(sec, ancla);
    else if (actual === "calendario") paginaCalendario();
    else if (actual === "noticias") paginaNoticias();
    else if (actual === "datos") paginaDatos();
    else paginaInicio();
    document.title = (actual === "inicio" ? "" : PAGINAS.find((p) => p[0] === actual)[1] + " · ") + "EconSV · Signos vitales de la economía salvadoreña";
  }
  let ancho = window.innerWidth, espera;
  window.addEventListener("resize", () => { if (window.innerWidth === ancho) return; ancho = window.innerWidth; clearTimeout(espera); espera = setTimeout(() => document.querySelectorAll(".tarjeta").forEach((f) => f._pintar && f._pintar()), 150); });
  window.addEventListener("hashchange", () => { render(); if (!location.hash.split("/")[2]) window.scrollTo(0, 0); });
  window.addEventListener("scroll", ocultarTip, { passive: true });
  document.getElementById("generado").textContent = "Sitio armado el " + fechaCorta(D.generado.slice(0, 10), true) + " a las " + D.generado.slice(11) + ", hora de El Salvador.";
  render();
})();
