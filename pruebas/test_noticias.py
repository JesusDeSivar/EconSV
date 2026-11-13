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
            if f.get("exige"):
                self.assertIn(f["exige"], noticias.cfg()["palabras"])


if __name__ == "__main__":
    unittest.main()
