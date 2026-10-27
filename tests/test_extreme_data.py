"""Dados extremos: o que a bateria de casos extremos da 1.3.0 achou.

Depois do defeito dos pontos demais, a mesma pergunta foi feita a outros
extremos, compondo cada um pelo SIGMAI com o parque e os municípios reais do
Itatiaia. Saíram com nota A, ou com a causa calada:
- um MDE com um bloco de -32.768 sem "sem dado" declarado (relevo de uma cor
  só, legenda "-32.768 m") e outro com um pixel de 9.000 m;
- um mapa de calor com um foco de 20.000 registros, em que 300 registros
  espalhados sumiam;
- coordenadas em graus declaradas como UTM (escala 1:2, perto do polo) e um
  registro em 0,0 (o mapa virava o Atlântico);
- um mapa-múndi em graus com barra de escala métrica, que a própria auditoria
  reprovava;
- 20 mil polígonos pequenos fundidos num bloco pelo contorno.
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
from sigmai.qgis_actions.raster_style import NODATA_SENTINELS, robust_range  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _regra(rule_id):
    return next(rule for rule in rulebook.RULES if rule.id == rule_id)


class IntervaloRobusto(unittest.TestCase):
    def setUp(self):
        sorteio = random.Random(1)
        self.mde = [sorteio.uniform(372, 2793) for _ in range(20000)]

    def test_mde_limpo_fica_com_os_extremos(self):
        faixa = robust_range(self.mde)
        self.assertAlmostEqual(faixa["min"], min(self.mde))
        self.assertAlmostEqual(faixa["max"], max(self.mde))
        self.assertEqual((faixa["sentinels"], faixa["clipped"]), ([], {}))

    def test_sentinela_nao_declarado_sai_da_rampa(self):
        faixa = robust_range(self.mde + [-32768.0] * 5000)
        self.assertGreater(faixa["min"], 0)
        self.assertEqual(faixa["sentinels"], [(-32768.0, 5000)])

    def test_pico_isolado_fica_fora(self):
        faixa = robust_range(self.mde + [9000.0])
        self.assertLess(faixa["max"], 2800)
        self.assertEqual(faixa["clipped"], {"high": 9000.0})

    def test_sem_dado_declarado_e_descartado(self):
        faixa = robust_range(self.mde + [-9999.0] * 10, declared_nodata=-9999.0)
        self.assertEqual(faixa["sentinels"], [])
        self.assertGreater(faixa["min"], 0)

    def test_so_sentinela_recusa(self):
        with self.assertRaises(ValueError):
            robust_range([NODATA_SENTINELS[0]] * 10)


class ClassesQueColapsam(unittest.TestCase):
    """Contagens com muitos zeros: 5 classes por quantis viravam 1, sem aviso."""

    def test_quantis_com_muitos_zeros_avisam(self):
        from sigmai.qgis_actions.symbology import _class_breaks, collapsed_classes_warning

        valores = sorted([0] * 900 + [1] * 50 + [2, 3, 5, 8, 13, 40, 100] * 7)
        limites = _class_breaks(valores, 5, "quantile")
        aviso = collapsed_classes_warning(valores, 5, len(limites) - 1, "quantile")
        self.assertIn("saíram 1", aviso)
        self.assertIn("90%", aviso)
        self.assertIn("jenks", aviso)

    def test_classes_completas_nao_avisam(self):
        from sigmai.qgis_actions.symbology import collapsed_classes_warning

        self.assertEqual(collapsed_classes_warning([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 5, 5, "jenks"), "")


class RegrasNovas(unittest.TestCase):
    def test_cart077_rampa_esticada(self):
        rampa = {"layer": "MDE", "renderer": "singlebandpseudocolor", "ramp_min": -32768, "ramp_max": 2764,
                 "p02": 420, "p98": 2680, "data_min": 372, "data_max": 2764, "used_fraction": 0.0636}
        resultado = _regra("CART077").check({"map": {"raster_ramps": [rampa]}})
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("-32.768", resultado.detail_pt)
        self.assertEqual(_regra("CART077").check({"map": {"raster_ramps": [{**rampa, "used_fraction": 0.9}]}}).status,
                         rulebook.STATUS_PASSED)
        self.assertEqual(_regra("CART077").check({"map": {"raster_ramps": []}}).status, rulebook.STATUS_SKIP)

    def test_cart078_graus_como_utm(self):
        obs = {"map": {"coordinate_checks": [{"layer": "R", "crs": "EPSG:31983", "features": 200, "degree_like": True,
                                              "outside_area_of_use": 200, "null_island": 0}]}}
        resultado = _regra("CART078").check(obs)
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("parecem graus", resultado.detail_pt)
        self.assertEqual(_regra("CART078").severity, rulebook.SEVERITY_ERROR)

    def test_cart078_ilha_nula_e_fora_da_area(self):
        obs = {"map": {"coordinate_checks": [{"layer": "R", "crs": "EPSG:4674", "features": 501, "degree_like": False,
                                              "null_island": 1, "outside_area_of_use": 1,
                                              "outside_examples": [[0.0, 0.0]], "area_of_use": [-122.2, -59.9, -25.3, 32.7]}]}}
        resultado = _regra("CART078").check(obs)
        self.assertIn("0,0", resultado.detail_pt)
        self.assertIn("fora da área de uso", resultado.detail_pt)

    def test_cart078_coordenadas_limpas(self):
        obs = {"map": {"coordinate_checks": [{"layer": "R", "crs": "EPSG:4674", "features": 10, "degree_like": False,
                                              "null_island": 0, "outside_area_of_use": 0}]}}
        self.assertEqual(_regra("CART078").check(obs).status, rulebook.STATUS_PASSED)

    def test_cart079_pontos_isolados(self):
        isolado = {"layer": "R", "points": 501, "isolated": 1, "core_diagonal": 25000, "full_diagonal": 5_000_000,
                   "spread_ratio": 200.0}
        self.assertEqual(_regra("CART079").check({"map": {"extent_outliers": [isolado]}}).status, rulebook.STATUS_FAIL)
        espalhados = {**isolado, "points": 20300, "isolated": 300}
        self.assertEqual(_regra("CART079").check({"map": {"extent_outliers": [espalhados]}}).status,
                         rulebook.STATUS_PASSED)
        bimodal = {**isolado, "isolated": 200}
        self.assertEqual(_regra("CART079").check({"map": {"extent_outliers": [bimodal]}}).status, rulebook.STATUS_PASSED)
        compacto = {**isolado, "spread_ratio": 1.3}
        self.assertEqual(_regra("CART079").check({"map": {"extent_outliers": [compacto]}}).status, rulebook.STATUS_PASSED)

    def test_cart080_foco_dominante(self):
        calor = {"layer": "R", "radius_mm": 3, "places": 250, "faint_places": 249, "faint_points": 300,
                 "points": 20300, "peak": 20000, "max_value_fixed": False}
        resultado = _regra("CART080").check({"map": {"heatmap_visibility": [calor]}})
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("max_value", _regra("CART080").fix_pt)
        # Focos de calor do INPE no Piauí: 55 % dos lugares abaixo de 2 % do pico, mapa legítimo.
        queimadas = {**calor, "places": 613, "faint_places": 337}
        self.assertEqual(_regra("CART080").check({"map": {"heatmap_visibility": [queimadas]}}).status,
                         rulebook.STATUS_PASSED)
        equilibrado = {**calor, "faint_places": 20}
        self.assertEqual(_regra("CART080").check({"map": {"heatmap_visibility": [equilibrado]}}).status,
                         rulebook.STATUS_PASSED)


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

    def _camada(self, tipo, crs, nome, wkts):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        layer = QgsVectorLayer(f"{tipo}?crs={crs}", nome, "memory")
        feats = []
        for wkt in wkts:
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            feats.append(feature)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _mde(self, pasta, defeito=None):
        from osgeo import gdal, osr  # type: ignore
        from qgis.core import QgsProject, QgsRasterLayer

        caminho = os.path.join(pasta, "mde.tif")
        ds = gdal.GetDriverByName("GTiff").Create(caminho, 120, 100, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((520000, 200, 0, 7535000, 0, -200))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(31983)
        ds.SetProjection(srs.ExportToWkt())
        import struct

        valores = [400.0 + 20.0 * r + 3.0 * c for r in range(100) for c in range(120)]
        if defeito == "sentinela":
            valores = [-32768.0 if (i // 120) < 25 and (i % 120) < 40 else v for i, v in enumerate(valores)]
        elif defeito == "pico":
            valores[50 * 120 + 60] = 9000.0
        ds.GetRasterBand(1).WriteRaster(0, 0, 120, 100, struct.pack("f" * 12000, *valores))
        ds = None
        layer = QgsRasterLayer(caminho, "Elevation")
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _compor(self, pasta, layers, subject, nome="m", **extra):
        from sigmai.cartography.compose import compose_map

        params = {"layer_ids": [layer.id() for layer in layers], "subject_layer_id": [s.id() for s in subject],
                  "title": "T", "map_author": "T", "data_source": "teste", "map_language": "pt-BR",
                  "output_path": os.path.join(pasta, f"{nome}.png"), "format": "png", "dpi": 72, "page": "A5",
                  "orientation": "landscape", "layout_name": nome}
        params.update(extra)
        return compose_map(params, {"dry_run": False})

    @staticmethod
    def _status(resultado, rule_id):
        return next(r for r in resultado["audit"]["results"] if r["id"] == rule_id)["status"]

    def test_mde_com_sentinela_vira_sem_dado(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            mde = self._mde(pasta, "sentinela")
            plano = apply_raster_style({"layer_id": mde.id(), "unit": "m"}, {"dry_run": False})
            self.assertEqual(plano["assumed_nodata"], [-32768.0])
            self.assertGreater(plano["min"], 0)
            self.assertTrue(mde.dataProvider().userNoDataValues(1))
            resultado = self._compor(pasta, [mde], [mde])
            self.assertEqual(self._status(resultado, "CART077"), rulebook.STATUS_PASSED)

    def test_rampa_esticada_a_mao_e_acusada(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            mde = self._mde(pasta, "sentinela")
            apply_raster_style({"layer_id": mde.id(), "min": -32768, "max": 2764}, {"dry_run": False})
            resultado = self._compor(pasta, [mde], [mde])
            self.assertEqual(self._status(resultado, "CART077"), rulebook.STATUS_FAIL)

    def test_relevo_reamostrado_na_leitura(self):
        """Sombreamento e hipsometria com reamostragem bilinear no provedor; classes continuam no vizinho mais próximo."""
        from qgis.core import QgsRasterLayer

        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            mde = self._mde(pasta)
            sombra = QgsRasterLayer(mde.source(), "Sombreamento")
            classes = QgsRasterLayer(mde.source(), "Classes")
            apply_raster_style({"layer_id": mde.id(), "unit": "m"}, {"dry_run": False})
            from qgis.core import QgsProject

            QgsProject.instance().addMapLayers([sombra, classes])
            apply_raster_style({"layer_id": sombra.id(), "mode": "hillshade"}, {"dry_run": False})
            apply_raster_style({"layer_id": classes.id(), "mode": "classes", "breaks": [400, 1000, 2000, 3000]},
                               {"dry_run": False})
            for camada in (mde, sombra):
                self.assertTrue(camada.dataProvider().isProviderResamplingEnabled(), camada.name())
                self.assertNotEqual(int(camada.dataProvider().zoomedInResamplingMethod()), 0, camada.name())
            self.assertFalse(classes.dataProvider().isProviderResamplingEnabled())

    def test_rotulos_quebrados_de_classes_de_raster_ficam_na_propria_classe(self):
        """A legenda de um raster de classes esconde "Band 1"; o rótulo quebrado caía na classe anterior."""
        import struct

        from osgeo import gdal, osr  # type: ignore
        from qgis.core import QgsLayoutItemLegend, QgsProject, QgsRasterLayer

        from sigmai.qgis_actions.raster_style import apply_raster_style

        nomes = {"10": "Tree cover", "20": "Shrubland", "30": "Grassland", "40": "Cropland", "50": "Built-up",
                 "60": "Bare or sparse vegetation", "80": "Permanent water bodies", "90": "Herbaceous wetland"}
        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "cobertura.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 80, 60, 1, gdal.GDT_Byte)
            ds.SetGeoTransform((520000, 300, 0, 7535000, 0, -300))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(31983)
            ds.SetProjection(srs.ExportToWkt())
            valores = [int(sorted(nomes)[(c // 10) % len(nomes)]) for _ in range(60) for c in range(80)]
            ds.GetRasterBand(1).WriteRaster(0, 0, 80, 60, struct.pack("B" * 4800, *valores))
            ds = None
            camada = QgsRasterLayer(caminho, "Land cover")
            QgsProject.instance().addMapLayer(camada)
            apply_raster_style({"layer_id": camada.id(), "mode": "unique_values", "labels": nomes, "map_language": "en"},
                               {"dry_run": False})
            resultado = self._compor(pasta, [camada], [camada], figure_width_mm=88, map_language="en",
                                     title_placement="caption", data_source="ESA WorldCover")
            layout = QgsProject.instance().layoutManager().layoutByName("m")
            legenda = next(i for i in layout.items() if isinstance(i, QgsLayoutItemLegend))
            no = legenda.model().rootGroup().findLayer(camada.id())
            mostrados = [" ".join(str(n.data(0)).replace("~", " ").split()) for n in legenda.model().layerLegendNodes(no)]
        self.assertEqual(mostrados, [nomes[k] for k in sorted(nomes)], resultado["notes"])

    def test_pico_isolado_fica_fora_da_rampa(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            mde = self._mde(pasta, "pico")
            plano = apply_raster_style({"layer_id": mde.id(), "unit": "m"}, {"dry_run": False})
            self.assertLess(plano["max"], 9000)
            self.assertTrue(any("Pico isolado" in nota for nota in plano.get("notes", [])))

    def test_graus_declarados_como_utm(self):
        sorteio = random.Random(2)
        pontos = self._camada("Point", "EPSG:31983", "R",
                              [f"POINT({sorteio.uniform(-44.8, -44.5)} {sorteio.uniform(-22.5, -22.2)})" for _ in range(50)])
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos])
        self.assertEqual(self._status(resultado, "CART078"), rulebook.STATUS_FAIL)

    def test_registro_em_zero_zero(self):
        sorteio = random.Random(3)
        wkts = [f"POINT({sorteio.uniform(-44.8, -44.5)} {sorteio.uniform(-22.5, -22.2)})" for _ in range(200)] + ["POINT(0 0)"]
        pontos = self._camada("Point", "EPSG:4674", "R", wkts)
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos])
        self.assertEqual(self._status(resultado, "CART078"), rulebook.STATUS_FAIL)
        self.assertEqual(self._status(resultado, "CART079"), rulebook.STATUS_FAIL)

    def test_pontos_limpos_passam_nas_regras_de_coordenada(self):
        sorteio = random.Random(4)
        pontos = self._camada("Point", "EPSG:4674", "R",
                              [f"POINT({sorteio.uniform(-44.8, -44.5)} {sorteio.uniform(-22.5, -22.2)})" for _ in range(200)])
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos])
        self.assertEqual(self._status(resultado, "CART078"), rulebook.STATUS_PASSED)
        self.assertEqual(self._status(resultado, "CART079"), rulebook.STATUS_PASSED)

    def test_mapa_mundi_em_graus_sem_barra_metrica(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        sorteio = random.Random(5)
        pontos = self._camada("Point", "EPSG:4326", "R",
                              [f"POINT({sorteio.uniform(-170, 170)} {sorteio.uniform(-55, 70)})" for _ in range(100)])
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos])
            from qgis.core import QgsLayoutItemMap

            layout = QgsProject.instance().layoutManager().layoutByName("m")
            mapa = max((i for i in layout.items() if isinstance(i, QgsLayoutItemMap)), key=lambda m: m.rect().width())
            rotulos = {(eixo, valor): self._rotulo(mapa.grid().annotationExpression(), eixo, valor)
                       for eixo, valor in (("x", -210), ("x", -180), ("x", 30), ("y", 90), ("y", -120))}
        self.assertNotIn("scale_bar", resultado["items_created"])
        self.assertNotEqual(self._status(resultado, "CART024"), rulebook.STATUS_FAIL)
        self.assertEqual(self._status(resultado, "CART003"), rulebook.STATUS_PASSED)
        self.assertEqual(rotulos, {("x", -210): "", ("x", -180): "-180°", ("x", 30): "30°", ("y", 90): "90°",
                                   ("y", -120): ""})

    @staticmethod
    def _rotulo(expressao, eixo, valor):
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextScope

        escopo = QgsExpressionContextScope()
        escopo.setVariable("grid_axis", eixo)
        escopo.setVariable("grid_number", float(valor))
        contexto = QgsExpressionContext()
        contexto.appendScope(escopo)
        return QgsExpression(expressao).evaluate(contexto)

    def test_rotulo_em_graus_usa_o_separador_da_lingua(self):
        from sigmai.cartography.compose import _degree_label_expression

        self.assertEqual(self._rotulo(_degree_label_expression(1, ","), "y", -22.5), "-22,5°")
        self.assertEqual(self._rotulo(_degree_label_expression(1, "."), "y", -22.0), "-22.0°")
        self.assertEqual(self._rotulo(_degree_label_expression(3, ","), "x", -44.0833333333), "-44,083°")

    def test_poligonos_pequenos_ganham_contorno_fino(self):
        lado = 150
        wkts = [f"POLYGON(({x} {y},{x + lado} {y},{x + lado} {y + lado},{x} {y + lado},{x} {y}))"
                for x in range(520000, 535000, lado) for y in range(7520000, 7530000, lado)]
        imoveis = self._camada("Polygon", "EPSG:31983", "Imoveis", wkts)
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [imoveis], [imoveis])
            largura = imoveis.renderer().symbol().symbolLayer(0).strokeWidth()
        self.assertLess(largura, 0.2)
        self.assertTrue(any("engolia o preenchimento" in nota for nota in resultado["notes"]), resultado["notes"])

    def test_poligonos_grandes_mantem_o_contorno(self):
        from sigmai.cartography.symbology import GEOMETRY_DEFAULTS

        wkts = [f"POLYGON(({x} 7520000,{x + 4000} 7520000,{x + 4000} 7524000,{x} 7524000,{x} 7520000))"
                for x in range(520000, 540000, 4000)]
        lotes = self._camada("Polygon", "EPSG:31983", "Lotes", wkts * 12)
        with pasta_temporaria() as pasta:
            self._compor(pasta, [lotes], [lotes])
            largura = lotes.renderer().symbol().symbolLayer(0).strokeWidth()
        self.assertAlmostEqual(largura, GEOMETRY_DEFAULTS["Polygon"]["stroke_width"])

    def test_rotulos_demais_sao_recusados(self):
        from sigmai.cartography.compose import MAX_LABELLED_FEATURES, CompositionError
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer("Point?crs=EPSG:31983&field=nome:string(10)", "R", "memory")
        feats = []
        for i in range(MAX_LABELLED_FEATURES + 1):
            f = QgsFeature(camada.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(520000 + i, 7520000 + (i % 97) * 50)))
            f.setAttribute(0, f"R{i}")
            feats.append(f)
        camada.dataProvider().addFeatures(feats)
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        with pasta_temporaria() as pasta:
            with self.assertRaises(CompositionError) as erro:
                self._compor(pasta, [camada], [camada], label_field="nome")
        self.assertIn("extract_by_expression", str(erro.exception))

    def test_mapa_de_calor_com_foco_dominante(self):
        from sigmai.qgis_actions.symbology import apply_heatmap_style

        sorteio = random.Random(6)
        wkts = ["POINT(532000 7525000)"] * 20000 + [f"POINT({sorteio.uniform(520000, 545000)} {sorteio.uniform(7514000, 7536000)})"
                                                     for _ in range(300)]
        pontos = self._camada("Point", "EPSG:31983", "R", wkts)
        apply_heatmap_style({"layer_id": pontos.id(), "radius": 3}, {"dry_run": False})
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos])
        self.assertEqual(self._status(resultado, "CART080"), rulebook.STATUS_FAIL)

    def test_poligono_assunto_sobre_mapa_de_calor_vira_contorno(self):
        from qgis.PyQt.QtCore import Qt

        from sigmai.cartography.qtcompat import qt_enum
        from sigmai.qgis_actions.symbology import apply_heatmap_style

        sorteio = random.Random(7)
        pontos = self._camada("Point", "EPSG:31983", "R",
                              [f"POINT({sorteio.uniform(522000, 543000)} {sorteio.uniform(7516000, 7534000)})" for _ in range(3000)])
        parque = self._camada("Polygon", "EPSG:31983", "Parque",
                              ["POLYGON((520000 7514000,545000 7514000,545000 7536000,520000 7536000,520000 7514000))"])
        apply_heatmap_style({"layer_id": pontos.id(), "radius": 3}, {"dry_run": False})
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos, parque], [pontos, parque])
            pincel = parque.renderer().symbol().symbolLayer(0).brushStyle()
        self.assertEqual(pincel, qt_enum(Qt, "BrushStyle", "NoBrush"))
        self.assertEqual(self._status(resultado, "CART075"), rulebook.STATUS_PASSED)

    def _mundo(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsProject

        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        sorteio = random.Random(5)
        return self._camada("Point", "EPSG:4326", "R",
                            [f"POINT({sorteio.uniform(-170, 170)} {sorteio.uniform(-55, 70)})" for _ in range(100)])

    def _grade(self, nome="m"):
        from qgis.core import QgsLayoutItemMap, QgsProject

        layout = QgsProject.instance().layoutManager().layoutByName(nome)
        return max((i for i in layout.items() if isinstance(i, QgsLayoutItemMap)), key=lambda m: m.rect().width()).grid()

    def test_mapa_mundi_automatico_em_equal_earth(self):
        pontos = self._mundo()
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos], map_crs="auto")
            grade = self._grade()
            self.assertTrue(grade.crs().isGeographic())
            self.assertFalse(grade.annotationEnabled())
        self.assertEqual(resultado["map_crs"], "EPSG:8857")
        self.assertNotIn("scale_bar", resultado["items_created"])
        self.assertNotIn("north_arrow", resultado["items_created"])
        self.assertEqual(resultado["audit"]["grade"], "A")
        for regra in ("CART060", "CART064", "CART006", "CART008"):
            self.assertNotEqual(self._status(resultado, regra), rulebook.STATUS_FAIL, regra)

    def test_mapa_mundi_sem_auto_continua_em_graus(self):
        pontos = self._mundo()
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos])
        self.assertEqual(resultado["map_crs"], "EPSG:4326")
        self.assertTrue(any('map_crs="auto"' in nota for nota in resultado["notes"]), resultado["notes"])

    def test_continente_automatico_em_lambert_com_latitude_nas_laterais(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsLayoutItemLabel, QgsLayoutItemMapGrid, QgsProject

        from sigmai.cartography.qtcompat import qt_enum

        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        sorteio = random.Random(8)
        pontos = self._camada("Point", "EPSG:4326", "R",
                              [f"POINT({sorteio.uniform(-80, -35)} {sorteio.uniform(-55, 12)})" for _ in range(200)])
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos], [pontos], map_crs="auto", map_language="en")
            grade = self._grade()
            esquerda = grade.annotationDisplay(qt_enum(QgsLayoutItemMapGrid, "BorderSide", "Left"))
            baixo = grade.annotationDisplay(qt_enum(QgsLayoutItemMapGrid, "BorderSide", "Bottom"))
            layout = QgsProject.instance().layoutManager().layoutByName("m")
            textos = " ".join(i.text() for i in layout.items() if isinstance(i, QgsLayoutItemLabel))
        self.assertIn("Lambert", resultado["map_crs"])
        self.assertEqual(esquerda, qt_enum(QgsLayoutItemMapGrid, "DisplayMode", "LatitudeOnly"))
        self.assertEqual(baixo, qt_enum(QgsLayoutItemMapGrid, "DisplayMode", "LongitudeOnly"))
        self.assertIn("WGS 84 / Lambert Azimuthal Equal Area", textos)
        self.assertIn("scale_bar", resultado["items_created"])
        self.assertNotIn("north_arrow", resultado["items_created"])
        self.assertEqual(self._status(resultado, "CART008"), rulebook.STATUS_PASSED)

    def test_classes_demais_ficam_as_mais_frequentes(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        from sigmai.qgis_actions.symbology import apply_categorized_style

        camada = QgsVectorLayer("Point?crs=EPSG:31983&field=classe:string(10)", "C", "memory")
        feats = []
        valores = ["A"] + [f"M{i:02d}" for i in range(30)] * 2 + ["Z"] * 50
        for i, valor in enumerate(valores):
            f = QgsFeature(camada.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(520000 + i * 10, 7520000)))
            f.setAttribute(0, valor)
            feats.append(f)
        camada.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(camada)
        plano = apply_categorized_style({"layer_id": camada.id(), "field_name": "classe", "limit": 12}, {"dry_run": True})
        self.assertIn("Z", plano["values"])
        self.assertNotIn("A", plano["values"])
        self.assertEqual(len(plano["values"]), 12)
        self.assertTrue(any("menos frequentes" in aviso for aviso in plano["warnings"]))


if __name__ == "__main__":
    unittest.main()
