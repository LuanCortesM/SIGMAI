"""Achados do exemplo do artigo (27/10/2026): um assistente fez as figuras só pelo SIGMAI e tropeçou nisto.

Cada teste reproduz um tropeço: o estilo QML dado como não carregado, a falta de
um comando para renomear camada, a opacidade de pontos que ia para a camada,
os rótulos espremidos da legenda de círculos, o título vazio que virava o nome
do campo, a legenda partida entre colunas e o parágrafo de Métodos que dizia
que a receita estava dentro do PDF.
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

from sigmai.cartography.recipe import SOFTWARE_DOI, methods_paragraph  # noqa: E402
from sigmai.cartography.symbology import proportional_size_mm, size_legend_values  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


def _receita(fmt="pdf", **extra):
    params = {"title": "Records", "data_source": {"a": "GBIF.org (2026)", "b": "GBIF.org (2026)", "c": "CNUC/MMA (2025)"},
              "recipe_path": "/x/fig.json", **extra}
    return {"params": params, "layers": [{"id": "a", "name": "Records", "provider": "ogr"},
                                         {"id": "b", "name": "Sites", "provider": "ogr"},
                                         {"id": "c", "name": "Park", "provider": "ogr"}],
            "page": {"name": "figura", "width_mm": 180, "height_mm": 90}, "output": {"format": fmt, "dpi": 300},
            "audit": {"grade": "A", "score": 95.0, "rule_count": 43}, "map_crs": "EPSG:31983",
            "map_crs_description": "SIRGAS 2000 / UTM zone 23S", "scale_denominator": 500000,
            "qgis_version": "4.0.2-Norrköping", "sigmai_version": "1.3.1", "created_at": "2026-10-28T00:00:00Z"}


class ParagrafoDeMetodos(unittest.TestCase):
    def test_pdf_nao_diz_que_a_receita_esta_no_arquivo(self):
        en = methods_paragraph(_receita("pdf"), "en")["paragraph"]
        self.assertNotIn("exported file's metadata", en)
        self.assertNotIn("metadata of the exported PNG", en)
        self.assertIn("in the layout properties and in a JSON file distributed with the figure", en)
        self.assertIn("exported as PDF.", en)  # sem raster, o dpi não diz nada
        png = methods_paragraph(_receita("png"), "en")["paragraph"]
        self.assertIn("in the metadata of the exported PNG", png)
        self.assertIn("exported as PNG at 300 dpi", png)

    def test_raster_no_pdf_leva_o_dpi(self):
        receita = _receita("pdf")
        receita["layers"].append({"id": "d", "name": "Relief", "provider": "gdal"})
        self.assertIn("exported as PDF, with raster layers at 300 dpi", methods_paragraph(receita, "en")["paragraph"])

    def test_mesma_fonte_sai_uma_vez(self):
        en = methods_paragraph(_receita(), "en")["paragraph"]
        self.assertEqual(en.count("GBIF.org (2026)"), 1)
        self.assertIn("GBIF.org (2026) [Records, Sites]", en)  # 1.3.2: camadas entre colchetes depois de um ano entre parênteses

    def test_citacao_e_referencia_pela_lingua_com_doi(self):
        en = methods_paragraph(_receita(), "en")
        self.assertIn("(Maciel 2026)", en["paragraph"])
        self.assertNotIn("MACIEL, 2026", en["paragraph"])
        self.assertIn(f"https://doi.org/{SOFTWARE_DOI}", en["software_reference"])
        self.assertIn("version 1.3.1", en["software_reference"])
        pt = methods_paragraph(_receita(), "pt-BR")
        self.assertIn("(MACIEL, 2026)", pt["paragraph"])  # ABNT no português, como antes
        self.assertIn(f"https://doi.org/{SOFTWARE_DOI}", pt["software_reference"])

    def test_doi_e_o_do_citation(self):
        self.assertIn(f"doi: {SOFTWARE_DOI}", (ROOT / "CITATION.cff").read_text(encoding="utf-8"))


class LegendaDeCirculos(unittest.TestCase):
    def test_valores_com_circulos_separados(self):
        """1, 100, 10.000 e 69.542 davam círculos de 1,0 e 1,3 mm com rótulos sobrepostos; na 1.3.1, a legenda
        pulava para 2.000 e deixava de fora o menor símbolo do mapa."""
        valores = size_legend_values(1, 69542, 1.0, 8.0)
        self.assertEqual(valores, [1, 20000, 69542])
        tamanhos = [proportional_size_mm(v, 1, 69542, 1.0, 8.0) for v in valores]
        self.assertTrue(all(b - a >= 2.5 for a, b in zip(tamanhos, tamanhos[1:])), tamanhos)

    def test_faixa_curta_e_degenerada(self):
        self.assertEqual(size_legend_values(5, 5, 1.0, 8.0), [5])
        self.assertEqual(size_legend_values(0, 1000, 1.0, 8.0)[0], 1)  # contagem com zero começa em 1
        self.assertLessEqual(len(size_legend_values(3, 40, 1.0, 8.0)), 3)
        self.assertEqual(size_legend_values(3, 40, 1.0, 8.0)[-1], 40)


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
    def _pontos(nome="Pontos", quantos=40, campo=False):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer("Point?crs=EPSG:31983" + ("&field=records:integer" if campo else ""), nome, "memory")
        feats = []
        for i in range(quantos):
            f = QgsFeature(camada.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(520000 + 400 * i, 7515000 + 300 * (i % 9))))
            if campo:
                f.setAttribute(0, 1 + (i * 37) % 5000)
            feats.append(f)
        camada.dataProvider().addFeatures(feats)
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def test_qml_salvo_e_carregado_sai_como_carregado(self):
        from sigmai.cartography.symbology import style_origin
        from sigmai.qgis_actions.symbology import apply_single_symbol, load_qml_style, save_qml_style

        origem, destino = self._pontos("Origem"), self._pontos("Destino")
        apply_single_symbol({"layer_id": origem.id(), "fill_color": "#0072B2", "size_mm": 2}, {"dry_run": False})
        with pasta_temporaria() as pasta:
            qml = os.path.join(pasta, "estilo.qml")
            salvo = save_qml_style({"layer_id": origem.id(), "output_path": qml}, {"dry_run": False})
            self.assertIs(salvo["saved"], True, salvo)
            carregado = load_qml_style({"layer_id": destino.id(), "path": qml}, {"dry_run": False})
            self.assertIs(carregado["loaded"], True, carregado)
            self.assertEqual(style_origin(destino), "user")

    def test_renomear_camada(self):
        from sigmai.permissions import COMMAND_PERMISSIONS
        from sigmai.qgis_actions.layer_tree import rename_layer
        from sigmai.validators import ValidationError

        camada = self._pontos("GBIF record (A)")
        plano = rename_layer({"layer_id": camada.id(), "name": "GBIF record"}, {"dry_run": True})
        self.assertEqual((plano["old_name"], plano["new_name"]), ("GBIF record (A)", "GBIF record"))
        self.assertEqual(camada.name(), "GBIF record (A)")
        rename_layer({"layer_id": camada.id(), "name": "  GBIF record  "}, {"dry_run": False})
        self.assertEqual(camada.name(), "GBIF record")
        with self.assertRaises(ValidationError):
            rename_layer({"layer_id": camada.id(), "name": "   "}, {"dry_run": False})
        self.assertTrue(COMMAND_PERMISSIONS["rename_layer"].supports_dry_run)

    def test_opacidade_de_ponto_vai_para_o_simbolo(self):
        from sigmai.qgis_actions.symbology import apply_single_symbol

        camada = self._pontos()
        apply_single_symbol({"layer_id": camada.id(), "fill_color": "#0072B2", "opacity": 0.5}, {"dry_run": False})
        self.assertAlmostEqual(camada.opacity(), 1.0)
        self.assertAlmostEqual(camada.renderer().symbol().opacity(), 0.5)
        apply_single_symbol({"layer_id": camada.id(), "fill_color": "#0072B2", "fill_opacity": 0.75}, {"dry_run": False})
        marcador = camada.renderer().symbol().symbolLayer(0)
        self.assertAlmostEqual(marcador.color().alphaF(), 0.75, places=2)
        self.assertAlmostEqual(camada.opacity(), 1.0)

    def test_legenda_de_circulos_sem_titulo_quando_pedido(self):
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style

        camada = self._pontos("Records per site", campo=True)
        plano = apply_proportional_symbol_style({"layer_id": camada.id(), "field_name": "records", "legend_title": ""},
                                                {"dry_run": False})
        self.assertEqual(plano["legend_title"], "")
        self.assertEqual(camada.renderer().dataDefinedSizeLegend().title(), "")
        sem = apply_proportional_symbol_style({"layer_id": camada.id(), "field_name": "records"}, {"dry_run": True})
        self.assertEqual(sem["legend_title"], "records")

    def test_figura_de_dados_em_graus_tem_a_altura_do_mapa_projetado(self):
        """A altura da figura saía da proporção do recorte em graus; com map_crs explícito, da do recorte projetado.

        A mesma figura do Itatiaia saía com 1.724 px de altura composta pela primeira vez e 1.842 px recomposta
        pela receita (que passa o CRS gravado).
        """
        from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        from sigmai.cartography.compose import compose_map

        projeto = QgsProject.instance()
        projeto.clear()
        projeto.setCrs(QgsCoordinateReferenceSystem("EPSG:4674"))
        parque = QgsVectorLayer("Polygon?crs=EPSG:4674&field=nome:string", "Parque", "memory")
        f = QgsFeature(parque.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(-44.85, -22.50, -44.45, -22.25)))
        parque.dataProvider().addFeatures([f])
        parque.updateExtents()
        projeto.addMapLayer(parque)
        alturas = []
        with pasta_temporaria() as pasta:
            for i, extra in enumerate(({}, {"map_crs": "EPSG:31983"})):
                feito = compose_map({"layer_ids": [parque.id()], "title": "Parque", "data_source": "teste",
                                     "figure_width_mm": 180, "title_placement": "caption", "layout_name": f"F{i}",
                                     "output_path": os.path.join(pasta, f"f{i}.png"), "format": "png", "dpi": 72,
                                     **extra}, {"dry_run": False})
                self.assertEqual(feito["map_crs"], "EPSG:31983")
                alturas.append(feito["page"]["height_mm"])
        self.assertAlmostEqual(alturas[0], alturas[1], places=1)

    def test_legenda_com_circulos_nao_se_divide_entre_colunas(self):
        from qgis.core import QgsLayoutItemLegend, QgsPrintLayout, QgsProject

        from sigmai.cartography.compose import _has_size_legend
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style

        camada = self._pontos("Records per site", campo=True)
        layout = QgsPrintLayout(QgsProject.instance())
        layout.initializeDefaults()
        legenda = QgsLayoutItemLegend(layout)
        layout.addLayoutItem(legenda)
        self.assertFalse(_has_size_legend(legenda))
        apply_proportional_symbol_style({"layer_id": camada.id(), "field_name": "records"}, {"dry_run": False})
        self.assertTrue(_has_size_legend(legenda))


if __name__ == "__main__":
    unittest.main()
