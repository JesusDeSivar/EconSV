"""El reparto de las noticias en categorías y la limpieza de cada nota, sin red."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tuberias"))
import noticias  # noqa: E402

EUA, LATAM, RESTO = "Internacional – EUA", "Internacional – LATAM", "Internacional – Resto del mundo"
NAC, FIS = "El Salvador – Nacionales", "El Salvador – Fiscales"


class Reparto(unittest.TestCase):
    def test_lo_que_menciona_el_salvador_es_salvadoreno_venga_de_donde_venga(self):
        self.assertEqual(noticias.clasificar("El FMI aprueba un desembolso para El Salvador", RESTO), FIS)
        self.assertEqual(noticias.clasificar("Turistas salvadoreños llenan las playas", LATAM), NAC)

    def test_fiscal_por_palabras(self):
        self.assertEqual(noticias.clasificar("Hacienda reporta alza en la recaudación de IVA", NAC), FIS)
        self.assertEqual(noticias.clasificar("Inauguran centro comercial en Santa Tecla", NAC), NAC)

    def test_la_fiscalia_no_es_fiscal(self):
        self.assertEqual(noticias.clasificar("La Fiscalía de El Salvador presenta acusación", NAC), NAC)

    def test_regiones(self):
        self.assertEqual(noticias.clasificar("La Reserva Federal mantiene las tasas", RESTO), EUA)
        self.assertEqual(noticias.clasificar("México y Brasil negocian un acuerdo comercial", RESTO), LATAM)
        self.assertEqual(noticias.clasificar("El BCE baja los tipos de interés en la eurozona", LATAM), RESTO)

    def test_sin_palabras_de_region_vale_la_fuente(self):
        self.assertEqual(noticias.clasificar("Los mercados cierran al alza", EUA), EUA)
        self.assertEqual(noticias.clasificar("Los mercados cierran al alza", LATAM), LATAM)

    def test_empate_de_regiones_lo_decide_la_fuente(self):
        t = "Estados Unidos impone aranceles a México"
        self.assertEqual(noticias.clasificar(t, LATAM), LATAM)
        self.assertEqual(noticias.clasificar(t, EUA), EUA)

    def test_un_diario_salvadoreno_con_nota_extranjera(self):
        self.assertEqual(noticias.clasificar("China anuncia estímulos a su economía", NAC), RESTO)

    def test_tildes_y_mayusculas_no_importan(self):
        self.assertTrue(noticias.menciona_sv("EL SALVADOR crece"))
        self.assertTrue(noticias.menciona_sv("la economía salvadoreña"))
        self.assertFalse(noticias.menciona_sv("el salvadorismo"))


class Gusto(unittest.TestCase):
    """El puntaje ordena, dentro de una categoría, lo que más se parece al reporte diario."""

    def nota(self, categoria, titular, resumen="", fuente="Otra"):
        return {"categoria": categoria, "titular": titular, "resumen": resumen, "fuente": fuente}

    def test_lo_fiscal_de_el_mundo_va_primero(self):
        a = noticias.puntaje(self.nota(FIS, "Ministro de Defensa pide presupuesto de $314.5 millones para el año 2027", fuente="Diario El Mundo"))
        b = noticias.puntaje(self.nota(FIS, "Salinas Pliego dice que bitcoin es el mejor dinero"))
        self.assertGreater(a, b + 5)

    def test_la_inversion_publica_es_fiscal_y_va_arriba(self):
        """Lo que pidió el dueño: no solo BCIE y BID, cualquier proyecto de inversión pública."""
        casos = ["CAF aprueba crédito para ampliar la carretera al puerto de La Libertad",
                 "KfW financiará el saneamiento del lago de Ilopango con cooperación alemana",
                 "El Banco Mundial desembolsa fondos para escuelas",
                 "FOVIAL inicia la reparación de 40 kilómetros de la Panamericana",
                 "La DOM entrega un mercado municipal en Usulután",
                 "MOP adjudica el diseño del viaducto de Los Chorros",
                 "Cooperación italiana financia rescate habitacional en el Centro Histórico",
                 "JICA y el MOP firman convenio para un puente en San Miguel"]
        comun = noticias.puntaje(self.nota(FIS, "Diputados discuten una reforma al reglamento interno"))
        for t in casos:
            self.assertEqual(noticias.clasificar(t, NAC), FIS, t)
            self.assertTrue(noticias.cumple("fiscales", t), t)
            self.assertGreaterEqual(noticias.puntaje(self.nota(FIS, t)), comun + 3, t)
        self.assertEqual(noticias.clasificar("Abren un nuevo centro comercial en Santa Tecla", NAC), NAC)

    def test_el_titular_pesa_el_doble_que_el_extracto(self):
        t = noticias.puntaje(self.nota(EUA, "La Fed sube las tasas"))
        r = noticias.puntaje(self.nota(EUA, "Una decisión esperada", "La Fed sube las tasas"))
        self.assertEqual(t, 2 * r)

    def test_una_nota_de_servicio_baja(self):
        noticia = noticias.puntaje(self.nota(NAC, "La inflación repunta a 3.91 % en octubre"))
        servicio = noticias.puntaje(self.nota(NAC, "¿Cómo afecta la inflación a tu bolsillo?"))
        self.assertGreater(noticia, servicio)
        self.assertLess(noticias.puntaje(self.nota(EUA, "Requisitos para tramitar la visa de trabajo")), 0)

    def test_cada_categoria_tiene_sus_listas(self):
        for cat, g in noticias.cfg()["gusto"].items():
            self.assertIn(cat, noticias.CATEGORIAS)
            self.assertIn(g["prefiere"], noticias.cfg()["palabras"])
            self.assertIn(g["evita"], noticias.cfg()["palabras"])
        self.assertEqual(set(noticias.cfg()["gusto"]), set(noticias.CATEGORIAS))


class Fiscales(unittest.TestCase):
    """Qué nota salvadoreña es «Fiscales»: la regla `fiscales` del catálogo, no la sección de donde vino."""

    def test_lo_que_el_dueno_pone_en_fiscales_entra(self):
        """Titulares de la sección Fiscales de sus reportes del 10 y el 11 de noviembre de 2026."""
        for t in ["Ministro de Defensa pide presupuesto de $314.5 millones para el año 2027",
                  "TSE adjudica a CGTS la auditoría del voto electrónico de salvadoreños en el extranjero",
                  "Gobierno pide ratificar préstamo del BID por $50 millones para censo económico",
                  "BCIE aprueba $1.72 millones para financiar un programa de becas en El Salvador",
                  "BCIE aprueba $500,000 para mitigar el impacto de El Niño en la agricultura salvadoreña",
                  "Asamblea ratifica acuerdo de El Salvador y Argentina que promete protección del patrimonio de las inversiones",
                  "Aprobado acuerdo de exención mutua visas a funcionarios de El Salvador y Kuwait"]:
            self.assertTrue(noticias.cumple("fiscales", t), t)
            self.assertEqual(noticias.clasificar(t, NAC), FIS, t)

    def test_un_actor_publico_con_dinero_entra(self):
        for t in ["Ministerio de Trabajo da ultimátum a alcaldía por salarios atrasados",
                  "Alcaldía de Santa Tecla pagó $481,000 por el carnaval",
                  "Diputados recortan fondos al deporte",
                  "Gobierno recibe donación de Japón para equipar hospitales",
                  "Corte de Cuentas audita contratos del hospital Rosales"]:
            self.assertTrue(noticias.cumple("fiscales", t), t)

    def test_una_palabra_suelta_no_basta(self):
        """Lo que la primera corrida en GitHub (2026-11-13) dejó entrar en Fiscales por una sola palabra."""
        for t in ["Muere perrita rescatada por alcaldía y anuncian seguimiento al caso",
                  "DoctorSV registra 5.4 millones de consultas en su primer año de funcionamiento",
                  "VMT anuncia cierre de tramo en la carretera Litoral por 9 horas. De acuerdo con el ministerio, es por obras",
                  "Gustavo Acevedo inscribe su candidatura en busca de su tercer periodo como alcalde de Santa Ana",
                  "Prevén altas temperaturas y déficit de lluvias en 2027",
                  "Bukele responde a Amnistía tras exigir revelar acuerdo sobre operaciones en Haití",
                  "3,412 personas recibieron este año aparatos auditivos del Ministerio de Salud",
                  "Súper Selectos y Nivea entregaron donativo a Fundación Ayúdame a Vivir",
                  "Corte de Cuentas extiende plazo para que candidatos soliciten constancias"]:
            self.assertFalse(noticias.cumple("fiscales", t), t)
            self.assertEqual(noticias.clasificar(t, FIS), NAC, t)

    def test_la_seccion_no_hace_fiscal_a_una_nota(self):
        t = "Salinas Pliego dice en El Salvador que bitcoin es el mejor dinero"
        self.assertEqual(noticias.clasificar(t, FIS), NAC)

    def test_un_monto_en_dolares_es_dinero(self):
        self.assertEqual(noticias.cuenta("dinero", "destina $350,000 y otros US$ 2 millones"), 2)
        self.assertEqual(noticias.cuenta("dinero", "costó 5 mil dólares"), 1)
        self.assertEqual(noticias.cuenta("dinero", "5.4 millones de consultas"), 0)

    def test_exigir_varias_cosas_es_exigirlas_todas(self):
        self.assertTrue(noticias.cumple(["el_salvador", "fiscales"], "El Salvador coloca bonos por $500 millones"))
        self.assertFalse(noticias.cumple(["el_salvador", "fiscales"], "Honduras coloca bonos por $500 millones"))
        self.assertFalse(noticias.cumple(["el_salvador", "fiscales"], "El Salvador gana en el fútbol playa"))


class AlDia(unittest.TestCase):
    """Lo ya guardado se vuelve a pasar por el catálogo de hoy."""

    def nota(self, url, titular, categoria, fuente="Diario El Mundo", resumen=""):
        return {"id": url[-6:], "url": url, "titular": titular, "resumen": resumen, "categoria": categoria,
                "fuente": fuente}

    def test_se_va_lo_que_su_seccion_ya_no_admite_y_lo_demas_se_reparte_de_nuevo(self):
        perrita = "Muere perrita rescatada por alcaldía y anuncian seguimiento al caso"
        notas = [
            self.nota("https://diario.elmundo.sv/nacionales/perrita", perrita, FIS),
            self.nota("https://www.eldiariodehoy.com/noticias/nacionales/perrita/", perrita, FIS, "El Diario de Hoy"),
            self.nota("https://diarioelsalvador.com/depais/perrita/1/", perrita, FIS, "Diario El Salvador"),
            self.nota("https://diario.elmundo.sv/economia/perrita", perrita, FIS),          # Economía no exige nada
            self.nota("https://diario.elmundo.sv/politica/prestamo", "Gobierno pide ratificar préstamo del BID", NAC),
            self.nota("https://news.google.com/rss/articles/abc", "Salinas Pliego elogia el bitcoin en El Salvador", FIS,
                      "Yahoo (vía Google News)"),
            self.nota("https://www.bloomberglinea.com/x", "Los mercados cierran al alza", LATAM, "Bloomberg Línea"),
        ]
        self.assertEqual([n["categoria"] for n in noticias.al_dia(notas)], [NAC, FIS, NAC, LATAM])

    def test_se_va_lo_de_un_medio_que_ya_no_entra_y_la_cripto_que_no_interesa(self):
        notas = [self.nota("https://news.google.com/rss/articles/a1", "La Fed sube las tasas", EUA, "Infobae (vía Google News)"),
                 self.nota("https://feeds.elpais.com/a2", "El BCE baja los tipos", RESTO, "El País · Economía"),
                 self.nota("https://www.bloomberglinea.com/a3", "Solana y XRP lideran el rebote de las altcoins", LATAM, "Bloomberg Línea"),
                 self.nota("https://www.bloomberglinea.com/a4", "La Fed sube las tasas", EUA, "Bloomberg Línea")]
        self.assertEqual([n["id"] for n in noticias.al_dia(notas)], ["com/a4"])

    def test_dos_pasadas_dan_lo_mismo(self):
        notas = [self.nota("https://diario.elmundo.sv/politica/a", "Asamblea ratifica acuerdo de El Salvador y Argentina", NAC),
                 self.nota("https://example.com/b", "La Fed sube las tasas", RESTO, "Otra")]
        una = [(n["id"], n["categoria"]) for n in noticias.al_dia(notas)]
        dos = [(n["id"], n["categoria"]) for n in noticias.al_dia(notas)]
        self.assertEqual(una, dos)
        self.assertEqual([c for _, c in una], [FIS, EUA])


class Fuentes(unittest.TestCase):
    """Qué medios entran y cuánto pesan: la lista y el orden que dio el dueño el 2026-11-13."""

    def test_los_medios_que_el_dueno_saco_no_entran(self):
        for f in ["Clarin.com (vía Google News)", "Comercio TV (vía Google News)", "Debate (vía Google News)",
                  "Diario Digital Cronio de El Salvador (vía Google News)", "DiarioDigitalRD (vía Google News)",
                  "Expansión (México)", "Funds Society (vía Google News)", "FXStreet (vía Google News)",
                  "Howl.Link (vía Google News)", "Infobae · Economía", "Infobae (vía Google News)", "EL PAÍS (vía Google News)",
                  "El País · edición EE. UU.", "La Crónica de Hoy (vía Google News)", "La Nación Costa Rica (vía Google News)",
                  "La República EC (vía Google News)", "LancasterOnline (vía Google News)", "Luz Noticias (vía Google News)",
                  "MarketScreener España (vía Google News)", "Noticias24hrs.com.ve (vía Google News)", "NTN24 (vía Google News)",
                  "Quartz (vía Google News)", "Revista ADVFN (vía Google News)", "RFI (vía Google News)",
                  "Rosario Finanzas (vía Google News)", "San Antonio Express-News (vía Google News)",
                  "TalCual Digital (vía Google News)", "Universitat de València (vía Google News)",
                  "Univision (vía Google News)", "XTB.com (vía Google News)", "DW · Economía"]:
            self.assertTrue(noticias.fuera(f), f)

    def test_los_demas_si(self):
        for f in ["Bloomberg Línea", "elEconomista.net", "Diario El Salvador", "Diario El Mundo", "La Prensa Gráfica",
                  "La Prensa Gráfica (vía Google News)", "El Diario de Hoy", "France 24 · Economía", "Yahoo (vía Google News)",
                  "El Economista (vía Google News)", "AP News (vía Google News)", "La República (vía Google News)"]:
            self.assertFalse(noticias.fuera(f), f)
        for f in noticias.cfg()["fuente"]:
            self.assertFalse(noticias.fuera(f.get("medio") or f["nombre"]), f["clave"])

    def test_el_orden_de_los_pesos(self):
        nac = [noticias.peso_de(f, NAC) for f in ["elEconomista.net", "Diario El Salvador", "Diario El Mundo",
                                                  "La Prensa Gráfica (vía Google News)", "El Diario de Hoy",
                                                  "Bloomberg Línea", "Yahoo (vía Google News)"]]
        self.assertEqual(nac, sorted(nac, reverse=True))
        self.assertEqual(len(set(nac[:5])), 5, "los cinco medios nacionales pesan distinto")
        self.assertEqual(nac[-1], 0)
        inter = noticias.cfg()["pesos"]["internacional"]
        self.assertTrue(all(inter["Bloomberg Línea"] > v for k, v in inter.items() if k != "Bloomberg Línea"))
        self.assertEqual(noticias.peso_de("Diario El Salvador", FIS), noticias.peso_de("Diario El Salvador", NAC))
        self.assertLess(noticias.peso_de("Diario El Salvador", EUA), noticias.peso_de("Bloomberg Línea", EUA))

    def test_el_peso_no_rescata_a_una_nota_que_no_dice_nada(self):
        n = {"categoria": NAC, "fuente": "elEconomista.net", "resumen": ""}
        self.assertEqual(noticias.puntaje(dict(n, titular="Fallece reconocido locutor de radio")), 0)
        self.assertGreater(noticias.puntaje(dict(n, titular="Las remesas crecieron 9 % en octubre")), 6)

    def test_una_busqueda_de_un_solo_sitio_nombra_su_medio(self):
        for f in noticias.cfg()["fuente"]:
            if f.get("medio"):
                self.assertEqual(f["metodo"], "gnews", f["clave"])
                self.assertIn("site:", f["url"], f["clave"])
                self.assertGreater(noticias.peso_de(f["medio"], NAC), 0, f["clave"])


class Cripto(unittest.TestCase):
    def test_solo_bitcoin_monedas_estables_y_casas_de_cambio(self):
        for t in ["Solana y XRP lideran el rebote de las altcoins", "Dogecoin se dispara tras un mensaje de Musk",
                  "Ethereum estrena una nueva actualización de su red"]:
            self.assertTrue(noticias.cripto_ajena(t), t)
        for t in ["Bitcoin supera los US$100.000 mientras el ether sube 4 %", "Tether lanza una moneda estable en pesos",
                  "Binance lista una nueva memecoin", "La Fed mantiene las tasas"]:
            self.assertFalse(noticias.cripto_ajena(t), t)

    def test_el_precio_del_bitcoin_va_en_lo_nacional(self):
        for defecto in (EUA, LATAM, RESTO, NAC):
            t = "Bitcoin cae por debajo de US$90.000 tras el dato de empleo en EE.UU."
            self.assertEqual(noticias.clasificar(t, defecto), NAC, defecto)
        n = {"categoria": NAC, "titular": "Bitcoin toca un nuevo máximo sobre los $120,000", "resumen": ""}
        self.assertEqual(noticias.tema(n)[1], "Otros: precio del bitcoin")
        # hablar de bitcoin no es hablar de su precio
        self.assertEqual(noticias.clasificar("Salinas Pliego dice que bitcoin es el mejor dinero", LATAM), LATAM)


class Temas(unittest.TestCase):
    """El orden de las dos subsecciones nacionales, como lo dictó el dueño el 2026-11-13."""

    def tema(self, categoria, titular, resumen=""):
        return noticias.tema({"categoria": categoria, "titular": titular, "resumen": resumen})[1]

    def test_el_orden_de_los_temas(self):
        self.assertEqual([t["nombre"] for t in noticias.temas_de(FIS)],
                         ["Combustibles y petróleo", "Deuda pública", "Presupuesto", "Otra materia fiscal"])
        self.assertEqual([t["nombre"] for t in noticias.temas_de(NAC)],
                         ["Sector real", "Sector externo", "Sector monetario y financiero", "Turismo",
                          "Agricultura y sector primario", "Otros: precio del bitcoin", "Otros: investigación económica",
                          "Otros: empresas", "Otros"])
        self.assertEqual(noticias.temas_de(EUA), [])

    def test_fiscales(self):
        for titular, esperado in [
                ("Precios de los combustibles bajarán hasta $0.10 esta quincena", "Combustibles y petróleo"),
                ("El barril de Brent baja de 90 dólares por primera vez desde agosto", "Combustibles y petróleo"),
                ("Gobierno pide ratificar préstamo del BID por $50 millones para censo económico", "Deuda pública"),
                ("El Salvador coloca bonos por $1,000 millones en los mercados internacionales", "Deuda pública"),
                ("Asamblea aprueba refuerzo presupuestario de $30 millones para Salud", "Presupuesto"),
                ("Ministro de Defensa pide presupuesto de $314.5 millones para el año 2027", "Presupuesto"),
                ("Estudio mide el impacto del IVA en los hogares más pobres", "Otra materia fiscal"),
                ("TSE adjudica a CGTS la auditoría del voto electrónico", "Otra materia fiscal")]:
            self.assertEqual(noticias.clasificar(titular, NAC), FIS, titular)
            self.assertEqual(self.tema(FIS, titular), esperado, titular)

    def test_economicas(self):
        for titular, esperado in [
                ("El PIB creció 3.1 % en el tercer trimestre, impulsado por la construcción", "Sector real"),
                ("La inflación repunta a 3.91 % en octubre", "Sector real"),
                ("Las remesas suman $8,000 millones a octubre", "Sector externo"),
                ("La inversión extranjera directa cae 12 % en el primer semestre", "Sector externo"),
                ("La banca aumentó 8 % el crédito a las empresas", "Sector monetario y financiero"),
                ("El Salvador recibe 3.9 millones de visitantes hasta octubre", "Turismo"),
                ("La cosecha de maíz caerá 15 % por la sequía", "Agricultura y sector primario"),
                ("Bitcoin supera los $100,000 y marca un nuevo máximo", "Otros: precio del bitcoin"),
                ("Fusades presenta un estudio sobre la informalidad", "Otros: investigación económica"),
                ("Textilera invertirá $40 millones y se acoge a incentivos fiscales de zona franca", "Otros: empresas"),
                ("Fallece reconocido locutor de radio", "Otros")]:
            self.assertEqual(self.tema(NAC, titular), esperado, titular)

    def test_el_petroleo_es_de_aqui_solo_en_un_medio_de_aqui_y_si_manda_en_el_titular(self):
        brent = "El barril de Brent baja de 90 dólares por primera vez desde agosto"
        self.assertEqual(noticias.clasificar(brent, NAC), FIS)
        self.assertEqual(noticias.clasificar(brent, LATAM), RESTO)            # en Bloomberg Línea sigue siendo internacional
        mercados = "Wall Street se recupera en medio del escándalo de Nvidia y el repunte del petróleo"
        self.assertEqual(noticias.clasificar(mercados, NAC), EUA)

    def test_una_palabra_fiscal_suelta_en_el_extracto_no_hace_fiscal_a_la_nota(self):
        titular = "Opamss reporta más de $7,888.5 millones en inversión liberada"
        extracto = "Las actividades vinculadas a la construcción generaron $1,022.8 millones en ingresos tributarios y 157,000 empleos."
        self.assertEqual(noticias.clasificar(titular + " " + extracto, NAC, titular), NAC)
        self.assertEqual(self.tema(NAC, titular, extracto), "Sector real")

    def test_una_deuda_con_la_justicia_no_es_deuda_publica(self):
        t = "Benjamín Cuéllar: “La impunidad tiene cuatro rostros y El Salvador sigue sin saldar su deuda con la justicia”"
        self.assertEqual(noticias.clasificar(t, FIS), NAC)
        self.assertEqual(noticias.clasificar("Prevén déficit de lluvias en El Salvador en 2027", FIS), NAC)
        self.assertEqual(noticias.clasificar("La deuda pública de El Salvador llega al 88 % del PIB", NAC), FIS)

    def test_el_catalogo_de_temas_esta_completo(self):
        c = noticias.cfg()
        for t in c["tema"]:
            self.assertIn(t["categoria"], noticias.NACIONALES)
            self.assertTrue(t.get("resto") or t.get("regla") in c["reglas"] or t.get("palabras") in c["palabras"], t["nombre"])
        for cat in noticias.NACIONALES:
            self.assertEqual(sum(1 for t in noticias.temas_de(cat) if t.get("resto")), 1, cat)
        import rutas
        series = {s["clave"] for s in rutas.series()}
        for d in c["dato_bcr"]:
            self.assertTrue(set(d["series"]) <= series, d["series"])


class Prioridad(unittest.TestCase):
    """`priorizar`: una historia cuenta una vez, las otras fuentes entran poco, y el orden es el de los temas."""
    n = 0

    def nota(self, categoria, titular, fuente="Diario El Mundo", hora="06:00", edicion="2026-11-13", resumen=""):
        Prioridad.n += 1
        return {"id": f"n{Prioridad.n:03d}", "edicion": edicion, "fecha_hora": f"2026-11-12T{hora}", "categoria": categoria,
                "fuente": fuente, "titular": titular, "resumen": resumen}

    def test_la_misma_historia_queda_en_el_medio_que_mas_pesa(self):
        a = self.nota(FIS, "Ministerio de Trabajo da ultimátum a alcaldía de Usulután Norte por salarios atrasados", "El Diario de Hoy")
        b = self.nota(FIS, "Ministerio del Trabajo advierte acciones penales a Alcaldía de Usulután Norte por no pagar salarios")
        c = self.nota(NAC, "Alcaldía de Usulután Norte: Ministerio de Trabajo advierte por salarios atrasados", "Yahoo (vía Google News)")
        noticias.priorizar([a, b, c])
        self.assertEqual(b["orden"], 1)
        self.assertGreater(b["puntaje"], 0)
        self.assertLessEqual(a["puntaje"], 0)
        self.assertLessEqual(c["puntaje"], 0, "la misma historia baja aunque haya caído en la otra subsección")

    def test_historias_distintas_no_se_confunden(self):
        a = noticias.fichas("El Salvador proyecta que el aporte económico del turismo al PIB pase del 10 % a un 14 %")
        b = noticias.fichas("Turismo podría aportar el 14 % del PIB de El Salvador")
        c = noticias.fichas("Las remesas crecieron 14 % en octubre, según el BCR")
        self.assertTrue(noticias.misma_historia(a, b))
        self.assertFalse(noticias.misma_historia(a, c))
        self.assertFalse(noticias.misma_historia(b, c))

    def test_de_otras_fuentes_solo_dos_por_subseccion(self):
        temas = ["Las remesas crecieron 9 % en octubre", "El PIB creció 3 % en el trimestre", "La banca sube el crédito 8 %",
                 "El turismo deja $3,000 millones en divisas"]
        otras = [self.nota(NAC, t, f"Medio {i} (vía Google News)") for i, t in enumerate(temas)]
        propia = self.nota(NAC, "La cosecha de maíz cae 15 % por la sequía", "Diario El Salvador")
        noticias.priorizar(otras + [propia])
        self.assertEqual(sum(1 for n in otras if n["puntaje"] > 0), 2)
        self.assertGreater(propia["puntaje"], 0)
        self.assertEqual(sorted(n["orden"] for n in otras + [propia]), [1, 2, 3, 4, 5])
        self.assertTrue(all(n["orden"] > 3 for n in otras if n["puntaje"] <= 0), "las que bajan van al final")

    def test_el_orden_es_el_de_los_temas_y_no_el_del_puntaje(self):
        empresas = self.nota(NAC, "Empresa invertirá $251 millones en centros comerciales y crea empleos", "elEconomista.net")
        turismo = self.nota(NAC, "El turismo crece 8 %", "El Diario de Hoy")
        externo = self.nota(NAC, "Las remesas crecen 9 %", "El Diario de Hoy")
        real = self.nota(NAC, "El IVAE sube 2 %", "El Diario de Hoy")
        noticias.priorizar([empresas, turismo, externo, real])
        self.assertEqual([n["titular"] for n in sorted([empresas, turismo, externo, real], key=lambda n: n["orden"])],
                         [real["titular"], externo["titular"], turismo["titular"], empresas["titular"]])
        self.assertEqual(max([empresas, turismo, externo, real], key=lambda n: n["puntaje"]), empresas)

    def test_la_segunda_nota_de_un_tema_vale_menos(self):
        a = self.nota(NAC, "Las remesas crecieron 9 % en octubre", hora="06:00")
        b = self.nota(NAC, "Deportaciones de salvadoreños suben 20 % y golpean las remesas del oriente", hora="05:00")
        solas = {n["id"]: noticias.puntaje(n) for n in (a, b)}
        noticias.priorizar([a, b])
        primera, segunda = sorted((a, b), key=lambda n: n["orden"])
        self.assertEqual(primera["tema"], segunda["tema"])
        self.assertEqual(primera["puntaje"], solas[primera["id"]])
        self.assertEqual(segunda["puntaje"], max(solas[segunda["id"]] - noticias.cfg()["general"]["paso_mismo_tema"], 1))

    def test_del_precio_del_bitcoin_una_sola(self):
        a = self.nota(NAC, "Bitcoin cae por debajo de US$90.000", "Bloomberg Línea", hora="06:00")
        b = self.nota(NAC, "El precio del bitcoin repunta 4 % tras el dato de inflación", "Bloomberg Línea", hora="03:00")
        noticias.priorizar([a, b])
        self.assertEqual(sum(1 for n in (a, b) if n["puntaje"] > 0), 1)
        self.assertEqual({a["tema"], b["tema"]}, {"Otros: precio del bitcoin"})

    def test_un_dato_que_el_bcr_acaba_de_publicar_sube(self):
        publicado = noticias.publicaciones([{"serie": "remesas", "origen": "bcr", "fecha_esperada": "2026-11-24"},
                                            {"serie": "ipc", "origen": "rezago", "fecha_esperada": "2026-11-24"}])
        self.assertEqual(set(publicado), {"remesas"}, "solo cuentan las fechas que anunció el BCR")
        dia = self.nota(NAC, "Las remesas crecieron 9 % en octubre", edicion="2026-11-25")
        antes = self.nota(NAC, "Las remesas crecieron 9 % en octubre", edicion="2026-11-20")
        otra = self.nota(NAC, "El turismo crece 8 %", edicion="2026-11-25")
        bono = noticias.cfg()["general"]["bono_dato_bcr"]
        self.assertEqual(noticias.puntaje(dia, publicado), noticias.puntaje(antes, publicado) + bono)
        self.assertEqual(noticias.puntaje(otra, publicado), noticias.puntaje(otra))

    def test_cada_subseccion_se_numera_desde_uno_y_no_quedan_marcas(self):
        notas = [self.nota(EUA, "La Fed sube las tasas", "Bloomberg Línea"), self.nota(EUA, "Wall Street cae 2 %", "Bloomberg Línea"),
                 self.nota(FIS, "Hacienda coloca LETES por $50 millones"), self.nota(NAC, "Las remesas crecen 9 %")]
        noticias.priorizar(notas)
        self.assertEqual(sorted(n["orden"] for n in notas if n["categoria"] == EUA), [1, 2])
        self.assertEqual([n["orden"] for n in notas if n["categoria"] != EUA], [1, 1])
        self.assertEqual(notas[0]["tema"], "")
        self.assertTrue(all(set(n) == {"id", "edicion", "fecha_hora", "categoria", "fuente", "titular", "resumen",
                                       "puntaje", "tema", "orden"} for n in notas))


class ElMundo(unittest.TestCase):
    PORTADA = '''<article> <div class="article-image"><a href="https://diario.elmundo.sv/economia/nota-uno" title="x"></a></div>
      <div class="article-details"><div class="article-title"><a href="https://diario.elmundo.sv/economia/nota-uno"
      title="La inflaci&oacute;n repunta a 3.91 %">La inflación repunta a 3.91 %</a></div>
      <div class="article-date"> lunes 9, noviembre 2026 - 4:50 a. m. </div></div></article>
      <article><div class="article-title"><a href="https://diario.elmundo.sv/economia/nota-dos" title="Otra nota">Otra nota</a></div>
      <div class="article-date"> jueves 12, noviembre 2026 - 12:07 p. m. </div></article>'''

    def test_la_portada_da_enlace_titular_y_fecha(self):
        notas = noticias.portada_elmundo(self.PORTADA)
        self.assertEqual([(u.rsplit("/", 1)[1], t) for u, t, _ in notas], [("nota-uno", "La inflación repunta a 3.91 %"), ("nota-dos", "Otra nota")])
        self.assertEqual(notas[0][2].strftime("%Y-%m-%d %H:%M"), "2026-11-09 04:50")
        self.assertEqual(notas[1][2].strftime("%Y-%m-%d %H:%M"), "2026-11-12 12:07")

    def test_fechas(self):
        self.assertEqual(noticias.fecha_elmundo("jueves 12, noviembre 2026 - 5:47 p. m.").hour, 17)
        self.assertEqual(noticias.fecha_elmundo("jueves 12, noviembre 2026 - 12:30 a. m.").hour, 0)
        self.assertIsNone(noticias.fecha_elmundo("ayer"))

    def test_meta(self):
        pagina = '<meta property="og:description" content="El BCR inform&oacute; el dato."><meta content="2026-11-12T17:47:21-06:00" property="article:published_time">'
        self.assertEqual(noticias.meta(pagina, "og:description"), "El BCR informó el dato.")
        self.assertEqual(noticias.fecha_de(noticias.meta(pagina, "article:published_time")).hour, 17)
        self.assertEqual(noticias.meta(pagina, "no-esta"), "")


class Limpieza(unittest.TestCase):
    def test_extracto_sin_html_y_cortado(self):
        self.assertEqual(noticias.extracto("<p>Hola&nbsp;<b>mundo</b> &amp; más</p>"), "Hola mundo & más")
        largo = noticias.extracto("palabra " * 100)
        self.assertLessEqual(len(largo), noticias.LARGO_RESUMEN)
        self.assertTrue(largo.endswith("…"))

    def test_extracto_igual_al_titular_no_se_repite(self):
        self.assertEqual(noticias.extracto("Sube el café", "Sube el Café"), "")

    def test_url_sin_rastreadores(self):
        self.assertEqual(noticias.url_limpia("https://x.com/a?utm_source=rss&id=3#frag"), "https://x.com/a?id=3")

    def test_fechas_de_feed(self):
        self.assertEqual(noticias.fecha_de("Thu, 12 Nov 2026 13:00:00 GMT").hour, 13)
        self.assertEqual(noticias.fecha_de("2026-11-12T13:00:00Z").tzinfo, dt.timezone.utc)
        self.assertIsNone(noticias.fecha_de("ayer"))

    def test_la_edicion_cierra_a_las_siete(self):
        antes = dt.datetime(2026, 11, 12, 6, 59, tzinfo=noticias.SV)
        despues = dt.datetime(2026, 11, 12, 7, 0, tzinfo=noticias.SV)
        self.assertEqual(noticias.edicion_de(antes), "2026-11-12")
        self.assertEqual(noticias.edicion_de(despues), "2026-11-13")

    def test_las_fuentes_del_catalogo_tienen_categoria_valida(self):
        for f in noticias.cfg()["fuente"]:
            self.assertIn(f["categoria"], noticias.CATEGORIAS, f["clave"])
            self.assertIn(f["metodo"], {"rss", "wp_api", "gnews", "elmundo"}, f["clave"])
            exige = f.get("exige", [])
            for e in [exige] if isinstance(exige, str) else exige:
                self.assertTrue(e in noticias.cfg()["palabras"] or e in noticias.cfg()["reglas"], f"{f['clave']}: {e}")

    def test_las_reglas_nombran_listas_que_existen(self):
        for regla, vias in noticias.cfg()["reglas"].items():
            self.assertNotIn(regla, noticias.cfg()["palabras"], "una regla y una lista no comparten nombre")
            for via in vias:
                for lista in via:
                    self.assertIn(lista, noticias.cfg()["palabras"], f"{regla}: {lista}")


if __name__ == "__main__":
    unittest.main()
