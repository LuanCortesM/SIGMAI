"""Regras que o experimento "PyQGIS puro × SIGMAI" mostrou que faltavam.

* CART068 — rótulos descartados pelo motor do QGIS (o agente direto perdeu
  'Piracuruca' na moldura e ninguém avisou);
* CART069 — faixa inteira do quadro sem dado (a metade leste vazia do mapa
  do Parque das Carnaúbas passava com nota A);
* CART042 — sobreposição sobre o quadro aceita quando o entorno está vazio
  (rosa dos ventos num canto vazio era acusada de colisão);
* CART070 — cores distinguíveis por daltônicos (Machado et al., 2009);
* CART071 — fontes julgadas na largura final impressa.

As classes que precisam de PyQGIS são puladas numa máquina sem QGIS.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography import vision  # noqa: E402
from sigmai.cartography.rulebook import (  # noqa: E402
    FRAME_BAND_EMPTY_MAX, OVERLAY_MAX_SURROUNDINGS_INK, RULES_BY_ID, _empty_bands, evaluate,
)


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


def _base_observation(**overrides):
    observation = {
        "page": {"width_mm": 297, "height_mm": 210, "content_area_mm": {"x": 10, "y": 10, "width": 277, "height": 190}},
        "items": [{"id": "main_map", "type": "map", "role": "map", "x": 10, "y": 30, "width": 200, "height": 150}],
        "map": {"item_id": "main_map", "visible_layer_names": ["A"]},
        "legend": None, "scalebar": None, "north": None, "map_frames": [], "inset": None, "output": {},
    }
    observation.update(overrides)
    return observation


def _result(laudo, rule_id):
    return next(c for c in laudo["results"] if c["id"] == rule_id)


class SimulacaoDeDaltonismo(unittest.TestCase):
    def test_pares_classicos_sao_acusados(self):
        for a, b in (("#FF0000", "#00A000"), ("#8B0000", "#006400"), ("#FF6600", "#66CC00")):
            achados = vision.confusable_pairs([("a", a), ("b", b)])
            self.assertEqual(len(achados), 1, (a, b))
            self.assertIn(achados[0]["deficiency"], ("protanopia", "deuteranopia"))

    def test_paleta_okabe_ito_nao_tem_par_confundivel(self):
        cores = [(f"c{i}", c) for i, c in enumerate(vision.OKABE_ITO)]
        self.assertEqual(vision.confusable_pairs(cores), [])

    def test_luminosidade_diferente_salva_o_par(self):
        self.assertEqual(vision.confusable_pairs([("a", "#FF0000"), ("b", "#00FF00")]), [])

    def test_a_paleta_da_composicao_passa_na_propria_regra(self):
        """Na emulação da 1.1.0 o mapa composto pelo SIGMAI foi reprovado em CART070
        pela própria paleta (matizes clareados 82 % convergem para o branco).
        Os quatro primeiros preenchimentos de polígono têm de ser distintos
        em qualquer das três simulações; e um par só de matiz, sem diferença
        de claridade, mostra por que a sequência alterna claridades."""
        from sigmai.cartography.symbology import POLYGON_FILLS, _tint

        fills = [(f"p{i}", _tint(accent, amount)) for i, (accent, amount) in enumerate(POLYGON_FILLS[:4])]
        self.assertEqual(vision.confusable_pairs(fills), [], fills)
        so_matiz = [("azul", _tint("#0072B2", 0.82)), ("verde", _tint("#009E73", 0.82))]
        self.assertEqual(len(vision.confusable_pairs(so_matiz)), 1)

    def test_preenchimento_novo_desvia_dos_que_ja_estao_em_uso(self):
        """Camada preservada de um mapa anterior em laranja + camada nova: a nova não pode sair laranja."""
        from sigmai.cartography.symbology import POLYGON_FILLS, _next_polygon_fill, _tint

        laranja = _tint(*POLYGON_FILLS[0])
        accent, amount, proximo = _next_polygon_fill(0, [laranja])
        self.assertNotEqual((accent, amount), POLYGON_FILLS[0])
        self.assertEqual(vision.confusable_pairs([("uso", laranja), ("novo", _tint(accent, amount))]), [])
        self.assertEqual(proximo, 2)
        # sem nada em uso, a sequência é respeitada
        self.assertEqual(_next_polygon_fill(0, [])[:2], POLYGON_FILLS[0])

    def test_cor_invalida_e_ignorada(self):
        self.assertIsNone(vision.parse_hex("azul"))
        self.assertEqual(vision.confusable_pairs([("a", "azul"), ("b", "#FF0000")]), [])

    def test_branco_e_preto_em_lab(self):
        self.assertAlmostEqual(vision.to_lab((1, 1, 1))[0], 100.0, places=3)
        self.assertAlmostEqual(vision.to_lab((0, 0, 0))[0], 0.0, places=3)


class RotulosDescartados(unittest.TestCase):
    def test_sem_coleta_pula(self):
        self.assertEqual(_result(evaluate(_base_observation()), "CART068")["status"], "skip")

    def test_sem_camada_rotulada_pula(self):
        obs = _base_observation(map_frames=[{"item_id": "main_map", "labels": {"placed": 0, "unplaced": 0, "by_layer": {}}}])
        self.assertEqual(_result(evaluate(obs), "CART068")["status"], "skip")

    def test_todos_colocados_passa(self):
        obs = _base_observation(map_frames=[{"item_id": "main_map", "labels": {"placed": 8, "unplaced": 0, "by_layer": {"M": {"placed": 8, "unplaced": 0}}}}])
        self.assertEqual(_result(evaluate(obs), "CART068")["status"], "pass")

    def test_descartado_reprova_com_nome_da_feicao(self):
        labels = {"placed": 8, "unplaced": 1, "by_layer": {"Municípios": {"placed": 5, "unplaced": 1}},
                  "unplaced_sample": [{"layer": "Municípios", "text": "Piracuruca"}]}
        obs = _base_observation(map_frames=[{"item_id": "main_map", "labels": labels}])
        resultado = _result(evaluate(obs), "CART068")
        self.assertEqual(resultado["status"], "fail")
        self.assertIn("Piracuruca", resultado["detail_pt"])
        self.assertEqual(resultado["evidence"]["by_layer"], {"Municípios": 1})


class FaixaVaziaDoQuadro(unittest.TestCase):
    PIAUI_RETRATO = [[0.0, 0.211, 0.305], [0.167, 0.708, 0.611], [0.518, 0.447, 0.09]]
    PIAUI_PAISAGEM = [[0.0, 0.282, 0.009], [0.022, 0.689, 0.125], [0.115, 0.475, 0.004]]
    CARNAUBAS = [[0.41, 0.012, 0.045], [0.083, 0.196, 0.021], [0.138, 0.009, 0.0]]

    def test_estado_diagonal_em_retrato_nao_forma_faixa(self):
        self.assertEqual(_empty_bands(self.PIAUI_RETRATO, FRAME_BAND_EMPTY_MAX), [])

    def test_estado_em_paisagem_tem_duas_colunas_vazias(self):
        self.assertEqual(_empty_bands(self.PIAUI_PAISAGEM, FRAME_BAND_EMPTY_MAX), ["coluna oeste", "coluna leste"])

    def test_carnaubas_tem_leste_e_sul_vazios(self):
        self.assertEqual(_empty_bands(self.CARNAUBAS, FRAME_BAND_EMPTY_MAX), ["coluna leste", "linha sul"])

    def test_regra_usa_cobertura_geometrica_quando_ha_poligonos(self):
        obs = _base_observation(map={"item_id": "main_map", "polygon_coverage": {"fraction": 0.38, "cells": self.CARNAUBAS, "layers": []}})
        resultado = _result(evaluate(obs), "CART069")
        self.assertEqual(resultado["status"], "fail")
        self.assertEqual(resultado["evidence"]["empty_bands"], ["coluna leste", "linha sul"])
        obs = _base_observation(map={"item_id": "main_map", "polygon_coverage": {"fraction": 0.34, "cells": self.PIAUI_RETRATO, "layers": []}})
        self.assertEqual(_result(evaluate(obs), "CART069")["status"], "pass")

    def test_sem_poligonos_usa_tinta_do_raster(self):
        grade = [[0.3, 0.2, 0.0], [0.3, 0.2, 0.01], [0.3, 0.2, 0.0]]
        obs = _base_observation(map={"item_id": "main_map", "rendered_ink_grid": grade})
        resultado = _result(evaluate(obs), "CART069")
        self.assertEqual(resultado["status"], "fail")
        self.assertEqual(resultado["evidence"]["empty_bands"], ["coluna leste"])

    def test_sem_nada_para_medir_pula(self):
        self.assertEqual(_result(evaluate(_base_observation()), "CART069")["status"], "skip")


class SobreposicaoSobreOQuadro(unittest.TestCase):
    def _obs(self, ring):
        norte = {"id": "north_arrow", "type": "picture", "role": "north", "x": 180, "y": 35, "width": 13, "height": 16}
        if ring is not None:
            norte["surroundings_ink_fraction"] = ring
        obs = _base_observation()
        obs["items"].append(norte)
        return obs

    def test_rosa_dos_ventos_em_canto_vazio_e_aceita(self):
        resultado = _result(evaluate(self._obs(0.01)), "CART042")
        self.assertEqual(resultado["status"], "pass")
        self.assertEqual(len(resultado["evidence"]["overlays"]), 1)

    def test_rosa_dos_ventos_sobre_dados_continua_colisao(self):
        resultado = _result(evaluate(self._obs(OVERLAY_MAX_SURROUNDINGS_INK + 0.2)), "CART042")
        self.assertEqual(resultado["status"], "fail")

    def test_sem_raster_a_sobreposicao_e_acusada(self):
        self.assertEqual(_result(evaluate(self._obs(None)), "CART042")["status"], "fail")

    def test_dois_rotulos_encostados_nao_sao_sobreposicao_sobre_o_quadro(self):
        obs = _base_observation()
        obs["items"] += [
            {"id": "title", "type": "label", "role": "title", "x": 10, "y": 6, "width": 190, "height": 10, "surroundings_ink_fraction": 0.0},
            {"id": "subtitle", "type": "label", "role": "subtitle", "x": 10, "y": 15, "width": 190, "height": 6, "surroundings_ink_fraction": 0.0},
        ]
        resultado = _result(evaluate(obs), "CART042")
        self.assertEqual(resultado["status"], "fail")
        self.assertEqual(resultado["evidence"]["collisions"][0]["a"], "title")


class CoresNaLegenda(unittest.TestCase):
    def _obs(self, layer_colours):
        return _base_observation(map={"item_id": "main_map", "layer_colours": layer_colours})

    def test_par_vermelho_verde_reprova(self):
        obs = self._obs([
            {"layer": "Uso", "family": "polygon", "classes": [{"label": "Mata", "colour": "#006400"}, {"label": "Pasto", "colour": "#8B0000"}]},
        ])
        resultado = _result(evaluate(obs), "CART070")
        self.assertEqual(resultado["status"], "fail")
        self.assertEqual(resultado["evidence"]["confusable"][0]["family"], "polygon")

    def test_familias_diferentes_nao_competem(self):
        obs = self._obs([
            {"layer": "Mata", "family": "polygon", "classes": [{"label": "Mata", "colour": "#006400"}]},
            {"layer": "Rios", "family": "line", "classes": [{"label": "Rios", "colour": "#8B0000"}]},
        ])
        self.assertEqual(_result(evaluate(obs), "CART070")["status"], "skip")

    def test_paleta_do_sigmai_passa(self):
        obs = self._obs([
            {"layer": "A", "family": "polygon", "classes": [{"label": "A", "colour": "#CFE3EF"}]},
            {"layer": "B", "family": "polygon", "classes": [{"label": "B", "colour": "#D55E00"}]},
        ])
        self.assertEqual(_result(evaluate(obs), "CART070")["status"], "pass")

    def test_sem_cores_pula(self):
        self.assertEqual(_result(evaluate(_base_observation()), "CART070")["status"], "skip")


class FontesNaLarguraImpressa(unittest.TestCase):
    def test_sem_largura_pula(self):
        self.assertEqual(_result(evaluate(_base_observation()), "CART071")["status"], "skip")

    def test_a4_reduzida_a_coluna_reprova_rodape_de_7pt(self):
        obs = _base_observation(print_width_mm=85.0)
        obs["items"].append({"id": "source", "type": "label", "role": "source", "text": "Fonte: x", "font_size_pt": 7.0,
                             "x": 10, "y": 195, "width": 200, "height": 5})
        resultado = _result(evaluate(obs), "CART071")
        self.assertEqual(resultado["status"], "fail")
        self.assertEqual(resultado["evidence"]["small_texts"][0]["effective_pt"], 2.0)

    def test_figura_composta_na_largura_final_passa(self):
        obs = _base_observation(print_width_mm=297.0)
        obs["items"].append({"id": "source", "type": "label", "role": "source", "text": "Fonte: x", "font_size_pt": 7.0})
        self.assertEqual(_result(evaluate(obs), "CART071")["status"], "pass")


class LegendaCabeNaCaixa(unittest.TestCase):
    """CART072 — a emulação da 1.1.0 mostrou '(IBGE, 2024)' cortado sobre a linha de crédito."""

    def _obs(self, **legend):
        return _base_observation(legend={"item_id": "legend", "layer_names": ["A", "B"], **legend})

    def test_conteudo_maior_que_a_caixa_reprova(self):
        obs = self._obs(box_mm={"width": 34.6, "height": 26.0}, content_mm={"width": 32.8, "height": 29.3})
        resultado = _result(evaluate(obs), "CART072")
        self.assertEqual(resultado["status"], "fail")
        self.assertIn("3.3 mm a mais de altura", resultado["detail_pt"])

    def test_conteudo_que_cabe_passa(self):
        obs = self._obs(box_mm={"width": 34.6, "height": 26.0}, content_mm={"width": 32.8, "height": 23.5})
        self.assertEqual(_result(evaluate(obs), "CART072")["status"], "pass")

    def test_caixa_que_cresce_passa_e_sem_medida_pula(self):
        obs = self._obs(box_mm={"width": 10, "height": 10}, content_mm={"width": 40, "height": 40}, resize_to_contents=True)
        self.assertEqual(_result(evaluate(obs), "CART072")["status"], "pass")
        self.assertEqual(_result(evaluate(self._obs()), "CART072")["status"], "skip")
        self.assertEqual(_result(evaluate(_base_observation()), "CART072")["status"], "skip")


class RegulamentoRegistraAsNovasRegras(unittest.TestCase):
    def test_ids_e_categorias(self):
        for rule_id, categoria in (("CART068", "elementos"), ("CART069", "dados"), ("CART070", "simbologia"), ("CART071", "tipografia"),
                                   ("CART072", "elementos")):
            self.assertEqual(RULES_BY_ID[rule_id].category, categoria)
            self.assertTrue(RULES_BY_ID[rule_id].reference)


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class MedicoesNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _projeto_com_quadrados(self):
        from qgis.core import (
            QgsFeature, QgsGeometry, QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsPalLayerSettings,
            QgsPrintLayout, QgsProject, QgsRectangle, QgsUnitTypes, QgsVectorLayer, QgsVectorLayerSimpleLabeling,
            QgsCoordinateReferenceSystem,
        )

        project = QgsProject.instance()
        project.clear()
        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", "Quadrados", "memory")
        provider = layer.dataProvider()
        feats = []
        # Dois retângulos nos dois terços oeste; o terço leste do quadro fica
        # vazio (extensão 1200 x 1000; o terço leste começa em x=800).
        for i, (x, y) in enumerate(((0, 0), (0, 600))):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromRect(QgsRectangle(x, y, x + 800, y + 400)))
            f.setAttribute("nome", f"Quadrado {i}")
            feats.append(f)
        provider.addFeatures(feats)
        layer.updateExtents()
        settings = QgsPalLayerSettings()
        settings.fieldName = "nome"
        settings.enabled = True
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        project.addMapLayer(layer)
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("quadrados")
        item = QgsLayoutItemMap(layout)
        item.attemptMove(QgsLayoutPoint(10, 10, QgsUnitTypes.LayoutMillimeters))
        item.attemptResize(QgsLayoutSize(200, 150, QgsUnitTypes.LayoutMillimeters))
        item.setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))
        item.setLayers([layer])
        item.setExtent(QgsRectangle(0, 0, 1200, 1000))
        layout.addLayoutItem(item)
        project.layoutManager().addLayout(layout)
        return layout, item, layer

    def test_cobertura_por_celula_encontra_a_metade_leste_vazia(self):
        from sigmai.cartography.inspector import _polygon_coverage

        _, item, layer = self._projeto_com_quadrados()
        cobertura = _polygon_coverage(item, [layer])
        self.assertIsNotNone(cobertura)
        self.assertAlmostEqual(cobertura["fraction"], 2 * 800 * 400 / (item.extent().width() * item.extent().height()), places=2)
        self.assertEqual(_empty_bands(cobertura["cells"], FRAME_BAND_EMPTY_MAX), ["coluna leste"])

    def test_coleta_de_rotulos_conta_os_colocados(self):
        from sigmai.cartography.inspector import collect_label_results

        _, item, _ = self._projeto_com_quadrados()
        resultado = collect_label_results(item, dpi=96)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["placed"] + resultado["unplaced"], 2)
        self.assertIn("Quadrados", resultado["by_layer"])

    def test_legenda_estreita_e_medida_e_ajustada(self):
        """Uma legenda de 30 x 12 mm feita à mão com dois nomes compridos transborda
        (CART072 reprova); a composição numa coluna de revista com os mesmos
        nomes cabe, porque compose_map reduz a fonte e tira as fontes por camada."""
        from qgis.core import QgsLayoutItemLegend, QgsLayoutPoint, QgsLayoutSize, QgsProject, QgsUnitTypes

        from sigmai.cartography.compose import audit_layout
        from sigmai.cartography.inspector import observe_layout
        from sigmai.qgis_actions.cartography_engine import compose_map

        layout, item, layer = self._projeto_com_quadrados()
        layer.setName("Limite estadual do Piauí segundo a malha territorial")
        legend = QgsLayoutItemLegend(layout)
        legend.setId("legend")
        legend.setLinkedMap(item)
        legend.setResizeToContents(False)
        legend.attemptMove(QgsLayoutPoint(220, 10, QgsUnitTypes.LayoutMillimeters))
        legend.attemptResize(QgsLayoutSize(30, 12, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)
        observacao = observe_layout(layout)
        self.assertGreater(observacao["legend"]["content_mm"]["width"], observacao["legend"]["box_mm"]["width"])
        laudo = audit_layout(layout, collect_labels=False)
        self.assertEqual(_result(laudo, "CART072")["status"], "fail")

        from qgis.core import QgsFeature, QgsGeometry, QgsRectangle, QgsVectorLayer

        outra = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string", "Municípios da mesorregião norte", "memory")
        f = QgsFeature(outra.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1200, 1000)))
        outra.dataProvider().addFeatures([f])
        outra.updateExtents()
        QgsProject.instance().addMapLayer(outra)
        with tempfile.TemporaryDirectory() as pasta:
            r = compose_map({"layer_ids": [layer.id(), outra.id()], "title": "F", "map_author": "a",
                             "data_source": {layer.id(): "IBGE, Malha Municipal 2024", outra.id(): "IBGE, Malha Municipal 2024"},
                             "journal_column": "single", "output_path": os.path.join(pasta, "f.png"), "format": "png",
                             "dpi": 72, "layout_name": "F"}, {"dry_run": False})
        self.assertEqual(next(c for c in r["audit"]["results"] if c["id"] == "CART072")["status"], "pass")
        self.assertTrue(any("legenda" in n.lower() and ("reduzida" in n or "não couberam" in n) for n in r["notes"]), r["notes"])

    def test_tinta_em_grade_e_no_entorno(self):
        from qgis.PyQt.QtGui import QColor, QImage, QPainter

        from sigmai.cartography.inspector import measure_ink_grid, measure_surroundings_ink

        # Página 100x100 mm a 2 px/mm; metade oeste pintada de azul.
        image = QImage(200, 200, QImage.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.fillRect(0, 0, 100, 200, QColor("#0072B2"))
        painter.end()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "p.png")
            image.save(caminho)
            quadro = {"x": 0, "y": 0, "width": 100, "height": 100}
            grade = measure_ink_grid(caminho, quadro, (100, 100))
            self.assertEqual(_empty_bands(grade, 0.02), ["coluna leste"])
            vazio = measure_surroundings_ink(caminho, {"x": 80, "y": 80, "width": 10, "height": 10}, quadro, (100, 100))
            cheio = measure_surroundings_ink(caminho, {"x": 20, "y": 20, "width": 10, "height": 10}, quadro, (100, 100))
            self.assertEqual(vazio, 0.0)
            self.assertGreater(cheio, 0.9)


if __name__ == "__main__":
    unittest.main()
