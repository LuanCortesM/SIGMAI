"""Onde vai a legenda e o que ela mostra (1.4).

O teste real do chat com o Gemini gratuito (31/10/2026) entregou um mapa nota
A com a legenda "parna_itatiaia", "municipios_2024", "relevo_copernicus_glo30":
nomes de arquivo. Daí a CART082. O autor pediu também que a legenda complexa
seja perguntada, porque há revistas que a querem embaixo da figura ou noutro
lugar do artigo: daí legend_placement e o aviso da simulação.
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
from sigmai.cartography.layoutgrid import SCALE_ONLY_BAND_MM, solve_layout  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


class NomesDaLegenda(unittest.TestCase):
    def test_nome_de_arquivo_reprova(self):
        observado = {"legend": {"item_id": "l", "layer_names": ["parna_itatiaia", "municipios_2024", "Estados"]}}
        resultado = rulebook._check_legend_names(observado)
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertEqual(resultado.evidence["file_like"], ["parna_itatiaia", "municipios_2024"])
        self.assertIn("rename_layer", resultado.detail_pt)

    def test_nome_legivel_passa(self):
        observado = {"legend": {"item_id": "l", "layer_names": ["Itatiaia National Park", "Municipal boundaries",
                                                                "GBIF record", "BR UF 2024"]}}
        self.assertEqual(rulebook._check_legend_names(observado).status, rulebook.STATUS_PASSED)

    def test_extensao_e_ano_colado(self):
        for nome in ("relevo.tif", "municipios2024", "UCs.gpkg"):
            with self.subTest(nome=nome):
                observado = {"legend": {"item_id": "l", "layer_names": [nome]}}
                self.assertEqual(rulebook._check_legend_names(observado).status, rulebook.STATUS_FAIL)

    def test_legenda_a_parte_tambem_e_conferida(self):
        observado = {"caption": {"legend_placement": "separate", "legend_layer_names": ["estados_2024"]}}
        self.assertEqual(rulebook._check_legend_names(observado).status, rulebook.STATUS_FAIL)

    def test_e_erro(self):
        regra = rulebook.RULES_BY_ID["CART082"]
        self.assertEqual(regra.severity, rulebook.SEVERITY_ERROR)


class LegendaPresente(unittest.TestCase):
    MAPA = {"map": {"visible_layer_names": ["Parque", "Municípios"]}}

    def test_legenda_em_arquivo_a_parte_conta_como_presente(self):
        observado = {**self.MAPA, "caption": {"legend_placement": "separate", "legend_layer_names": ["Parque", "Municípios"]}}
        resultado = rulebook._check_legend(observado)
        self.assertEqual(resultado.status, rulebook.STATUS_PASSED)
        self.assertIn("arquivo à parte", resultado.detail_pt)

    def test_legenda_fora_da_figura_por_escolha(self):
        observado = {**self.MAPA, "caption": {"legend_placement": "none"}}
        self.assertEqual(rulebook._check_legend(observado).status, rulebook.STATUS_SKIP)

    def test_sem_escolha_continua_reprovando(self):
        self.assertEqual(rulebook._check_legend(self.MAPA).status, rulebook.STATUS_FAIL)


class FaixaSemLegenda(unittest.TestCase):
    """Com a legenda à parte, a faixa inferior só tem escala e norte."""

    def _faixa(self, plan):
        return plan.page.content_y_mm + plan.page.content_height_mm - plan.slots["scale_text"].y

    def test_figura_de_coluna(self):
        pagina = {"width_mm": 88.0, "height_mm": 90.0, "name": "figura"}
        sem = solve_layout(page=pagina, include_legend=False, include_title=False, include_footer=False)
        com = solve_layout(page=pagina, include_title=False, include_footer=False)
        self.assertEqual(sem.arrangement, "faixa_inferior")
        self.assertAlmostEqual(self._faixa(sem), SCALE_ONLY_BAND_MM)
        self.assertGreater(sem.map_frame().height, com.map_frame().height)

    def test_seta_de_norte_maior_manda(self):
        plano = solve_layout(page="A4 portrait", include_legend=False)
        self.assertGreater(self._faixa(plano), SCALE_ONLY_BAND_MM)
        self.assertLessEqual(plano.slots["north"].bottom, plano.page.content_y_mm + plano.page.content_height_mm + 1e-6)


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

    def _camada(self, nome, x0, y0):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        camada = QgsVectorLayer("Polygon?crs=EPSG:31983&field=classe:string", nome, "memory")
        feicao = QgsFeature(camada.fields())
        feicao.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, y0, x0 + 20000, y0 + 15000)))
        feicao.setAttribute("classe", "a")
        camada.dataProvider().addFeatures([feicao])
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def _classificada(self, classes):
        from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsProject, QgsRectangle,
                               QgsRendererCategory, QgsSymbol, QgsVectorLayer)

        camada = QgsVectorLayer("Polygon?crs=EPSG:31983&field=classe:string", "Uso do solo", "memory")
        feicoes = []
        for i in range(classes):
            feicao = QgsFeature(camada.fields())
            feicao.setGeometry(QgsGeometry.fromRect(QgsRectangle(520000 + i * 2000, 7515000, 521500 + i * 2000, 7530000)))
            feicao.setAttribute("classe", f"Classe {i}")
            feicoes.append(feicao)
        camada.dataProvider().addFeatures(feicoes)
        camada.updateExtents()
        categorias = [QgsRendererCategory(f"Classe {i}", QgsSymbol.defaultSymbol(camada.geometryType()), f"Classe {i}")
                      for i in range(classes)]
        camada.setRenderer(QgsCategorizedSymbolRenderer("classe", categorias))
        QgsProject.instance().addMapLayer(camada)
        return camada

    def test_legenda_em_arquivo_a_parte(self):
        from sigmai.cartography.compose import compose_map

        parque = self._camada("Parque", 520000, 7515000)
        municipios = self._camada("Municípios", 510000, 7505000)
        with pasta_temporaria() as pasta:
            saida = os.path.join(pasta, "fig.png")
            feito = compose_map({"layer_ids": [parque.id(), municipios.id()], "subject_layer_id": parque.id(),
                                 "title": "Parque", "title_placement": "caption", "data_source": "teste",
                                 "figure_width_mm": 88, "legend_placement": "separate", "output_path": saida,
                                 "format": "png", "dpi": 72}, {"dry_run": False})
            legenda = Path(pasta) / "fig_legend.png"
            self.assertTrue(legenda.exists(), feito["notes"])
            self.assertEqual(feito["legend_output_path"], str(legenda))
            self.assertNotIn("legend", feito["items_created"])
            from qgis.PyQt.QtGui import QImage  # o QGIS do conda-forge no macOS não traz o PIL

            imagem = QImage(str(legenda))
            self.assertLess(imagem.height(), imagem.width())  # só a legenda, cortada na altura dela
        cart002 = next(r for r in feito["audit"]["results"] if r["id"] == "CART002")
        self.assertEqual(cart002["status"], "pass")
        self.assertIn("arquivo à parte", cart002["detail_pt"])

    def test_figura_sem_legenda_fica_com_o_quadro_mais_largo(self):
        from sigmai.cartography.compose import compose_map

        uso = self._classificada(10)
        plano = compose_map({"layer_ids": [uso.id()], "title": "Uso", "title_placement": "caption", "data_source": "teste",
                             "figure_width_mm": 88, "legend_placement": "separate"}, {"dry_run": True})
        # Empatava a 58 mm, com coluna lateral e o mapa em 1:400.000.
        self.assertEqual(plano["plan"]["arrangement"], "faixa_inferior")
        self.assertGreater(plano["plan"]["slots"]["map"]["width"], 60.0)

    def test_legenda_embaixo(self):
        from sigmai.cartography.compose import compose_map

        parque = self._camada("Parque", 520000, 7515000)
        plano = compose_map({"layer_ids": [parque.id()], "title": "Parque", "data_source": "teste",
                             "figure_width_mm": 180, "legend_placement": "below"}, {"dry_run": True})
        self.assertEqual(plano["plan"]["arrangement"], "faixa_inferior")
        self.assertEqual(plano["legend"]["placement"], "below")

    def test_legenda_complexa_manda_perguntar(self):
        from sigmai.cartography.compose import compose_map

        uso = self._classificada(10)
        plano = compose_map({"layer_ids": [uso.id()], "title": "Uso", "data_source": "teste",
                             "figure_width_mm": 180}, {"dry_run": True})
        self.assertEqual(plano["legend"]["rows"], 10)
        self.assertTrue(any("pergunte ao usuário onde ela vai" in nota for nota in plano["notes"]), plano["notes"])
        escolhida = compose_map({"layer_ids": [uso.id()], "title": "Uso", "data_source": "teste",
                                 "figure_width_mm": 180, "legend_placement": "map"}, {"dry_run": True})
        self.assertFalse(any("pergunte ao usuário onde ela vai" in nota for nota in escolhida["notes"]))

    def test_legenda_simples_nao_pergunta(self):
        from sigmai.cartography.compose import compose_map

        parque = self._camada("Parque", 520000, 7515000)
        plano = compose_map({"layer_ids": [parque.id()], "title": "Parque", "data_source": "teste",
                             "figure_width_mm": 88}, {"dry_run": True})
        self.assertFalse(any("pergunte ao usuário onde ela vai" in nota for nota in plano["notes"]))

    def test_nome_de_arquivo_na_legenda_derruba_a_nota(self):
        from sigmai.cartography.compose import compose_map

        parque = self._camada("parna_itatiaia", 520000, 7515000)
        municipios = self._camada("municipios_2024", 510000, 7505000)
        with pasta_temporaria() as pasta:
            feito = compose_map({"layer_ids": [parque.id(), municipios.id()], "subject_layer_id": parque.id(),
                                 "title": "Parque", "data_source": "teste", "output_path": os.path.join(pasta, "f.png"),
                                 "format": "png", "dpi": 72}, {"dry_run": False})
        cart082 = next(r for r in feito["audit"]["results"] if r["id"] == "CART082")
        self.assertEqual(cart082["status"], "fail")
        self.assertNotEqual(feito["audit"]["grade"], "A")

    def test_posicao_desconhecida_e_recusada(self):
        from sigmai.cartography.compose import CompositionError, compose_map

        parque = self._camada("Parque", 520000, 7515000)
        with self.assertRaises(CompositionError) as recusa:
            compose_map({"layer_ids": [parque.id()], "title": "P", "legend_placement": "rodape"}, {"dry_run": True})
        self.assertIn("'separate'", str(recusa.exception))


if __name__ == "__main__":
    unittest.main()
