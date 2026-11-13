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

    def nota(self, url, titular, categoria, resumen=""):
        return {"id": url[-6:], "url": url, "titular": titular, "resumen": resumen, "categoria": categoria}

    def test_se_va_lo_que_su_seccion_ya_no_admite_y_lo_demas_se_reparte_de_nuevo(self):
        perrita = "Muere perrita rescatada por alcaldía y anuncian seguimiento al caso"
        notas = [
            self.nota("https://diario.elmundo.sv/nacionales/perrita", perrita, FIS),
            self.nota("https://www.elsalvador.com/noticias/nacional/perrita/1/2026/", perrita, FIS),
            self.nota("https://diario.elmundo.sv/economia/perrita", perrita, FIS),          # Economía no exige nada
            self.nota("https://diario.elmundo.sv/politica/prestamo", "Gobierno pide ratificar préstamo del BID", NAC),
            self.nota("https://news.google.com/rss/articles/abc", "Salinas Pliego elogia el bitcoin en El Salvador", FIS),
            self.nota("https://www.bloomberglinea.com/x", "Los mercados cierran al alza", LATAM),
        ]
        quedan = {n["url"].rsplit("/", 1)[0][-12:] + n["url"][-8:]: n["categoria"] for n in noticias.al_dia(notas)}
        self.assertEqual(list(quedan.values()), [NAC, FIS, NAC, LATAM])

    def test_dos_pasadas_dan_lo_mismo(self):
        notas = [self.nota("https://diario.elmundo.sv/politica/a", "Asamblea ratifica acuerdo de El Salvador y Argentina", NAC),
                 self.nota("https://example.com/b", "La Fed sube las tasas", RESTO)]
        una = [(n["id"], n["categoria"]) for n in noticias.al_dia(notas)]
        dos = [(n["id"], n["categoria"]) for n in noticias.al_dia(notas)]
        self.assertEqual(una, dos)
        self.assertEqual([c for _, c in una], [FIS, EUA])


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
