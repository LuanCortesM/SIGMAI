"""Mapas de pontos com muitos registros: símbolo do compositor, CART076 e símbolo por local.

A base B5 do experimento E1 (362.210 registros do GBIF no PARNA do Itatiaia)
saiu do compositor com pontos de 2,2 mm, opacos, cobrindo o parque; com
10.000 registros a nota era A, embora 98 % deles caíssem sobre outros. Estes
testes fixam o que a 1.3.0 passou a fazer: o compositor ajusta o símbolo de
ponto da paleta, CART076 acusa registros escondidos, count_points_by_site e
apply_proportional_symbol_style mostram a contagem, e o mapa de calor deixa
o contexto como contorno, como um raster. Depois, os locais passaram a ser
agrupados na escala do mapa, e CART076 a medir também os círculos
proporcionais: a 1:300.000, os 11.224 locais do Itatiaia se amontoavam.
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
from sigmai.cartography.pointdensity import (  # noqa: E402
    DENSE_ONLY_FROM_STEP, POINT_SYMBOL_STEPS, STACKING_HIDDEN_MAX, STACKING_MIN_POINTS, choose_point_symbol,
    merge_sites, saturation_depth, stacking,
)
from sigmai.cartography.symbology import shade  # noqa: E402
from sigmai.validators import ValidationError  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _regra(rule_id):
    return next(rule for rule in rulebook.RULES if rule.id == rule_id)


class MedidaPura(unittest.TestCase):
    def test_profundidade_de_saturacao(self):
        self.assertEqual(saturation_depth(1.0), 1)
        self.assertEqual(saturation_depth(0.95), 1)
        self.assertEqual(saturation_depth(0.5), 5)
        self.assertEqual(saturation_depth(0.35), 7)
        self.assertEqual(saturation_depth(0.25), 11)

    def test_registros_repetidos_ficam_ocultos(self):
        pontos = [(10.0, 10.0)] * 10
        self.assertEqual(stacking(pontos, 2.2, 0.95)["hidden_fraction"], 0.9)
        self.assertEqual(stacking(pontos, 2.2, 0.5)["hidden_fraction"], 0.5)

    def test_pontos_separados_nao_se_escondem(self):
        pontos = [(x * 5.0, y * 5.0) for x in range(10) for y in range(10)]
        medida = stacking(pontos, 2.2, 0.95)
        self.assertEqual(medida["hidden_fraction"], 0.0)
        self.assertEqual(medida["cells"], 100)
        self.assertLessEqual(medida["ink_coverage"], 1.0)

    def test_diametro_invalido_recusado(self):
        with self.assertRaises(ValueError):
            stacking([(0.0, 0.0)], 0.0, 1.0)

    def test_poucos_pontos_ficam_com_o_padrao(self):
        escolha = choose_point_symbol([(float(i), float(i)) for i in range(STACKING_MIN_POINTS - 1)])
        self.assertEqual((escolha["size_mm"], escolha["step"]), (POINT_SYMBOL_STEPS[0][0], 0))

    def test_nuvem_densa_reduz_o_simbolo(self):
        sorteio = random.Random(1)
        pontos = [(sorteio.uniform(0, 60), sorteio.uniform(0, 60)) for _ in range(3000)]
        escolha = choose_point_symbol(pontos)
        self.assertGreater(escolha["step"], 0)
        self.assertTrue(escolha["reached"])
        self.assertLess(escolha["size_mm"], POINT_SYMBOL_STEPS[0][0])

    def test_registros_repetidos_nao_apagam_o_mapa(self):
        """Repetidos nas mesmas coordenadas: encolher não os separa, e o símbolo fica visível."""
        locais = [(10.0 * i, 7.0 * i) for i in range(5)]
        pontos = [locais[i % 5] for i in range(1000)]
        escolha = choose_point_symbol(pontos)
        self.assertFalse(escolha["reached"])
        self.assertLess(escolha["step"], DENSE_ONLY_FROM_STEP)
        self.assertGreater(escolha["hidden_fraction"], STACKING_HIDDEN_MAX)

    def test_aglomerado_esparso_nao_vira_textura(self):
        """100 registros em poucos aglomerados: o ponto de textura (0,45 mm, 25 %) sumiria."""
        sorteio = random.Random(3)
        centros = [(sorteio.uniform(0, 120), sorteio.uniform(0, 90)) for _ in range(25)]
        pontos = [(cx + sorteio.uniform(-0.3, 0.3), cy + sorteio.uniform(-0.3, 0.3))
                  for cx, cy in (centros[i % 25] for i in range(100))]
        escolha = choose_point_symbol(pontos)
        self.assertLess(escolha["step"], DENSE_ONLY_FROM_STEP)
        self.assertGreaterEqual(escolha["size_mm"], POINT_SYMBOL_STEPS[DENSE_ONLY_FROM_STEP - 1][0])

    def test_nuvem_muito_densa_chega_a_textura(self):
        sorteio = random.Random(5)
        pontos = [(sorteio.uniform(0, 60), sorteio.uniform(0, 60)) for _ in range(20000)]
        self.assertGreaterEqual(choose_point_symbol(pontos)["step"], DENSE_ONLY_FROM_STEP)


class AgrupamentoDeLocais(unittest.TestCase):
    def test_locais_proximos_vao_para_o_maior(self):
        locais = [(0.0, 0.0, 5), (100.0, 0.0, 50), (1000.0, 0.0, 1)]
        self.assertEqual(merge_sites(locais, 300.0), [(100.0, 0.0, 55), (1000.0, 0.0, 1)])

    def test_sedes_ficam_afastadas_e_a_contagem_se_conserva(self):
        sorteio = random.Random(11)
        locais = [(sorteio.uniform(0, 5000), sorteio.uniform(0, 5000), sorteio.randint(1, 40)) for _ in range(2000)]
        juntos = merge_sites(locais, 300.0)
        self.assertLess(len(juntos), len(locais))
        self.assertEqual(sum(n for _, _, n in juntos), sum(n for _, _, n in locais))
        originais = {(x, y) for x, y, _ in locais}
        self.assertTrue(all((x, y) in originais for x, y, _ in juntos))
        for i, (x1, y1, _) in enumerate(juntos):
            for x2, y2, _ in juntos[i + 1:]:
                self.assertGreaterEqual((x1 - x2) ** 2 + (y1 - y2) ** 2, 300.0 ** 2)

    def test_graus_convertidos_em_metros(self):
        locais = [(-44.0, -22.0, 3), (-43.999, -22.0, 1)]  # 0,001° de longitude, cerca de 103 m a 22° S
        self.assertEqual(len(merge_sites(locais, 150.0, x_metres=103_000.0, y_metres=110_574.0)), 1)
        self.assertEqual(len(merge_sites(locais, 50.0, x_metres=103_000.0, y_metres=110_574.0)), 2)

    def test_distancia_invalida_recusada(self):
        with self.assertRaises(ValueError):
            merge_sites([(0.0, 0.0, 1)], 0.0)

    def test_contorno_do_circulo_escurece_a_cor(self):
        self.assertEqual(shade("#0072B2", 0.45), "#003F62")
        self.assertEqual(shade("#FFFFFF", 0.0), "#FFFFFF")
        self.assertEqual(shade("azul", 0.5), "azul")


class RegraCart076(unittest.TestCase):
    def _obs(self, pontos, ocultos, camada="registros"):
        return {"map": {"point_stacking": [{"layer": camada, "layer_id": "x", "points": pontos, "cells": 10,
                                            "max_per_cell": 500, "saturation_depth": 1, "symbol_mm": 2.2,
                                            "opacity": 0.95, "hidden_fraction": ocultos, "ink_coverage": 0.1}]}}

    def test_reprova_quando_a_maioria_some(self):
        resultado = _regra("CART076").check(self._obs(10000, 0.98))
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("98%", resultado.detail_pt)
        self.assertIn("não quantos", resultado.detail_pt)

    def test_aprova_poucos_ocultos(self):
        self.assertEqual(_regra("CART076").check(self._obs(300, 0.2)).status, rulebook.STATUS_PASSED)

    def test_poucos_pontos_passam(self):
        self.assertEqual(_regra("CART076").check(self._obs(30, 0.5)).status, rulebook.STATUS_PASSED)

    def test_sem_camada_de_pontos_nao_se_avalia(self):
        self.assertEqual(_regra("CART076").check({"map": {"point_stacking": []}}).status, rulebook.STATUS_SKIP)
        self.assertEqual(_regra("CART076").check({"map": {}}).status, rulebook.STATUS_SKIP)

    def test_e_aviso_e_indica_como_mostrar_a_contagem(self):
        regra = _regra("CART076")
        self.assertEqual(regra.severity, rulebook.SEVERITY_WARNING)
        self.assertIn("apply_heatmap_style", regra.fix_pt)
        self.assertIn("apply_proportional_symbol_style", regra.fix_pt)

    def test_contagens_com_ponto_de_milhar(self):
        resultado = _regra("CART076").check(self._obs(362210, 0.99))
        self.assertIn("362.210", resultado.detail_pt)

    def _locais(self, ocultos):
        return {"map": {"point_stacking": [{"layer": "locais", "layer_id": "s", "points": 11224, "cells": 900,
                                            "max_per_cell": 416, "saturation_depth": 3, "symbol_mm": 1.0,
                                            "opacity": 0.75, "hidden_fraction": ocultos, "ink_coverage": 0.2,
                                            "proportional": True, "scale": 300000, "source_layer_id": "gbif"}]}}

    def test_circulos_amontoados_pedem_agrupar_na_escala(self):
        resultado = _regra("CART076").check(self._locais(0.79))
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("11.224 locais", resultado.detail_pt)
        self.assertIn("count_points_by_site sobre 'gbif' com scale=300000 e min_spacing_mm=1", resultado.detail_pt)

    def test_circulos_separados_passam(self):
        resultado = _regra("CART076").check(self._locais(0.0))
        self.assertEqual(resultado.status, rulebook.STATUS_PASSED)
        self.assertIn("círculos", resultado.detail_pt)

    def test_cart075_aponta_os_pontos_quando_sao_eles_que_cobrem(self):
        obs = self._obs(362210, 0.99)
        obs["map"].update({"subject_layer_ids": ["p"], "subject_visible_fraction": 0.29})
        resultado = _regra("CART075").check(obs)
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("apply_heatmap_style", resultado.detail_pt)
        self.assertIn("'registros'", resultado.detail_pt)


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

    def _parque(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        layer = QgsVectorLayer("Polygon?crs=EPSG:31983", "Parque", "memory")
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromWkt("POLYGON((520000 7515000,545000 7515000,545000 7535000,"
                                                "520000 7535000,520000 7515000))"))
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _pontos(self, coordenadas, nome="Registros"):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        layer = QgsVectorLayer("Point?crs=EPSG:31983", nome, "memory")
        feats = []
        for x, y in coordenadas:
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feats.append(feature)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def _espalhados(n, semente=7):
        sorteio = random.Random(semente)
        return [(sorteio.uniform(520500, 544500), sorteio.uniform(7515500, 7534500)) for _ in range(n)]

    @staticmethod
    def _repetidos(n, locais=8):
        base = [(522000 + 2900 * i, 7517000 + 2100 * i) for i in range(locais)]
        return [base[i % locais] for i in range(n)]

    def _compor(self, pasta, layers, subject, **extra):
        from sigmai.cartography.compose import compose_map

        params = {"layer_ids": [layer.id() for layer in layers], "subject_layer_id": [s.id() for s in subject],
                  "title": "T", "map_author": "T", "data_source": "teste", "map_language": "pt-BR",
                  "output_path": os.path.join(pasta, "m.png"), "format": "png", "dpi": 72, "page": "A5",
                  "orientation": "landscape"}
        params.update(extra)
        return compose_map(params, {"dry_run": False})

    @staticmethod
    def _regras(resultado):
        return {r["id"]: r for r in resultado["audit"]["results"]}

    def test_nuvem_densa_sai_com_ponto_menor_e_o_parque_a_vista(self):
        parque, pontos = self._parque(), self._pontos(self._espalhados(3000))
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos, parque], [pontos, parque])
            self.assertLess(pontos.renderer().symbol().size(), POINT_SYMBOL_STEPS[0][0])
        estilo = next(s for s in resultado["styling"] if s["layer"] == "Registros")
        self.assertLess(estilo["point_symbol"]["size_mm"], POINT_SYMBOL_STEPS[0][0])
        regras = self._regras(resultado)
        self.assertEqual(regras["CART075"]["status"], rulebook.STATUS_PASSED, regras["CART075"])
        self.assertEqual(regras["CART076"]["status"], rulebook.STATUS_PASSED, regras["CART076"])
        self.assertTrue(any("saíram com" in nota for nota in resultado["notes"]), resultado["notes"])

    def test_amostra_da_legenda_legivel_para_ponto_reduzido(self):
        from qgis.core import QgsLayoutItemLegend, QgsMapLayerLegendUtils, QgsProject

        from sigmai.cartography.compose import LEGEND_POINT_MIN_MM

        parque, pontos = self._parque(), self._pontos(self._espalhados(20000))
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos, parque], [pontos])
            self.assertLess(pontos.renderer().symbol().size(), LEGEND_POINT_MIN_MM)
            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            legenda = next(item for item in layout.items() if isinstance(item, QgsLayoutItemLegend))
            no = legenda.model().rootGroup().findLayer(pontos.id())
            amostra = QgsMapLayerLegendUtils.legendNodeCustomSymbol(no, 0)
            self.assertIsNotNone(amostra)
            self.assertGreaterEqual(amostra.size(), LEGEND_POINT_MIN_MM)

    def test_poucos_pontos_mantem_o_simbolo_padrao(self):
        parque, pontos = self._parque(), self._pontos(self._espalhados(20))
        with pasta_temporaria() as pasta:
            self._compor(pasta, [pontos, parque], [pontos])
            self.assertAlmostEqual(pontos.renderer().symbol().size(), POINT_SYMBOL_STEPS[0][0])

    def test_recompor_acompanha_os_pontos_de_agora(self):
        """O símbolo reduzido de uma composição anterior volta ao padrão quando os pontos diminuem."""
        parque, pontos = self._parque(), self._pontos(self._espalhados(3000))
        with pasta_temporaria() as pasta:
            self._compor(pasta, [pontos, parque], [pontos], layout_name="a")
            reduzido = pontos.renderer().symbol().size()
            self.assertLess(reduzido, POINT_SYMBOL_STEPS[0][0])
            self._compor(pasta, [pontos, parque], [pontos], layout_name="b", confirm_overwrite=True)
            self.assertAlmostEqual(pontos.renderer().symbol().size(), reduzido)
            ids = [f.id() for f in pontos.getFeatures()][20:]
            pontos.dataProvider().deleteFeatures(ids)
            pontos.updateExtents()
            self._compor(pasta, [pontos, parque], [pontos], layout_name="c", confirm_overwrite=True)
            self.assertAlmostEqual(pontos.renderer().symbol().size(), POINT_SYMBOL_STEPS[0][0])

    def test_poucos_pontos_em_cinza_mantem_o_padrao_da_paleta_cinza(self):
        from sigmai.cartography.symbology import GREY_GEOMETRY_DEFAULTS

        parque, pontos = self._parque(), self._pontos(self._espalhados(20))
        with pasta_temporaria() as pasta:
            self._compor(pasta, [pontos, parque], [pontos], colour_mode="greyscale")
            simbolo = pontos.renderer().symbol()
            self.assertAlmostEqual(simbolo.size(), GREY_GEOMETRY_DEFAULTS["Point"]["size"])
            self.assertAlmostEqual(simbolo.opacity(), GREY_GEOMETRY_DEFAULTS["Point"]["opacity"])

    def test_estilo_do_usuario_nao_e_trocado(self):
        from sigmai.qgis_actions.symbology import apply_single_symbol

        parque, pontos = self._parque(), self._pontos(self._espalhados(3000))
        apply_single_symbol({"layer_id": pontos.id(), "fill_color": "#000000", "size_mm": 3.0}, {"dry_run": False})
        self.assertAlmostEqual(pontos.renderer().symbol().size(), 3.0)
        with pasta_temporaria() as pasta:
            self._compor(pasta, [pontos, parque], [pontos])
            self.assertAlmostEqual(pontos.renderer().symbol().size(), 3.0)

    def test_registros_repetidos_acusados_pela_cart076(self):
        parque, pontos = self._parque(), self._pontos(self._repetidos(2000))
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos, parque], [pontos])
        regras = self._regras(resultado)
        self.assertEqual(regras["CART076"]["status"], rulebook.STATUS_FAIL, regras["CART076"])
        self.assertTrue(any("apply_proportional_symbol_style" in nota for nota in resultado["notes"]))

    def test_locais_com_simbolo_proporcional(self):
        from sigmai.qgis_actions.gis_tools import count_points_by_site
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style

        parque, pontos = self._parque(), self._pontos(self._repetidos(2000))
        with pasta_temporaria() as pasta:
            saida = os.path.join(pasta, "locais.gpkg")
            simulado = count_points_by_site({"layer_id": pontos.id(), "output_path": saida}, {"dry_run": True})
            self.assertEqual((simulado["sites"], simulado["records"], simulado["max_records_per_site"]), (8, 2000, 250))
            self.assertFalse(os.path.exists(saida))
            locais = count_points_by_site({"layer_id": pontos.id(), "output_path": saida}, {"dry_run": False})
            camada = __import__("qgis.core", fromlist=["QgsProject"]).QgsProject.instance().mapLayer(locais["layer_id"])
            self.assertEqual(camada.featureCount(), 8)
            self.assertEqual(camada.customProperty("sigmai/sites_of"), pontos.id())
            self.assertEqual(camada.customProperty("sigmai/derived_from", ""), "")
            with self.assertRaises(ValidationError):
                count_points_by_site({"layer_id": pontos.id(), "output_path": saida}, {"dry_run": False})
            plano = apply_proportional_symbol_style({"layer_id": camada.id(), "field_name": "records",
                                                     "legend_title": "Registros por local"}, {"dry_run": False})
            self.assertEqual(plano["max"], 250.0)
            self.assertTrue(camada.renderer().symbol().dataDefinedSize().isActive())
            contorno = camada.renderer().symbol().symbolLayer(0).strokeColor().name().upper()
            self.assertEqual(contorno, shade("#0072B2", 0.45))
            resultado = self._compor(pasta, [camada, parque], [camada])
            regras = self._regras(resultado)
            self.assertEqual(regras["CART076"]["status"], rulebook.STATUS_PASSED, regras["CART076"])
            self.assertNotEqual(regras["CART072"]["status"], rulebook.STATUS_FAIL, regras["CART072"])
            del camada

    def test_locais_amontoados_agrupados_na_escala_do_mapa(self):
        """Um local por ponto, apertados num canto do parque: CART076 acusa, e o agrupamento resolve."""
        from qgis.core import QgsProject

        from sigmai.qgis_actions.gis_tools import count_points_by_site
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style

        sorteio = random.Random(13)
        parque = self._parque()
        pontos = self._pontos([(sorteio.uniform(530000, 533000), sorteio.uniform(7520000, 7523000)) for _ in range(3000)])
        with pasta_temporaria() as pasta:
            crus = count_points_by_site({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "a.gpkg")},
                                        {"dry_run": False})
            self.assertEqual(crus["sites"], 3000)
            self.assertIn("scale", crus["note"])
            locais = QgsProject.instance().mapLayer(crus["layer_id"])
            apply_proportional_symbol_style({"layer_id": locais.id(), "field_name": "records"}, {"dry_run": False})
            resultado = self._compor(pasta, [locais, parque], [parque], layout_name="a")
            cart076 = self._regras(resultado)["CART076"]
            self.assertEqual(cart076["status"], rulebook.STATUS_FAIL, cart076)
            escala = int(resultado["scale_denominator"])
            self.assertIn(f"scale={escala}", cart076["detail_pt"])
            self.assertIn(repr(pontos.id()), cart076["detail_pt"])

            juntos = count_points_by_site({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "b.gpkg"),
                                           "scale": f"1:{escala:,}".replace(",", ".")}, {"dry_run": False})
            self.assertEqual((juntos["scale"], juntos["min_spacing_mm"], juntos["records"]), (escala, 1.0, 3000))
            self.assertLess(juntos["sites"], 300)
            agrupados = QgsProject.instance().mapLayer(juntos["layer_id"])
            apply_proportional_symbol_style({"layer_id": agrupados.id(), "field_name": "records"}, {"dry_run": False})
            QgsProject.instance().removeMapLayer(locais.id())
            resultado = self._compor(pasta, [agrupados, parque], [parque], layout_name="b", confirm_overwrite=True)
            cart076 = self._regras(resultado)["CART076"]
            self.assertEqual(cart076["status"], rulebook.STATUS_PASSED, cart076)
            del locais, agrupados

    def test_dense_points_sites_numa_chamada(self):
        from qgis.core import QgsProject

        from sigmai.cartography.compose import CompositionError

        sorteio = random.Random(17)
        parque = self._parque()
        pontos = self._pontos([(sorteio.uniform(530000, 533000), sorteio.uniform(7520000, 7523000)) for _ in range(3000)])
        with pasta_temporaria() as pasta:
            with self.assertRaises(CompositionError):
                self._compor(pasta, [pontos, parque], [pontos], dense_points="nuvem")
            resultado = self._compor(pasta, [pontos, parque], [pontos], dense_points="sites",
                                     data_source={pontos.id(): "GBIF.org", parque.id(): "CNUC/MMA"})
            derivada = resultado["derived_layers"][0]
            self.assertEqual(derivada["source_layer_id"], pontos.id())
            self.assertTrue(os.path.exists(derivada["output_path"]))
            locais = QgsProject.instance().mapLayer(derivada["layer_id"])
            self.assertLess(locais.featureCount(), 3000)
            self.assertTrue(locais.renderer().symbol().dataDefinedSize().isActive())
            self.assertEqual(locais.renderer().dataDefinedSizeLegend().title(), "Registros por local")
            self.assertIsNotNone(QgsProject.instance().mapLayer(pontos.id()))
            regras = self._regras(resultado)
            self.assertEqual(regras["CART076"]["status"], rulebook.STATUS_PASSED, regras["CART076"])
            self.assertTrue(any("dense_points='sites'" in nota for nota in resultado["notes"]), resultado["notes"])
            estilo = next(e for e in resultado["styling"] if e["layer"] == "Registros")
            self.assertEqual(estilo["style_origin"], "dense_points")  # não "estilo do usuário"
            from qgis.core import QgsLayoutItemLabel

            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            textos = " ".join(i.text() for i in layout.items() if isinstance(i, QgsLayoutItemLabel))
            self.assertIn("GBIF.org", textos)  # a fonte dos locais não some do rodapé
            del locais

    def test_dense_points_sites_nos_dois_paineis_com_a_mesma_escala_de_tamanhos(self):
        """Figura S3 (dois períodos): só o painel A virava locais; o B saía com 244.948 pontos."""
        from qgis.core import QgsProject

        sorteio = random.Random(23)
        parque = self._parque()
        antes = self._pontos([(sorteio.uniform(530000, 533000), sorteio.uniform(7520000, 7523000)) for _ in range(3000)],
                             nome="Até 2014")
        depois = self._pontos(self._repetidos(6000), nome="Desde 2015")
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [antes, parque], [antes], dense_points="sites", panel_title="A",
                                     second_map={"layer_ids": [depois.id(), parque.id()], "subject_layer_id": depois.id(),
                                                 "panel_title": "B"}, comparison_same_scale=True)
            derivadas = {d["source_layer_id"]: QgsProject.instance().mapLayer(d["layer_id"]) for d in resultado["derived_layers"]}
            self.assertEqual(set(derivadas), {antes.id(), depois.id()})
            transformadores = [camada.renderer().symbol().dataDefinedSize().transformer() for camada in derivadas.values()]
            self.assertEqual(len({(t.minValue(), t.maxValue()) for t in transformadores}), 1)  # mesma escala de tamanhos
            regras = self._regras(resultado)
            self.assertEqual(regras["CART076"]["status"], rulebook.STATUS_PASSED, regras["CART076"])
            del derivadas, transformadores

    def test_dense_points_simulado_nao_muda_nada(self):
        """E prevê a página do mapa: o plano de Itatiaia dava 88 x 120 mm e o mapa saía 88 x 134 (legenda de tamanhos)."""
        from qgis.core import QgsProject

        from sigmai.cartography.compose import compose_map

        parque, pontos = self._parque(), self._pontos(self._espalhados(3000))
        antes = pontos.renderer().type()
        camadas = set(QgsProject.instance().mapLayers())
        with pasta_temporaria() as pasta:
            pedido = {"layer_ids": [pontos.id(), parque.id()], "subject_layer_id": [pontos.id(), parque.id()],
                      "title": "T", "title_placement": "caption", "map_author": "T", "data_source": "teste",
                      "map_language": "pt-BR", "figure_width_mm": 88, "format": "pdf",
                      "output_path": os.path.join(pasta, "m.pdf"), "dense_points": "sites"}
            plano = compose_map(pedido, {"dry_run": True})
            self.assertEqual(os.listdir(pasta), [])
            self.assertEqual(pontos.renderer().type(), antes)
            self.assertEqual(set(QgsProject.instance().mapLayers()), camadas)
            self.assertLessEqual({c["id"] for c in plano["layers"]}, camadas)
            self.assertTrue(any("virariam" in nota and "locais" in nota for nota in plano["notes"]), plano["notes"])
            mapa = compose_map(pedido, {"dry_run": False})
            self.assertEqual(plano["plan"]["page"]["height_mm"], mapa["page"]["height_mm"])
            self.assertEqual(plano["scale_denominator"], mapa["scale_denominator"])

    def test_dense_points_mapa_de_calor(self):
        parque, pontos = self._parque(), self._pontos(self._espalhados(3000))
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos, parque], [pontos], dense_points="heatmap")
            self.assertEqual(pontos.renderer().type(), "heatmapRenderer")
        self.assertEqual(self._regras(resultado)["CART076"]["status"], rulebook.STATUS_SKIP)

    def test_escala_invalida_recusada(self):
        from sigmai.qgis_actions.gis_tools import count_points_by_site

        pontos = self._pontos(self._repetidos(10))
        with pasta_temporaria() as pasta:
            for escala in ("trezentos mil", 0, True):
                with self.assertRaises(ValidationError):
                    count_points_by_site({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "a.gpkg"),
                                          "scale": escala}, {"dry_run": True})
            with self.assertRaises(ValidationError):
                count_points_by_site({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "a.gpkg"),
                                      "scale": 300000, "min_spacing_mm": 0}, {"dry_run": True})

    def test_contagem_por_local_recusa_poligono_e_extensao_errada(self):
        from sigmai.qgis_actions.gis_tools import count_points_by_site

        parque, pontos = self._parque(), self._pontos(self._repetidos(10))
        with pasta_temporaria() as pasta:
            with self.assertRaises(ValidationError):
                count_points_by_site({"layer_id": parque.id(), "output_path": os.path.join(pasta, "a.gpkg")}, {})
            with self.assertRaises(ValidationError):
                count_points_by_site({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "a.shp")}, {})

    def test_mapa_de_calor_poe_o_contexto_em_contorno_por_cima(self):
        from sigmai.qgis_actions.symbology import apply_heatmap_style

        parque, pontos = self._parque(), self._pontos(self._espalhados(3000))
        apply_heatmap_style({"layer_id": pontos.id(), "radius": 4}, {"dry_run": False})
        with pasta_temporaria() as pasta:
            resultado = self._compor(pasta, [pontos, parque], [pontos])
            simbolo = parque.renderer().symbol()
            self.assertTrue(simbolo.symbolLayer(0).color().alpha() == 0 or simbolo.color().alpha() == 0)
        regras = self._regras(resultado)
        self.assertEqual(regras["CART021"]["status"], rulebook.STATUS_PASSED, regras["CART021"])
        self.assertEqual(regras["CART076"]["status"], rulebook.STATUS_SKIP)


if __name__ == "__main__":
    unittest.main()
