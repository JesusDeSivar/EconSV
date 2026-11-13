/**
 * EconSV → Google Sheets. Trae la capa oro del lago de EconSV a esta hoja de cálculo.
 *
 * Instalación (una vez): Extensiones → Apps Script, pegar este archivo completo, guardar, y recargar
 * la hoja. Aparece el menú «EconSV»; «Actualizar todo» pide permiso la primera vez.
 *
 * Qué escribe (cada hoja se reemplaza entera en cada actualización: el trabajo propio va en otras hojas):
 *
 *   Mensual, Trimestral, Anual   una fila por período y una columna por serie, lista para graficar
 *   Oro                          la tabla larga tal como está en el lago: indicador, linea, vista,
 *                                fecha, periodo, valor (para tablas dinámicas y QUERY)
 *   Diccionario                  qué es cada serie: título, unidad, frecuencia, variable del BCR,
 *                                tramo que cubre, último valor, y en qué hoja y columna está
 *   Calendario                   cuándo se espera el próximo dato de cada serie
 *   Noticias                     las últimas ediciones del resumen de noticias
 *   EconSV                       cuándo se actualizó y con qué
 *
 * De dónde: los CSV públicos de github.com/JesusDeSivar/EconSV (rama main, carpeta lago/). Las cifras
 * son del Banco Central de Reserva de El Salvador; las vistas (variaciones, sumas, % del PIB) las
 * calcula EconSV. Este script solo lee de ahí y escribe en esta hoja.
 *
 * @OnlyCurrentDoc
 */

const CONFIG = {
  ORIGEN: "https://raw.githubusercontent.com/JesusDeSivar/EconSV/main/lago/",
  DIAS_DE_NOTICIAS: 7,              // cuántas ediciones hacia atrás se traen
  HORAS_AUTOMATICAS: [8, 17],       // la actualización automática corre a estas horas (El Salvador)
  ZONA: "America/El_Salvador",
  HOJAS: { M: "Mensual", T: "Trimestral", A: "Anual", larga: "Oro", diccionario: "Diccionario",
           calendario: "Calendario", noticias: "Noticias", estado: "EconSV" },
};

const VISTAS = {
  nivel: function () { return "nivel"; },
  var_anual: function () { return "var. anual %"; },
  var_periodo: function (f) { return f === "M" ? "var. mensual %" : f === "T" ? "var. trimestral %" : "var. anual %"; },
  suma_anual: function (f) { return f === "M" ? "suma 12 meses" : "suma 4 trimestres"; },
  pct_pib: function () { return "% del PIB"; },
  meses_importacion: function () { return "meses de importación"; },
};

// ------------------------------------------------------------------ menú y órdenes

function onOpen() {
  SpreadsheetApp.getUi().createMenu("EconSV")
    .addItem("Actualizar todo", "actualizarTodo")
    .addSeparator()
    .addItem("Solo indicadores", "actualizarIndicadores")
    .addItem("Solo calendario", "actualizarCalendario")
    .addItem("Solo noticias", "actualizarNoticias")
    .addSeparator()
    .addItem("Programar actualización automática", "programarActualizacion")
    .addItem("Quitar actualización automática", "quitarActualizacion")
    .addToUi();
}

/** Trae todo. Es también lo que corre la actualización automática. */
function actualizarTodo() {
  const hecho = [], fallas = [];
  [["indicadores", actualizarIndicadores], ["calendario", actualizarCalendario], ["noticias", actualizarNoticias]]
    .forEach(function (par) {
      try { hecho.push(par[1]()); } catch (e) { fallas.push(par[0] + ": " + e.message); }
    });
  escribirEstado_(hecho, fallas);
  avisar_(fallas.length ? "EconSV: " + fallas.join(" · ") : "EconSV: " + hecho.join(" · "));
  if (fallas.length && !hecho.length) throw new Error(fallas.join(" · "));
}

/** Las hojas Mensual, Trimestral, Anual, Oro y Diccionario. */
function actualizarIndicadores() {
  const oro = traerCsv_("oro/indicadores.csv");
  if (!oro) throw new Error("no se pudo leer lago/oro/indicadores.csv");
  const catalogo = traerCsv_("oro/indicadores_catalogo.csv");      // si falta, se rotula con las claves
  const t = armarIndicadores_(oro, catalogo);
  ["M", "T", "A"].forEach(function (f) {
    if (!t.anchas[f]) return;
    escribirHoja_(CONFIG.HOJAS[f], t.anchas[f], { columnasFijas: 2, fechas: [1], texto: [2], numeros: [3, t.anchas[f][0].length - 2] });
  });
  escribirHoja_(CONFIG.HOJAS.larga, t.larga, { fechas: [4], texto: [1, 2, 3, 5], numeros: [6, 1] });
  escribirHoja_(CONFIG.HOJAS.diccionario, t.diccionario, { columnasFijas: 3, texto: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16] });
  return (t.larga.length - 1) + " cifras de " + (t.diccionario.length - 1) + " series, hasta " + t.ultimo;
}

/** La hoja Calendario: lo que falta por llegar, por fecha esperada. */
function actualizarCalendario() {
  const cal = traerCsv_("plata/calendario.csv");
  if (!cal) throw new Error("no se pudo leer lago/plata/calendario.csv");
  const filas = objetos_(cal).filter(function (r) { return r.en_lago !== "si"; })
    .sort(function (a, b) { return a.fecha_esperada < b.fecha_esperada ? -1 : a.fecha_esperada > b.fecha_esperada ? 1 : 0; })
    .map(function (r) {
      return [fechaDe_(r.fecha_esperada), r.periodo, r.nombre, r.serie,
              r.origen === "bcr" ? "anunciada por el BCR" : "estimada"];
    });
  escribirHoja_(CONFIG.HOJAS.calendario, [["Se espera", "Período", "Qué se publica", "Serie", "Fecha"]].concat(filas),
    { fechas: [1], texto: [2, 3, 4, 5] });
  return filas.length + " publicaciones por venir";
}

/** La hoja Noticias: las ediciones de los últimos días, la más nueva arriba. */
function actualizarNoticias() {
  const filas = [];
  let ediciones = 0, ultima = "";
  const hoy = hoy_();
  for (let d = 0; d <= CONFIG.DIAS_DE_NOTICIAS; d++) {
    const dia = Utilities.formatDate(new Date(hoy.getTime() - d * 864e5), CONFIG.ZONA, "yyyy-MM-dd");
    const csv = traerCsv_("oro/noticias/" + dia + ".csv");
    if (!csv) continue;
    ediciones++;
    if (!ultima) ultima = dia;
    objetos_(csv).forEach(function (r) {
      filas.push([dia, r.fecha_hora.replace("T", " "), r.categoria, r.fuente, r.titular, r.resumen, r.url]);
    });
  }
  if (!ediciones) throw new Error("no hay ediciones de noticias en los últimos " + CONFIG.DIAS_DE_NOTICIAS + " días");
  escribirHoja_(CONFIG.HOJAS.noticias,
    [["Edición", "Publicada", "Categoría", "Fuente", "Titular", "Resumen", "Enlace"]].concat(filas),
    { texto: [1, 2, 3, 4, 5, 6, 7] });
  return filas.length + " notas en " + ediciones + " ediciones, la última del " + ultima;
}

/** Crea los disparadores diarios (y quita los que hubiera, para no duplicar). */
function programarActualizacion() {
  quitarActualizacion_();
  CONFIG.HORAS_AUTOMATICAS.forEach(function (h) {
    ScriptApp.newTrigger("actualizarTodo").timeBased().everyDays(1).atHour(h).inTimezone(CONFIG.ZONA).create();
  });
  avisar_("EconSV se actualizará sola todos los días, entre las " +
    CONFIG.HORAS_AUTOMATICAS.map(function (h) { return h + ":00 y las " + (h + 1) + ":00"; }).join(" y entre las ") +
    ", hora de El Salvador.");
}

function quitarActualizacion() {
  const n = quitarActualizacion_();
  avisar_(n ? "Actualización automática quitada." : "No había actualización automática programada.");
}

function quitarActualizacion_() {
  let n = 0;
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "actualizarTodo") { ScriptApp.deleteTrigger(t); n++; }
  });
  return n;
}

// ------------------------------------------------------------------ armar las tablas (sin tocar la hoja)

/**
 * De la tabla larga de oro (y su catálogo, si está) a lo que va en cada hoja.
 * `oro` y `catalogo` son matrices como las da Utilities.parseCsv, con su fila de encabezado.
 */
function armarIndicadores_(oro, catalogo) {
  const filas = objetos_(oro);
  const clave = function (r) { return r.indicador + "|" + r.linea + "|" + r.vista; };

  // el catálogo, o uno mínimo armado con lo que trae la propia tabla
  let series;
  if (catalogo) {
    series = objetos_(catalogo);
  } else {
    const vistas = {};
    filas.forEach(function (r) {
      const k = clave(r);
      if (!vistas[k]) vistas[k] = { indicador: r.indicador, linea: r.linea, vista: r.vista, seccion: "", titulo: r.indicador,
        frecuencia: frecuenciaDe_(r.periodo), unidad: "", naturaleza: "", tipo: "", serie_bcr: "", variable_id: "",
        desde: r.periodo, hasta: r.periodo, ultimo_valor: r.valor, nota: "" };
      vistas[k].hasta = r.periodo; vistas[k].ultimo_valor = r.valor;
    });
    series = Object.keys(vistas).map(function (k) { return vistas[k]; });
  }
  const lineasPor = {};
  series.forEach(function (s) { (lineasPor[s.indicador] = lineasPor[s.indicador] || {})[s.linea] = true; });
  series.forEach(function (s) {
    const varias = Object.keys(lineasPor[s.indicador]).length > 1;
    const vista = (VISTAS[s.vista] || function () { return s.vista; })(s.frecuencia);
    s.encabezado = s.titulo + (varias ? " · " + s.linea : "") + " · " + vista;
  });

  // la tabla larga, con fecha y valor como fecha y número
  const larga = [["indicador", "linea", "vista", "fecha", "periodo", "valor"]].concat(filas.map(function (r) {
    return [r.indicador, r.linea, r.vista, fechaDe_(r.fecha), r.periodo, Number(r.valor)];
  }));

  // las tres hojas anchas: una columna por serie de esa frecuencia, en el orden del catálogo
  const valores = {};
  filas.forEach(function (r) { (valores[clave(r)] = valores[clave(r)] || {})[r.periodo] = [r.fecha, Number(r.valor)]; });
  const anchas = {}, lugar = {};
  let ultimo = "";
  ["M", "T", "A"].forEach(function (f) {
    const cols = series.filter(function (s) { return s.frecuencia === f && valores[clave(s)]; });
    if (!cols.length) return;
    const periodos = {};
    cols.forEach(function (s) {
      const v = valores[clave(s)];
      Object.keys(v).forEach(function (p) { periodos[p] = v[p][0]; });
    });
    const orden = Object.keys(periodos).sort(function (a, b) { return periodos[a] < periodos[b] ? -1 : periodos[a] > periodos[b] ? 1 : 0; });
    const tabla = [["Fecha", "Período"].concat(cols.map(function (s) { return s.encabezado; }))];
    orden.forEach(function (p) {
      tabla.push([fechaDe_(periodos[p]), p].concat(cols.map(function (s) {
        const x = valores[clave(s)][p];
        return x ? x[1] : "";
      })));
    });
    cols.forEach(function (s, i) { lugar[clave(s)] = [CONFIG.HOJAS[f], letra_(i + 3)]; });
    anchas[f] = tabla;
    if (f === "M") ultimo = orden[orden.length - 1];
  });

  const diccionario = [["Hoja", "Columna", "Encabezado", "Indicador", "Línea", "Vista", "Sección", "Frecuencia", "Unidad",
    "Naturaleza", "Serie del BCR", "Variable del BCR", "Desde", "Hasta", "Último valor", "Nota"]].concat(series.map(function (s) {
    const l = lugar[clave(s)] || ["", ""];
    return [l[0], l[1], s.encabezado, s.indicador, s.linea, s.vista, s.seccion,
      { M: "mensual", T: "trimestral", A: "anual" }[s.frecuencia] || s.frecuencia, s.unidad, s.naturaleza, s.serie_bcr,
      s.variable_id === "" ? "" : Number(s.variable_id), s.desde, s.hasta, s.ultimo_valor === "" ? "" : Number(s.ultimo_valor), s.nota];
  }));
  return { larga: larga, anchas: anchas, diccionario: diccionario, ultimo: ultimo || (filas.length ? filas[filas.length - 1].periodo : "") };
}

/** Matriz con encabezado → objetos. */
function objetos_(matriz) {
  const cab = matriz[0];
  return matriz.slice(1).filter(function (f) { return f.length === cab.length; }).map(function (f) {
    const o = {};
    cab.forEach(function (c, i) { o[c] = f[i]; });
    return o;
  });
}

function frecuenciaDe_(periodo) {
  return /^\d{4}$/.test(periodo) ? "A" : /-T\d$/.test(periodo) ? "T" : "M";
}

/** «2026-10-01» → fecha a mediodía, para que ningún huso horario la corra de día. */
function fechaDe_(iso) {
  const p = String(iso).split("-");
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2] || 1), 12, 0, 0);
}

/** 1 → A, 27 → AA. */
function letra_(n) {
  let s = "";
  while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); }
  return s;
}

function hoy_() { return new Date(); }

// ------------------------------------------------------------------ leer del lago y escribir en la hoja

/** Un CSV del lago como matriz; null si no existe (404). Cualquier otra respuesta es un error. */
function traerCsv_(ruta) {
  const r = UrlFetchApp.fetch(CONFIG.ORIGEN + ruta, { muteHttpExceptions: true });
  const codigo = r.getResponseCode();
  if (codigo === 404) return null;
  if (codigo !== 200) throw new Error("lago/" + ruta + " respondió HTTP " + codigo);
  const texto = r.getContentText("UTF-8").replace(/^﻿/, "");
  const m = Utilities.parseCsv(texto);
  return m && m.length > 1 ? m : null;
}

/**
 * Reemplaza el contenido de una hoja (la crea si no existe).
 * opciones: columnasFijas; fechas: [columna, ...]; numeros: [primera columna, cuántas]; texto: [columna, ...]
 *
 * Las columnas de texto se ponen en formato «texto sin formato» ANTES de escribir. Así Sheets no
 * convierte «2026-10» en una fecha, y un titular que empiece con «=», «+» o «-» queda como texto y
 * nunca se evalúa como fórmula: lo que viene de fuera se escribe, no se ejecuta.
 */
function escribirHoja_(nombre, filas, opciones) {
  opciones = opciones || {};
  const libro = SpreadsheetApp.getActiveSpreadsheet();
  const hoja = libro.getSheetByName(nombre) || libro.insertSheet(nombre);
  const nf = filas.length, nc = filas[0].length;
  hoja.clearContents();
  if (hoja.getMaxRows() < nf) hoja.insertRowsAfter(hoja.getMaxRows(), nf - hoja.getMaxRows());
  if (hoja.getMaxColumns() < nc) hoja.insertColumnsAfter(hoja.getMaxColumns(), nc - hoja.getMaxColumns());
  hoja.getRange(1, 1, nf, nc).setNumberFormat("General");
  (opciones.texto || []).forEach(function (c) { hoja.getRange(1, c, nf, 1).setNumberFormat("@"); });
  hoja.getRange(1, 1, nf, nc).setValues(filas);
  hoja.getRange(1, 1, 1, nc).setFontWeight("bold").setWrap(true).setVerticalAlignment("middle");
  hoja.setFrozenRows(1);
  if (opciones.columnasFijas) hoja.setFrozenColumns(opciones.columnasFijas);
  if (nf > 1) {
    (opciones.fechas || []).forEach(function (c) { hoja.getRange(2, c, nf - 1, 1).setNumberFormat("yyyy-mm-dd"); });
    if (opciones.numeros && opciones.numeros[1] > 0) {
      hoja.getRange(2, opciones.numeros[0], nf - 1, opciones.numeros[1]).setNumberFormat("#,##0.00");
    }
  }
  return hoja;
}

function escribirEstado_(hecho, fallas) {
  const ahora = Utilities.formatDate(new Date(), CONFIG.ZONA, "yyyy-MM-dd HH:mm");
  const filas = [
    ["EconSV · signos vitales de la economía salvadoreña", ""],
    ["Última actualización", ahora + " (hora de El Salvador)"],
  ];
  hecho.forEach(function (h) { filas.push(["Llegó", h]); });
  fallas.forEach(function (f) { filas.push(["No llegó", f]); });
  filas.push(["Origen", CONFIG.ORIGEN]);
  filas.push(["Fuente de las cifras", "Banco Central de Reserva de El Salvador (estadisticas.bcr.gob.sv). Las variaciones, sumas y porcentajes del PIB los calcula EconSV."]);
  filas.push(["Cómo usar", "Las hojas Mensual, Trimestral, Anual, Oro, Diccionario, Calendario y Noticias se reemplazan enteras en cada actualización. El trabajo propio va en otras hojas, con referencias a estas."]);
  filas.push(["Ejemplo", "En una celda de otra hoja:   =QUERY(Oro!A:F; \"select D, F where A = 'remesas' and C = 'suma_anual' order by D\"; 0)   (con coma en vez de punto y coma si la hoja está en inglés)"]);
  const hoja = escribirHoja_(CONFIG.HOJAS.estado, filas, { texto: [1, 2] });
  hoja.setColumnWidth(1, 190);
  hoja.setColumnWidth(2, 760);
}

/** Un aviso en la esquina de la hoja; en una corrida automática no hay a quién avisar. */
function avisar_(texto) {
  try { SpreadsheetApp.getActiveSpreadsheet().toast(texto, "EconSV", 8); } catch (e) { /* sin interfaz */ }
}
