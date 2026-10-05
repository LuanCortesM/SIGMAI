"""Defeitos do próprio regulamento achados pela injeção de defeitos (paper/tgis, E1).

O experimento E1 compõe mapas, estraga cada um pela API de layout do PyQGIS
— como um script ou uma edição à mão faria — e audita de novo. Três falhas
da auditoria apareceram no piloto:

* CART003: num layout sem barra de escala, ``observation["scalebar"]`` vale
  None; a regra chamava ``.get`` nele, quebrava e o motor a marcava "não
  avaliada" — um mapa sem escala nenhuma passava;
* CART062: o quadro em branco era medido pela tinta do PNG, e moldura e
  grade são tinta — apagadas as camadas de seis mapas, a regra passou nos seis;
* CART061: auditando um layout, a extensão dos dados nunca era informada e a
  regra nunca era avaliada. Agora vem do assunto (receita ou subject_layer_id).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography import rulebook  # noqa: E402
from sigmai.cartography.rulebook import evaluate  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _status(report, rule_id):
    return next(entry["status"] for entry in report["results"] if entry["id"] == rule_id)


class SemEscalaNenhuma(unittest.TestCase):
    def test_layout_sem_barra_e_sem_texto_reprova_em_vez_de_quebrar(self):
        observation = {"items": [], "scalebar": None, "map": {}, "legend": None, "north": None, "output": {}}
        self.assertEqual(_status(evaluate(observation), "CART003"), rulebook.STATUS_FAIL)


class QuadroEmBrancoPelasCamadas(unittest.TestCase):
    def _regra(self, mapa):
        return rulebook._check_map_not_blank({"map": mapa}).status

    def test_camadas_sem_nada_desenhado_reprovam_mesmo_com_tinta_de_moldura(self):
        self.assertEqual(self._regra({"layer_ink_fraction": 0.0, "rendered_ink_fraction": 0.04}), rulebook.STATUS_FAIL)

    def test_mapa_esparso_com_poucos_pixels_desenhados_passa(self):
        self.assertEqual(self._regra({"layer_ink_fraction": 0.0008, "rendered_ink_fraction": 0.03}), rulebook.STATUS_PASSED)

    def test_sem_renderizacao_das_camadas_vale_a_tinta_do_png(self):
        self.assertEqual(self._regra({"rendered_ink_fraction": 0.001}), rulebook.STATUS_FAIL)
        self.assertEqual(self._regra({"rendered_ink_fraction": 0.2}), rulebook.STATUS_PASSED)
        self.assertEqual(self._regra({"layer_ink_fraction": 0.1}), rulebook.STATUS_PASSED)


@unittest.skipUnless(HAS_QGIS, "PyQGIS indisponível")
class AuditoriaDeLayoutNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _poligono(self, nome, x0, y0, lado):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", nome, "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, y0, x0 + lado, y0 + lado)))
        feature.setAttribute("nome", nome)
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _compor(self, pasta):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        from sigmai.cartography.compose import compose_map

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        parque = self._poligono("Parque", 480000, 9000000, 20000)
        vizinho = self._poligono("Vizinho", 470000, 8990000, 40000)
        resultado = compose_map({
            "layer_ids": [vizinho.id(), parque.id()], "subject_layer_id": parque.id(), "title": "Parque",
            "map_author": "T", "data_source": "teste", "layout_name": "E1 teste",
            "output_path": os.path.join(pasta, "m.png"), "format": "png", "dpi": 72,
        }, {"dry_run": False})
        layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
        return layout, parque

    def _auditar(self, layout, pasta, **extra):
        from qgis.core import QgsLayoutExporter

        from sigmai.qgis_actions.cartography_engine import audit_map_layout

        png = os.path.join(pasta, "estragado.png")
        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 72
        exporter.exportToImage(png, settings)
        return audit_map_layout({"layout_name": layout.name(), "output_path": png, **extra}, {"dry_run": False})

    def test_camadas_apagadas_do_quadro_reprovam_cart062(self):
        from qgis.core import QgsProject, QgsVectorLayer

        with pasta_temporaria() as pasta:
            layout, _ = self._compor(pasta)
            vazia = QgsVectorLayer("Polygon?crs=EPSG:31984", "Vazia", "memory")
            QgsProject.instance().addMapLayer(vazia, False)
            quadro = layout.itemById("main_map")
            quadro.setKeepLayerSet(True)
            quadro.setLayers([vazia])
            self.assertEqual(_status(self._auditar(layout, pasta), "CART062"), rulebook.STATUS_FAIL)

    def test_extensao_dos_dados_vem_da_receita_e_cart061_e_avaliada(self):
        from qgis.core import QgsRectangle

        with pasta_temporaria() as pasta:
            layout, _ = self._compor(pasta)
            self.assertEqual(_status(self._auditar(layout, pasta), "CART061"), rulebook.STATUS_PASSED)
            quadro = layout.itemById("main_map")
            e = quadro.extent()
            quadro.zoomToExtent(QgsRectangle(e.xMinimum() + e.width() * 5, e.yMinimum(), e.xMaximum() + e.width() * 5, e.yMaximum()))
            relatorio = self._auditar(layout, pasta)
            self.assertEqual(_status(relatorio, "CART061"), rulebook.STATUS_FAIL)
            self.assertEqual(_status(relatorio, "CART062"), rulebook.STATUS_FAIL)

    def test_subject_layer_id_explicito_vale_para_qualquer_layout(self):
        with pasta_temporaria() as pasta:
            layout, parque = self._compor(pasta)
            relatorio = self._auditar(layout, pasta, subject_layer_id=[parque.id()])
            self.assertEqual(_status(relatorio, "CART061"), rulebook.STATUS_PASSED)


if __name__ == "__main__":
    unittest.main()
