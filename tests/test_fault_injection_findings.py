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



class RotulosDaBarra(unittest.TestCase):
    """Figura de coluna (E1): '25 0 25 50 75 100 km' em 12,5 mm virava '25 0 255075100 km'."""

    def test_selecao_de_segmentos_respeita_a_largura_dos_numeros(self):
        from sigmai.cartography.scaling import scalebar_labels_fit, scalebar_spec

        sem_fonte = scalebar_spec(10_000_000, 45, max_width_mm=30)
        com_fonte = scalebar_spec(10_000_000, 45, max_width_mm=30, label_font_pt=6.0)
        self.assertFalse(scalebar_labels_fit(sem_fonte.units_per_segment, sem_fonte.segments_right,
                                             sem_fonte.segments_left, sem_fonte.bar_width_mm, 6.0))
        self.assertTrue(scalebar_labels_fit(com_fonte.units_per_segment, com_fonte.segments_right,
                                            com_fonte.segments_left, com_fonte.bar_width_mm, 6.0))

    def test_cart074(self):
        regra = next(rule for rule in rulebook.RULES if rule.id == "CART074")
        apertada = {"scalebar": {"item_id": "s", "label_font_pt": 6.0, "bar_width_mm": 12.5,
                                 "units_per_segment": 25, "segments": 4, "segments_left": 1}}
        folgada = {"scalebar": {"item_id": "s", "label_font_pt": 6.0, "bar_width_mm": 10.0,
                                "units_per_segment": 50, "segments": 2, "segments_left": 0}}
        self.assertEqual(regra.check(apertada).status, rulebook.STATUS_FAIL)
        self.assertEqual(regra.check(folgada).status, rulebook.STATUS_PASSED)
        self.assertEqual(regra.check({"scalebar": None}).status, rulebook.STATUS_SKIP)


class CamadaCobertaNaLegenda(unittest.TestCase):
    def test_camada_ligada_mas_coberta_e_fantasma(self):
        observacao = {"legend": {"item_id": "legend", "layer_names": ["Estado", "Municipios"]},
                      "map": {"visible_layer_names": ["Estado", "Municipios"], "hidden_layer_names": ["Municipios"]},
                      "map_frames": [{"item_id": "main_map"}]}
        resultado = rulebook._check_legend_has_no_phantoms(observacao)
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertEqual(resultado.evidence["covered_layers"], ["Municipios"])

    def test_em_folha_de_paineis_nao_acusa(self):
        observacao = {"legend": {"item_id": "legend", "layer_names": ["A"]},
                      "map": {"visible_layer_names": ["A"], "hidden_layer_names": ["A"]},
                      "map_frames": [{"item_id": "main_map"}, {"item_id": "comparison_map"}]}
        self.assertEqual(rulebook._check_legend_has_no_phantoms(observacao).status, rulebook.STATUS_PASSED)


@unittest.skipUnless(HAS_QGIS, "PyQGIS indisponível")
class OrdemDeDesenhoNoQgis(unittest.TestCase):
    """O estado listado antes dos municípios os cobria inteiros e o laudo dava A."""

    _poligono = AuditoriaDeLayoutNoQgis._poligono
    _compor = AuditoriaDeLayoutNoQgis._compor
    _auditar = AuditoriaDeLayoutNoQgis._auditar

    @classmethod
    def setUpClass(cls):
        AuditoriaDeLayoutNoQgis.setUpClass.__func__(cls)

    def _camada(self, nome, retangulos):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", nome, "memory")
        feicoes = []
        for indice, (x0, y0, x1, y1) in enumerate(retangulos):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, y0, x1, y1)))
            feature.setAttribute("nome", f"{nome} {indice + 1}")
            feicoes.append(feature)
        layer.dataProvider().addFeatures(feicoes)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_estado_vira_contorno_por_cima_e_municipios_aparecem(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        from sigmai.cartography.compose import compose_map

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        estado = self._camada("Estado", [(400000, 9000000, 600000, 9200000)])
        municipios = self._camada("Municipios", [(400000, 9000000, 500000, 9200000), (500000, 9000000, 600000, 9200000)])
        with pasta_temporaria() as pasta:
            resultado = compose_map({
                "layer_ids": [estado.id(), municipios.id()], "subject_layer_id": estado.id(), "title": "Estado",
                "map_author": "T", "data_source": "teste", "output_path": os.path.join(pasta, "m.png"),
                "format": "png", "dpi": 72,
            }, {"dry_run": False})
            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            quadro = layout.itemById("main_map")
            self.assertEqual([layer.name() for layer in quadro.layers()], ["Estado", "Municipios"])
            from qgis.PyQt.QtCore import Qt

            simbolo = estado.renderer().symbol().symbolLayer(0)
            self.assertEqual(simbolo.brushStyle(), getattr(getattr(Qt, "BrushStyle", Qt), "NoBrush"))  # só contorno
            regras = {r["id"]: r["status"] for r in resultado["audit"]["results"]}
            self.assertEqual(regras["CART021"], rulebook.STATUS_PASSED)
            self.assertEqual(resultado["audit"]["observation"]["map"]["hidden_layer_names"], [])

    def _divisas(self, pasta):
        """Estados (25) e municípios (100) que coincidem nas divisas, um parque e o relevo sombreado embaixo."""
        import numpy
        from osgeo import gdal, osr
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer

        from sigmai.cartography.compose import compose_map
        from sigmai.qgis_actions.raster_style import apply_raster_style

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        x0, y0 = 400000, 9000000
        estados = self._camada("Estados", [(x0 + i * 40000, y0 + j * 40000, x0 + (i + 1) * 40000, y0 + (j + 1) * 40000)
                                           for i in range(5) for j in range(5)])
        municipios = self._camada("Municipios", [(x0 + i * 20000, y0 + j * 20000, x0 + (i + 1) * 20000, y0 + (j + 1) * 20000)
                                                 for i in range(10) for j in range(10)])
        parque = self._camada("Parque", [(x0 + 70000, y0 + 70000, x0 + 110000, y0 + 100000)])
        caminho = os.path.join(pasta, "dem.tif")
        ds = gdal.GetDriverByName("GTiff").Create(caminho, 100, 100, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((x0, 2000, 0, y0 + 200000, 0, -2000))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(31984)
        ds.SetProjection(srs.ExportToWkt())
        linhas, colunas = numpy.mgrid[0:100, 0:100]
        ds.GetRasterBand(1).WriteArray((numpy.sin(linhas / 7.0) * numpy.cos(colunas / 9.0) * 800 + 1200).astype("float32"))
        ds = None
        relevo = QgsRasterLayer(caminho, "Relevo")
        QgsProject.instance().addMapLayer(relevo)
        apply_raster_style({"layer_id": relevo.id(), "mode": "hillshade"}, {"dry_run": False})
        resultado = compose_map({
            "layer_ids": [parque.id(), municipios.id(), estados.id(), relevo.id()], "subject_layer_id": parque.id(),
            "title": "Parque", "map_author": "T", "data_source": "teste", "margin_percent": 60, "include_inset": True,
            "output_path": os.path.join(pasta, "m.png"), "format": "png", "dpi": 72,
        }, {"dry_run": False})
        return resultado, estados, municipios

    def test_divisa_coberta_e_fantasma_na_legenda(self):
        """Com a correção desligada, a divisa estadual fica sob a municipal: 44 % "à vista" pela medida antiga,
        a lasca ao lado do traço preto, e CART021 passava; a legenda mostrava uma linha que o mapa não tinha."""
        from unittest import mock

        from qgis.core import QgsProject

        with pasta_temporaria() as pasta, mock.patch("sigmai.cartography.compose._outline_parent_ids", return_value=set()):
            resultado, _estados, _municipios = self._divisas(pasta)
            ordem = [layer.name() for layer in QgsProject.instance().layoutManager()
                     .layoutByName(resultado["layout_name"]).itemById("main_map").layers()]
        self.assertLess(ordem.index("Municipios"), ordem.index("Estados"), ordem)
        cart021 = next(r for r in resultado["audit"]["results"] if r["id"] == "CART021")
        self.assertEqual(cart021["status"], rulebook.STATUS_FAIL)
        self.assertIn("Estados", cart021["evidence"]["covered_layers"])
        self.assertIn("mais grossa", cart021["detail_pt"])

    def test_contorno_grosso_cruzado_por_linhas_finas_nao_e_fantasma(self):
        """Bateria de mapas (m21): o contorno de 0,7 mm do parque sob curvas de nível de 0,25 mm, densas, passou
        a contar como coberto quando todo traço de cima cobria a vizinhança; ele continua legível."""
        from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsFillSymbol, QgsGeometry, QgsLineSymbol,
                               QgsPointXY, QgsProject, QgsSingleSymbolRenderer, QgsVectorLayer)

        from sigmai.cartography.compose import compose_map

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        x0, y0 = 400000, 9000000
        parque = self._camada("Parque", [(x0 + 10000, y0 + 10000, x0 + 30000, y0 + 30000)])
        parque.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "0,0,0,0", "style": "no", "outline_color": "#333333", "outline_width": "0.7"})))
        curvas = QgsVectorLayer("LineString?crs=EPSG:31984", "Curvas", "memory")
        feicoes = []
        for indice in range(270):
            feicao = QgsFeature()
            y = y0 + indice * 150
            feicao.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x0, y), QgsPointXY(x0 + 40000, y + 3000)]))
            feicoes.append(feicao)
        curvas.dataProvider().addFeatures(feicoes)
        curvas.updateExtents()
        curvas.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"line_color": "#8C510A", "line_width": "0.25"})))
        QgsProject.instance().addMapLayer(curvas)
        with pasta_temporaria() as pasta:
            resultado = compose_map({
                "layer_ids": [curvas.id(), parque.id()], "title": "Curvas", "map_author": "T", "data_source": "teste",
                "apply_style": "none", "output_path": os.path.join(pasta, "c.png"), "format": "png", "dpi": 72,
            }, {"dry_run": False})
        cart021 = next(r for r in resultado["audit"]["results"] if r["id"] == "CART021")
        self.assertEqual(cart021["status"], rulebook.STATUS_PASSED, cart021["detail_pt"])

    def test_divisa_estadual_por_cima_da_municipal(self):
        """Mapa de localização do Itatiaia (1.4): estados e municípios viravam contorno com o mesmo traço fino,
        os municípios por cima, e a divisa estadual que a legenda mostrava sumia no mapa."""
        from qgis.core import QgsProject

        from sigmai.cartography.symbology import OUTLINE_STROKE_MM, OUTLINE_SUBDIVISION_STROKE_MM

        with pasta_temporaria() as pasta:
            resultado, estados, municipios = self._divisas(pasta)
            cart021 = next(r for r in resultado["audit"]["results"] if r["id"] == "CART021")
            self.assertEqual(cart021["status"], rulebook.STATUS_PASSED, cart021["detail_pt"])
            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            ordem = [layer.name() for layer in layout.itemById("main_map").layers()]
            self.assertLess(ordem.index("Estados"), ordem.index("Municipios"), ordem)
            self.assertAlmostEqual(estados.renderer().symbol().symbolLayer(0).strokeWidth(), OUTLINE_STROKE_MM)
            self.assertAlmostEqual(municipios.renderer().symbol().symbolLayer(0).strokeWidth(), OUTLINE_SUBDIVISION_STROKE_MM)
            # No inserto a divisa afina: a 0,7 mm o país inteiro virava um borrão.
            from sigmai.cartography.compose import INSET_OUTLINE_MAX_MM

            import xml.etree.ElementTree as ET

            qml = layout.itemById("inset_map").layerStyleOverrides()[estados.id()]
            larguras = [float(option.get("value")) for option in ET.fromstring(qml.split("\n", 1)[1]).iter("Option")
                        if option.get("name") == "outline_width"]
            self.assertTrue(larguras)
            self.assertLessEqual(max(larguras), INSET_OUTLINE_MAX_MM)

    def test_auditoria_acusa_poligono_opaco_que_cobre_outro(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsFillSymbol, QgsProject, QgsSingleSymbolRenderer

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        with pasta_temporaria() as pasta:
            layout, parque = self._compor(pasta)
            vizinho = next(l for l in QgsProject.instance().mapLayers().values() if l.name() == "Vizinho")
            vizinho.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "#808080"})))
            quadro = layout.itemById("main_map")
            quadro.setKeepLayerSet(True)
            quadro.setLayers([vizinho, parque])  # o vizinho, maior e opaco, por cima do parque
            relatorio = self._auditar(layout, pasta)
            fantasma = next(r for r in relatorio["results"] if r["id"] == "CART021")
            self.assertEqual(fantasma["status"], rulebook.STATUS_FAIL)
            self.assertIn("Parque", relatorio["observation"]["map"]["hidden_layer_names"])


    def test_lasca_de_contorno_na_borda_nao_salva_a_camada_coberta(self):
        """F26 do E1: o estado opaco por cima, e o contorno largo dos municípios escapando na borda."""
        from qgis.core import (
            QgsCoordinateReferenceSystem, QgsFillSymbol, QgsLayoutExporter, QgsProject, QgsSingleSymbolRenderer,
        )

        from sigmai.cartography.compose import compose_map
        from sigmai.qgis_actions.cartography_engine import audit_map_layout

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        estado = self._camada("Estado", [(400000, 9000000, 600000, 9200000)])
        municipios = self._camada("Municipios", [(400000, 9000000, 500000, 9200000), (500000, 9000000, 600000, 9200000)])
        with pasta_temporaria() as pasta:
            resultado = compose_map({
                "layer_ids": [estado.id(), municipios.id()], "subject_layer_id": estado.id(), "title": "Estado",
                "map_author": "T", "data_source": "teste", "output_path": os.path.join(pasta, "m.png"),
                "format": "png", "dpi": 72,
            }, {"dry_run": False})
            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            estado.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({"color": "#9A9A9A", "outline_width": "0.1"})))
            municipios.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
                {"color": "#E8B07A", "outline_color": "#D55E00", "outline_width": "1.0"})))
            # Rótulos nos municípios cobertos: o motor os desenha por cima de tudo,
            # mas a legenda mostra o símbolo, não os nomes (B6 do E1).
            from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling

            from qgis.core import QgsTextFormat

            rotulos = QgsPalLayerSettings()
            rotulos.fieldName = "nome"
            formato = QgsTextFormat()
            formato.setSize(60)  # nomes grandes: no A3 do E1 eram 224, e somavam mais que a lasca
            rotulos.setFormat(formato)
            municipios.setLabeling(QgsVectorLayerSimpleLabeling(rotulos))
            municipios.setLabelsEnabled(True)
            quadro = layout.itemById("main_map")
            quadro.setKeepLayerSet(True)
            quadro.setLayers([estado, municipios])
            png = os.path.join(pasta, "coberto.png")
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = 72
            QgsLayoutExporter(layout).exportToImage(png, settings)
            relatorio = audit_map_layout({"layout_name": layout.name(), "output_path": png}, {"dry_run": False})
            mapa = relatorio["observation"]["map"]
            self.assertGreater(mapa["layer_visible_fraction"]["Municipios"], 0.0)  # a lasca existe
            self.assertIn("Municipios", mapa["hidden_layer_names"])
            self.assertEqual(next(r for r in relatorio["results"] if r["id"] == "CART021")["status"], rulebook.STATUS_FAIL)


if __name__ == "__main__":
    unittest.main()
