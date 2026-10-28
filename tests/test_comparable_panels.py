"""CART081: painéis comparáveis usam a mesma régua de cor e de tamanho.

Uma figura dos registros do GBIF no Itatiaia antes e depois de 2015, em dois
mapas de calor, saiu com nota A: cada painel esticava a rampa até o próprio
máximo, e o vermelho de um não valia o vermelho do outro.
"""

from __future__ import annotations

import importlib.util
import os
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography import rulebook  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _regra():
    return next(rule for rule in rulebook.RULES if rule.id == "CART081")


def _quadros(*escalas):
    return {"map_frames": [{"item_id": f"map{i}", "value_scales": e} for i, e in enumerate(escalas)]}


class RegraPura(unittest.TestCase):
    def test_um_quadro_nao_se_avalia(self):
        self.assertEqual(_regra().check(_quadros([])).status, rulebook.STATUS_SKIP)

    def test_mapa_de_calor_automatico_em_dois_paineis_reprova(self):
        calor = {"kind": "heatmap", "variable": "", "maximum": 0.0, "radius": 3.0}
        resultado = _regra().check(_quadros([{"layer": "Antes", **calor}], [{"layer": "Depois", **calor}]))
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("máximo automático", resultado.detail_pt)

    def test_mesmo_maximo_passa(self):
        calor = {"kind": "heatmap", "variable": "", "maximum": 40.0, "radius": 3.0}
        self.assertEqual(_regra().check(_quadros([{"layer": "A", **calor}], [{"layer": "B", **calor}])).status,
                         rulebook.STATUS_PASSED)

    def test_reguas_proporcionais_diferentes_reprovam(self):
        a = {"layer": "A", "kind": "proportional", "variable": "records", "domain": [1, 500], "sizes": [1, 8]}
        b = {"layer": "B", "kind": "proportional", "variable": "records", "domain": [1, 9000], "sizes": [1, 8]}
        self.assertEqual(_regra().check(_quadros([a], [b])).status, rulebook.STATUS_FAIL)
        self.assertEqual(_regra().check(_quadros([a], [{**b, "domain": [1, 500]}])).status, rulebook.STATUS_PASSED)

    def test_variaveis_diferentes_nao_se_comparam(self):
        a = {"layer": "População", "kind": "graduated", "variable": "pop", "breaks": [0, 10, 20]}
        b = {"layer": "Densidade", "kind": "graduated", "variable": "dens", "breaks": [0, 5, 9]}
        self.assertEqual(_regra().check(_quadros([a], [b])).status, rulebook.STATUS_SKIP)


@unittest.skipUnless(HAS_QGIS, "PyQGIS indisponível")
class NoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def setUp(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))

    @staticmethod
    def _locais(nome, quantos, semente, campo=True):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer("Point?crs=EPSG:31983" + ("&field=records:integer" if campo else ""), nome, "memory")
        sorteio = random.Random(semente)
        feats = []
        for i in range(quantos):
            f = QgsFeature(camada.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(sorteio.uniform(520000, 545000), sorteio.uniform(7515000, 7535000))))
            if campo:
                f.setAttribute(0, sorteio.randint(1, 50) * (10 if semente == 2 else 1))
            feats.append(f)
        camada.dataProvider().addFeatures(feats)
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def _compor(self, pasta, a, b):
        from sigmai.cartography.compose import compose_map

        return compose_map({
            "layer_ids": [a.id()], "subject_layer_id": a.id(), "panel_title": "Antes",
            "second_map": {"layer_ids": [b.id()], "subject_layer_id": b.id(), "panel_title": "Depois"},
            "comparison_same_scale": True, "title": "T", "data_source": "teste", "map_language": "pt-BR",
            "output_path": os.path.join(pasta, "p.png"), "format": "png", "dpi": 72, "confirm_overwrite": True,
        }, {"dry_run": False})

    @staticmethod
    def _status(resultado):
        return next(r for r in resultado["audit"]["results"] if r["id"] == "CART081")["status"]

    def test_mapas_de_calor_automaticos_em_paineis_reprovam(self):
        from sigmai.qgis_actions.symbology import apply_heatmap_style

        a, b = self._locais("Antes", 300, 1, campo=False), self._locais("Depois", 900, 2, campo=False)
        for camada in (a, b):
            apply_heatmap_style({"layer_id": camada.id(), "radius": 3}, {"dry_run": False})
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, a, b)
        self.assertEqual(self._status(resultado), rulebook.STATUS_FAIL)

    def test_simbolos_proporcionais_com_a_mesma_regua_passam(self):
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style

        a, b = self._locais("Antes", 60, 1), self._locais("Depois", 60, 2)
        with pasta_temporaria() as pasta:
            for camada in (a, b):
                apply_proportional_symbol_style({"layer_id": camada.id(), "field_name": "records"}, {"dry_run": False})
            self.assertEqual(self._status(self._compor(pasta, a, b)), rulebook.STATUS_FAIL)
            for camada in (a, b):
                plano = apply_proportional_symbol_style({"layer_id": camada.id(), "field_name": "records",
                                                         "min_value": 1, "max_value": 500}, {"dry_run": False})
                self.assertEqual((plano["min"], plano["max"]), (1.0, 500.0))
            self.assertEqual(self._status(self._compor(pasta, a, b)), rulebook.STATUS_PASSED)

    def test_cart076_mede_tambem_o_segundo_painel(self):
        """O laudo media os pontos só no primeiro painel: no exemplo do artigo, o painel B não tinha medida."""
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        poucos = self._locais("Poucos", 20, 1, campo=False)
        amontoados = QgsVectorLayer("Point?crs=EPSG:31983", "Amontoados", "memory")
        feats = []
        for i in range(3000):
            f = QgsFeature(amontoados.fields())
            x, y = (522000, 7516000) if i % 3 == 0 else (544000, 7534000) if i % 3 == 1 else (533000, 7525000)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x + (i % 7), y + (i % 5))))
            feats.append(f)
        amontoados.dataProvider().addFeatures(feats)
        amontoados.updateExtents()
        QgsProject.instance().addMapLayer(amontoados)
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, poucos, amontoados)
        cart076 = next(r for r in resultado["audit"]["results"] if r["id"] == "CART076")
        self.assertEqual(cart076["status"], rulebook.STATUS_FAIL, cart076)
        self.assertIn("(painel 2)", cart076["detail_pt"])


if __name__ == "__main__":
    unittest.main()
