#!/usr/bin/env node
/* Corre integraciones/google_sheets/EconSV.gs fuera de Google, con el lago que está en el repositorio.
 *
 *     node pruebas/prueba_sheets.js
 *
 * Apps Script no se puede ejecutar aquí, así que SpreadsheetApp, UrlFetchApp, Utilities y ScriptApp
 * son dobles mínimos. El doble de la hoja es estricto donde Sheets lo es o donde un descuido haría
 * daño: setValues exige una matriz rectangular del tamaño del rango, sin undefined ni NaN, y toda
 * cadena que Sheets convertiría sola (una fecha como «2026-10», un número, algo que empieza con
 * «=», «+», «-» o «@») tiene que caer en una columna puesta antes en formato de texto.
 * Lo que esto NO prueba es Google: permisos, cuotas y el aspecto final en la hoja.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const RAIZ = path.join(__dirname, "..");
const FUENTE = fs.readFileSync(path.join(RAIZ, "integraciones", "google_sheets", "EconSV.gs"), "utf8");

function parseCsv(texto) {
  const filas = [];
  let fila = [], celda = "", comillas = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (comillas) {
      if (c === '"' && texto[i + 1] === '"') { celda += '"'; i++; } else if (c === '"') comillas = false; else celda += c;
    } else if (c === '"') comillas = true;
    else if (c === ",") { fila.push(celda); celda = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && texto[i + 1] === "\n") i++;
      fila.push(celda); filas.push(fila); fila = []; celda = "";
    } else celda += c;
  }
  if (celda !== "" || fila.length) { fila.push(celda); filas.push(fila); }
  return filas;
}

function entorno(opciones) {
  opciones = opciones || {};
  const hojas = {}, disparadores = [], avisos = [], pedidos = [];
  const RIESGO = /^[=+\-@]|^\d{4}-\d{1,2}(-\d{1,2})?([ T]\d{1,2}:\d{2})?$|^-?\d+([.,]\d+)?$/;

  function Hoja(nombre) {
    const h = { nombre: nombre, valores: [], filas: 1000, columnas: 26, texto: {}, formatos: [], fijas: [0, 0] };
    h.clearContents = () => { h.valores = []; };
    h.getMaxRows = () => h.filas;
    h.getMaxColumns = () => h.columnas;
    h.insertRowsAfter = (_, n) => { h.filas += n; };
    h.insertColumnsAfter = (_, n) => { h.columnas += n; };
    h.setFrozenRows = (n) => { h.fijas[0] = n; };
    h.setFrozenColumns = (n) => { h.fijas[1] = n; };
    h.setColumnWidth = () => h;
    h.getRange = (f, c, nf, nc) => {
      assert(f >= 1 && c >= 1 && nf >= 1 && nc >= 1, `${nombre}: rango vacío o fuera de la hoja (${f},${c},${nf},${nc})`);
      assert(f + nf - 1 <= h.filas && c + nc - 1 <= h.columnas, `${nombre}: el rango se sale de la hoja`);
      const r = {
        setNumberFormat: (fmt) => {
          h.formatos.push([f, c, nf, nc, fmt]);
          for (let j = c; j < c + nc; j++) { if (fmt === "@") h.texto[j] = [f, f + nf - 1]; else if (f === 1) delete h.texto[j]; }
          return r;
        },
        setFontWeight: () => r, setWrap: () => r, setVerticalAlignment: () => r,
        setValues: (m) => {
          assert.strictEqual(m.length, nf, `${nombre}: setValues con ${m.length} filas en un rango de ${nf}`);
          m.forEach((fila, i) => {
            assert.strictEqual(fila.length, nc, `${nombre}: la fila ${i + 1} tiene ${fila.length} celdas y el rango ${nc}`);
            fila.forEach((v, j) => {
              const donde = `${nombre}!${j + c}:${i + f}`;
              assert(v !== undefined && v !== null, `${donde}: celda sin valor`);
              if (typeof v === "number") assert(Number.isFinite(v), `${donde}: número no finito`);
              else if (v instanceof Date || (v && typeof v.getTime === "function")) assert(!isNaN(v.getTime()), `${donde}: fecha inválida`);
              else {
                assert.strictEqual(typeof v, "string", `${donde}: tipo ${typeof v}`);
                const t = h.texto[j + c];
                if (RIESGO.test(v)) assert(t && t[0] <= i + f && i + f <= t[1], `${donde}: «${v.slice(0, 40)}» se escribiría en una columna que Sheets interpreta`);
              }
            });
          });
          h.valores = m;
          return r;
        },
      };
      return r;
    };
    return h;
  }
  const libro = {
    getSheetByName: (n) => hojas[n] || null,
    insertSheet: (n) => (hojas[n] = Hoja(n)),
    toast: (t) => avisos.push(t),
  };
  const ctx = {
    console: console,
    SpreadsheetApp: {
      getActiveSpreadsheet: () => libro,
      getUi: () => { const m = { items: [], createMenu: () => m, addItem: (t, f) => { m.items.push(f); return m; }, addSeparator: () => m, addToUi: () => { ctx.menu = m.items; } }; return m; },
    },
    UrlFetchApp: {
      fetch: (url) => {
        pedidos.push(url);
        const ruta = url.replace("https://raw.githubusercontent.com/JesusDeSivar/EconSV/main/lago/", "");
        assert(ruta !== url, "pedido fuera del lago: " + url);
        if (opciones.codigo && opciones.codigo[ruta]) return { getResponseCode: () => opciones.codigo[ruta], getContentText: () => "" };
        if (opciones.contenido && ruta in opciones.contenido) return { getResponseCode: () => 200, getContentText: () => opciones.contenido[ruta] };
        const p = path.join(RAIZ, "lago", ruta);
        if (!fs.existsSync(p)) return { getResponseCode: () => 404, getContentText: () => "404: Not Found" };
        return { getResponseCode: () => 200, getContentText: () => fs.readFileSync(p, "utf8") };
      },
    },
    Utilities: {
      parseCsv: parseCsv,
      formatDate: (d, zona, fmt) => {
        const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: zona, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(d).map((x) => [x.type, x.value]));
        return fmt.replace("yyyy", p.year).replace("MM", p.month).replace("dd", p.day).replace("HH", p.hour).replace("mm", p.minute);
      },
    },
    ScriptApp: {
      newTrigger: (f) => { const t = { f: f, getHandlerFunction: () => f }; const b = { timeBased: () => b, everyDays: () => b, atHour: (h) => { t.hora = h; return b; }, inTimezone: (z) => { t.zona = z; return b; }, create: () => { disparadores.push(t); return t; } }; return b; },
      getProjectTriggers: () => disparadores.slice(),
      deleteTrigger: (t) => { disparadores.splice(disparadores.indexOf(t), 1); },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(FUENTE, ctx, { filename: "EconSV.gs" });
  // «hoy» es el día de la última edición de noticias que hay en el lago, para que la prueba no envejezca
  const ediciones = fs.readdirSync(path.join(RAIZ, "lago", "oro", "noticias")).filter((f) => f.endsWith(".csv")).sort();
  const ultima = ediciones[ediciones.length - 1].slice(0, 10);
  vm.runInContext(`hoy_ = function () { return new Date("${ultima}T18:00:00Z"); };`, ctx);
  return { ctx: ctx, hojas: hojas, disparadores: disparadores, avisos: avisos, pedidos: pedidos, ultimaEdicion: ultima, ediciones: ediciones };
}

const leer = (ruta) => parseCsv(fs.readFileSync(path.join(RAIZ, "lago", ruta), "utf8")).filter((f) => f.length > 1);
let n = 0;
function prueba(nombre, f) { f(); n++; console.log("  ok    " + nombre); }

// ------------------------------------------------------------------ todo, con el lago del repositorio
const e = entorno();
e.ctx.actualizarTodo();
const oro = leer("oro/indicadores.csv"), cat = leer("oro/indicadores_catalogo.csv");

prueba("crea las ocho hojas", () => {
  assert.deepStrictEqual(Object.keys(e.hojas).sort(), ["Anual", "Calendario", "Diccionario", "EconSV", "Mensual", "Noticias", "Oro", "Trimestral"]);
});

prueba("Oro es la tabla del lago, con fecha y número", () => {
  const h = e.hojas.Oro.valores;
  assert.strictEqual(h.length, oro.length);
  assert.deepStrictEqual(Array.from(h[0]), oro[0]);
  const i = oro.findIndex((f) => f[0] === "reservas" && f[2] === "nivel" && f[4] === "2026-10");
  assert(i > 0, "el lago ya no tiene reservas de 2026-10");
  assert.strictEqual(h[i][5], Number(oro[i][5]));
  assert.strictEqual(h[i][5], 4818.22);
  assert.strictEqual(h[i][3].getFullYear() + "-" + (h[i][3].getMonth() + 1) + "-" + h[i][3].getDate(), "2026-10-1");
  assert.strictEqual(h[i][3].getHours(), 12);
});

prueba("cada serie del catálogo tiene su columna en la hoja de su frecuencia", () => {
  const nombres = { M: "Mensual", T: "Trimestral", A: "Anual" };
  for (const f of ["M", "T", "A"]) {
    const series = cat.slice(1).filter((s) => s[5] === f), h = e.hojas[nombres[f]].valores;
    assert.strictEqual(h[0].length, series.length + 2, nombres[f]);
    assert.strictEqual(new Set(h[0]).size, h[0].length, nombres[f] + ": encabezados repetidos");
    const periodos = h.slice(1).map((x) => x[1]);
    assert.deepStrictEqual(periodos, periodos.slice().sort(), nombres[f] + ": períodos fuera de orden");
    // el último valor de cada columna es el que dice el catálogo, en el período que dice
    series.forEach((s, j) => {
      const fila = h.find((x) => x[1] === s[12]);
      assert(fila, `${nombres[f]}: falta el período ${s[12]}`);
      assert.strictEqual(fila[j + 2], Number(s[13]), `${nombres[f]} · ${h[0][j + 2]}`);
    });
  }
});

prueba("los encabezados dicen qué es cada columna", () => {
  const m = Array.from(e.hojas.Mensual.valores[0]), t = Array.from(e.hojas.Trimestral.valores[0]);
  assert(m.includes("Remesas familiares · suma 12 meses"));
  assert(m.includes("Inflación al consumidor · IPC general · var. anual %"));
  assert(m.includes("Reservas internacionales netas · meses de importación"));
  assert(t.includes("Remesas familiares · % del PIB"), "el % del PIB de una serie mensual va en la hoja trimestral");
  assert(t.includes("Inversión extranjera directa · suma 4 trimestres"));
});

prueba("el Diccionario dice dónde está cada serie", () => {
  const d = e.hojas.Diccionario.valores;
  assert.strictEqual(d.length, cat.length);
  const fila = d.find((x) => x[3] === "remesas" && x[5] === "suma_anual");
  const hoja = e.hojas[fila[0]].valores, col = hoja[0].indexOf(fila[2]);
  assert.strictEqual(e.ctx.letra_(col + 1), fila[1]);
  assert.strictEqual(hoja.find((x) => x[1] === fila[13])[col], fila[14]);     // en su último período, no en la última fila
  assert.strictEqual(e.ctx.letra_(1) + e.ctx.letra_(26) + e.ctx.letra_(27) + e.ctx.letra_(53), "AZAABA");
});

prueba("Calendario y Noticias", () => {
  const c = e.hojas.Calendario.valores, nt = e.hojas.Noticias.valores;
  assert(c.length > 5 && typeof c[1][0].getTime === "function", "el calendario no trae fechas");   // las fechas son de otro contexto: instanceof no sirve
  for (let i = 2; i < c.length; i++) assert(c[i - 1][0].getTime() <= c[i][0].getTime(), "calendario fuera de orden");
  const esperadas = e.ediciones.slice(-8).reduce((s, f) => s + leer("oro/noticias/" + f).length - 1, 0);
  assert.strictEqual(nt.length - 1, esperadas);
  assert.strictEqual(nt[1][0], e.ultimaEdicion, "la edición más nueva va arriba");
  assert(nt.slice(1).every((x) => /^https?:\/\//.test(x[6])), "una nota sin enlace");
});

prueba("la hoja de estado y el aviso", () => {
  const s = e.hojas.EconSV.valores.map((x) => x.join(" | ")).join("\n");
  assert(/Llegó \| \d+ cifras de 115 series/.test(s), s);
  assert(!/No llegó/.test(s), s);
  assert.strictEqual(e.avisos.length, 1);
  assert(e.pedidos.every((u) => u.startsWith("https://raw.githubusercontent.com/JesusDeSivar/EconSV/main/lago/")));
});

prueba("volver a correr deja lo mismo", () => {
  const antes = JSON.stringify(e.hojas.Mensual.valores);
  e.ctx.actualizarIndicadores();
  assert.strictEqual(JSON.stringify(e.hojas.Mensual.valores), antes);
});

// ------------------------------------------------------------------ lo que puede salir mal
prueba("sin catálogo, rotula con las claves y no se cae", () => {
  const x = entorno({ codigo: { "oro/indicadores_catalogo.csv": 404 } });
  x.ctx.actualizarIndicadores();
  assert(Array.from(x.hojas.Mensual.valores[0]).includes("remesas · suma 12 meses"));
  assert.strictEqual(x.hojas.Diccionario.valores.length, cat.length);
});

prueba("si el lago no responde, lo dice y no borra nada", () => {
  const x = entorno({ codigo: { "oro/indicadores.csv": 500 } });
  assert.throws(() => x.ctx.actualizarIndicadores(), /HTTP 500/);
  assert.strictEqual(Object.keys(x.hojas).length, 0);
  x.ctx.actualizarTodo();                      // lo demás sí llega, y la falla queda anotada
  assert(x.hojas.EconSV.valores.some((f) => f[0] === "No llegó" && /indicadores/.test(f[1])));
  assert(x.hojas.Noticias && x.hojas.Calendario && !x.hojas.Oro);
});

prueba("un titular que parece fórmula se escribe como texto", () => {
  const dia = entorno().ultimaEdicion;
  const x = entorno({ contenido: { ["oro/noticias/" + dia + ".csv"]:
    'fecha_hora,categoria,fuente,titular,resumen,url,puntaje\n2026-11-12T06:45,El Salvador – Fiscales,=HYPERLINK("http://x";"y"),"=IMPORTXML(""http://x"";""//a"")",+503 2222-0000,https://ejemplo.org/a,7\n' } });
  x.ctx.actualizarNoticias();                  // el doble de la hoja falla si esa cadena cae en una columna que no es de texto
  const fila = x.hojas.Noticias.valores.find((f) => f[4].startsWith("=IMPORTXML"));
  assert(fila && fila[5] === "+503 2222-0000" && fila[7] === 7);
  assert.deepStrictEqual(Object.keys(x.hojas.Noticias.texto).map(Number), [1, 2, 3, 4, 5, 6, 7]);
});

prueba("programar y quitar la actualización automática", () => {
  const x = entorno();
  x.ctx.programarActualizacion();
  x.ctx.programarActualizacion();              // dos veces no duplica
  assert.deepStrictEqual(x.disparadores.map((t) => [t.f, t.hora, t.zona]), [["actualizarTodo", 8, "America/El_Salvador"], ["actualizarTodo", 17, "America/El_Salvador"]]);
  x.ctx.quitarActualizacion();
  assert.strictEqual(x.disparadores.length, 0);
  x.ctx.onOpen();
  x.ctx.menu.forEach((f) => assert.strictEqual(typeof x.ctx[f], "function", "el menú llama a «" + f + "», que no existe"));
});

console.log(`\n${n} de ${n} pruebas de la integración con Google Sheets pasan`);
