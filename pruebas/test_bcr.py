"""El lector del BCR, sin red: de lo que el servidor entrega a observaciones."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tuberias"))
import bcr  # noqa: E402


def grafica(series, fechas, celdas, tipo=3, nombres=None):
    n = len(series)
    return {"slug": "prueba", "url": "", "tipo_serie": tipo, "modo": "grafica",
            "variables": [{"id": i + 1, "nombre": (nombres or [f"{i + 1} V{i + 1}"] * n)[i], "nombre_en": ""} for i in range(n)],
            "fechas": fechas, "grafica": series, "tabla_celdas": celdas if celdas and isinstance(celdas[0], list) else [celdas],
            "vista_inicial": {}}


class Grafica(unittest.TestCase):
    def test_la_tabla_viene_por_periodo_y_en_cualquier_orden(self):
        # dos variables, tres meses; la tabla trae cada período como un tramo, desordenado por dentro
        b = grafica([[10.5, 11.0, 12.25], [1.0, 2.0, 3.0]], ["2026-01", "2026-02", "2026-3(p)"],
                    ["1.00", "10.50", "11.00", "2.00", "3.00", "12.25"])
        obs, res = bcr.interpretar(b, "M")
        self.assertEqual(res["observaciones"], 6)
        self.assertEqual(res["hasta"], "2026-03")
        self.assertIn((2026, 3, "p", 0, 12.25, ""), obs)
        self.assertIn((2026, 3, "p", 1, 3.0, ""), obs)

    def test_centinelas_y_celdas_vacias(self):
        # −3000000 es ND, −6000000 es C; un 0 es celda vacía solo si la tabla la trae vacía
        b = grafica([[0, -3000000, 5.0], [0, 7.0, -6000000], [0, 0, 0]], ["2025-01", "2025-02", "2025-03"],
                    ["", "", "", "ND", "7.00", "0", "5.00", "C", "0.00"])
        obs, res = bcr.interpretar(b, "M")
        d = {(o[1], o[3]): (o[4], o[5]) for o in obs}
        self.assertNotIn((1, 0), d)                    # vacía: no hay observación
        self.assertEqual(d[(2, 0)], (None, "ND"))
        self.assertEqual(d[(3, 1)], (None, "C"))
        self.assertEqual(d[(2, 2)], (0.0, ""))         # cero de verdad: la tabla dice «0»
        self.assertEqual(res["desde"], "2025-02")

    def test_una_cifra_distinta_en_la_tabla_falla(self):
        b = grafica([[10.5, 11.0]], ["2026-01", "2026-02"], ["10.50", "99.00"])
        with self.assertRaises(bcr.ErrorPortal):
            bcr.interpretar(b, "M")

    def test_centinela_desconocido_falla(self):
        b = grafica([[10.5, -9000000]], ["2026-01", "2026-02"], ["10.50", "X"])
        with self.assertRaises(bcr.ErrorPortal):
            bcr.interpretar(b, "M")

    def test_lotes_de_variables(self):
        b = grafica([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], ["2026-1(e)", "2026-2(e)"],
                    [["3.00", "1.00", "2.00", "4.00"], ["5.00", "6.00"]], tipo=5)
        obs, res = bcr.interpretar(b, "T")
        self.assertEqual(res["hasta"], "2026-T2")
        self.assertIn((2026, 2, "e", 2, 6.0, ""), obs)

    def test_frecuencia_del_catalogo_contra_la_del_portal(self):
        b = grafica([[1.0]], ["2026-01"], ["1.00"], tipo=3)
        with self.assertRaises(bcr.ErrorPortal):
            bcr.interpretar(b, "T")

    def test_la_vista_inicial_tiene_que_estar_en_lo_pedido(self):
        b = grafica([[10.5, 11.0]], ["2026-01", "2026-02"], ["10.50", "11.00"], nombres=["1 Total"])
        b["vista_inicial"] = {"fechas": ["2026-02"], "series": [{"nombre": "Total", "valores": [11.0]}]}
        self.assertEqual(bcr.interpretar(b, "M")[1]["testigo"], 1)
        b["vista_inicial"]["series"][0]["valores"] = [11.5]
        with self.assertRaises(bcr.ErrorPortal):
            bcr.interpretar(b, "M")


class Tabla(unittest.TestCase):
    def base(self):
        return {"slug": "prueba", "url": "", "tipo_serie": 3, "modo": "tabla",
                "variables": [{"id": 7, "nombre": "1 Índice general", "nombre_en": ""}],
                "cabecera": [[["2025", 2], ["2026", 1]], ["Nov", "Dic", "Ene (p)"]],
                "filas": [["134.99", "1,135.60", ""]], "vista_inicial": {}}

    def test_cabecera_de_anios_y_meses(self):
        obs, res = bcr.interpretar(self.base(), "M")
        self.assertEqual([(o[0], o[1], o[4]) for o in obs], [(2025, 11, 134.99), (2025, 12, 1135.6)])
        self.assertEqual(res["hasta"], "2025-12")

    def test_fila_mas_corta_que_la_cabecera_falla(self):
        b = self.base()
        b["filas"] = [["134.99"]]
        with self.assertRaises(bcr.ErrorPortal):
            bcr.interpretar(b, "M")


class Piezas(unittest.TestCase):
    def test_periodos(self):
        self.assertEqual(bcr.periodo_grafica("2025-9(p)", "M"), (2025, 9, "p"))
        self.assertEqual(bcr.periodo_grafica("2005-01", "T"), (2005, 1, ""))
        self.assertEqual(bcr.periodo_grafica(2021, "A"), (2021, 1, ""))
        self.assertEqual(bcr.periodo_grafica("2020(r)", "A"), (2020, 1, "r"))
        self.assertEqual(bcr.periodo_tabla("2026", "Feb (p)", "M"), (2026, 2, "p"))
        self.assertEqual(bcr.periodo_tabla("2026", "III", "T"), (2026, 3, ""))
        self.assertEqual(bcr.etiqueta(2026, 2, "T"), "2026-T2")
        self.assertEqual(bcr.fecha(2026, 2, "T"), "2026-04-01")

    def test_rotulos(self):
        self.assertEqual(bcr.rotulo("1.1 Activos de Reserva [Matriz]"), ("1.1", "Activos de Reserva"))
        self.assertEqual(bcr.rotulo("Crédito"), ("", "Crédito"))

    def test_tablas_del_html(self):
        h = '<table><tr><td colspan=2>2025</td></tr><tr><td> Ene </td><td>Feb&nbsp;</td></tr></table>'
        self.assertEqual(bcr.tablas(h), [[[{"txt": "2025", "span": 2}], [{"txt": "Ene", "span": 1}, {"txt": "Feb", "span": 1}]]])

    def test_volcar_es_json(self):
        import json
        obj = {"a": [1, 2.5, "x"], "b": [{"c": []}, {"d": [[1, 2], [3]]}], "e": "ñ"}
        self.assertEqual(json.loads(bcr.volcar(obj)), obj)


if __name__ == "__main__":
    unittest.main()
