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
            self.assertIn(f["metodo"], {"rss", "wp_api", "gnews"}, f["clave"])
            if f.get("exige"):
                self.assertIn(f["exige"], noticias.cfg()["palabras"])


if __name__ == "__main__":
    unittest.main()
