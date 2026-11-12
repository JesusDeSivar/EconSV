"""Los cálculos de oro y las reglas del calendario, sin red."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tuberias"))
import calendario  # noqa: E402
import oro  # noqa: E402
import rutas  # noqa: E402


class Oro(unittest.TestCase):
    def test_variacion_anual_y_del_periodo(self):
        v = {(2025, 1): 100.0, (2025, 2): 110.0, (2026, 1): 105.0, (2026, 2): 121.0}
        self.assertAlmostEqual(oro.variacion(v, "T", 4)[(2026, 2)], 10.0)
        self.assertAlmostEqual(oro.variacion(v, "T", 1)[(2025, 2)], 10.0)
        self.assertNotIn((2025, 1), oro.variacion(v, "T", 4))

    def test_no_hay_variacion_sobre_una_base_negativa_o_cero(self):
        self.assertEqual(oro.variacion({(2025, 1): -5.0, (2026, 1): 5.0}, "A", 1), {})

    def test_suma_anual_solo_con_la_ventana_completa(self):
        v = {(2025, m): 1.0 for m in range(1, 13)}
        v[(2026, 1)] = 3.0
        s = oro.suma_anual(v, "M")
        self.assertEqual(s, {(2025, 12): 12.0, (2026, 1): 14.0})

    def test_pct_pib_de_un_flujo_mensual_sale_por_trimestre(self):
        v = {(2025, m): 10.0 for m in range(1, 13)}
        r, fr = oro.pct_pib(v, "M", "flujo", {(2025, 4): 1200.0})
        self.assertEqual((r, fr), ({(2025, 4): 10.0}, "T"))

    def test_pct_pib_de_un_saldo_usa_el_cierre_del_trimestre(self):
        r, _ = oro.pct_pib({(2025, 3): 50.0, (2025, 4): 60.0}, "T", "saldo", {(2025, 4): 240.0})
        self.assertEqual(r, {(2025, 4): 25.0})

    def test_atras_cruza_el_anio(self):
        self.assertEqual(oro.atras(2026, 1, "M", 1), (2025, 12))
        self.assertEqual(oro.atras(2026, 2, "T", 4), (2025, 2))

    def test_el_catalogo_de_indicadores_es_coherente(self):
        claves = {s["clave"] for s in rutas.series()}
        for ind in rutas.catalogo("indicadores")["indicador"]:
            self.assertIn(ind["seccion"], {"actividad", "precios", "externo", "turismo", "construccion"})
            self.assertLessEqual(len(ind["linea"]) if ind.get("tipo", "lineas") != "ranking" else 0, 2,
                                 f"{ind['clave']}: una gráfica de tiempo lleva una o dos líneas")
            for linea in ind["linea"]:
                self.assertIn(linea["serie"], claves)
                self.assertTrue(set(linea.get("vistas", [])) <= set(ind["vistas"]))


class Calendario(unittest.TestCase):
    def setUp(self):
        self._orig = (calendario.leer_bronce, calendario.cortes, rutas.series)
        calendario.leer_bronce = lambda: {"eventos": [
            {"id": 1, "title": "Remesas", "start": "2026-11-24", "url": "Oct.26"},
            {"id": 2, "title": "Remesas", "start": "2026-12-23", "url": "Nov.26"},
            {"id": 3, "title": "PIB T", "start": "2026-12-23", "url": "T3-26"},
            {"id": 4, "title": "PIB T", "start": "2027-03-26", "url": "T4-26"}]}
        calendario.cortes = lambda: {"remesas": (2026, 9), "pib_t": (2026, 2), "pib_a": (2025, 1), "ipc": (2026, 10)}
        rutas.series = lambda: [
            {"clave": "remesas", "nombre": "Remesas", "frecuencia": "M", "calendario": "Remesas", "rezago_dias": 25},
            {"clave": "pib_t", "nombre": "PIB T", "frecuencia": "T", "calendario": "PIB T", "rezago_dias": 85},
            {"clave": "pib_a", "nombre": "PIB anual", "frecuencia": "A", "calendario": "PIB T", "rezago_dias": 90},
            {"clave": "ipc", "nombre": "IPC", "frecuencia": "M", "calendario": "No anunciado", "rezago_dias": 10}]

    def tearDown(self):
        calendario.leer_bronce, calendario.cortes, rutas.series = self._orig

    def estado(self, dia):
        return {e["clave"]: e for e in calendario.estado(dt.date.fromisoformat(dia))}

    def test_toca_desde_la_fecha_anunciada(self):
        self.assertEqual(self.estado("2026-11-23")["remesas"]["situacion"], "al día")
        e = self.estado("2026-11-24")["remesas"]
        self.assertEqual((e["situacion"], e["proximo"], e["origen"]), ("toca", "2026-10", "bcr"))

    def test_atrasada_pasados_diez_dias(self):
        self.assertEqual(self.estado("2026-12-04")["remesas"]["situacion"], "toca")
        self.assertEqual(self.estado("2026-12-05")["remesas"]["situacion"], "atrasada")

    def test_el_dato_anual_sale_con_el_cuarto_trimestre(self):
        e = self.estado("2026-11-12")["pib_a"]
        self.assertEqual((e["proximo"], e["esperado"], e["origen"]), ("2026", "2027-03-26", "bcr"))

    def test_sin_anuncio_se_estima_por_rezago(self):
        e = self.estado("2026-12-09")["ipc"]
        self.assertEqual((e["proximo"], e["esperado"], e["origen"], e["situacion"]), ("2026-11", "2026-12-10", "rezago", "al día"))

    def test_periodos(self):
        self.assertEqual(calendario.periodo_evento("Oct.26"), ("M", 2026, 10))
        self.assertEqual(calendario.periodo_evento("T3-26"), ("T", 2026, 3))
        self.assertEqual(calendario.periodo_evento("2025"), ("A", 2025, 1))
        self.assertIsNone(calendario.periodo_evento("sin período"))
        self.assertEqual(calendario.siguiente(2026, 12, "M"), (2027, 1))
        self.assertEqual(calendario.siguiente(2026, 4, "T"), (2027, 1))
        self.assertEqual(calendario.fin_de_periodo(2026, 3, "T"), dt.date(2026, 9, 30))


if __name__ == "__main__":
    unittest.main()
