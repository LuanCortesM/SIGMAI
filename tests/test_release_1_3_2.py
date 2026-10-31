"""Achados da segunda sessão do exemplo do artigo (28/10/2026), já na 1.3.1.

Um assistente novo, com o mesmo pedido, tropeçou nisto: a legenda de círculos
que começava em 2.000 registros, o aviso falso de que a recomposição ignorava o
recipe_path que ela usa, a simulação que aceitava uma rampa de cores
inexistente, a saída temporária do Processing tratada como caminho de arquivo e
o panel_title que sumia sem aviso num mapa só.

A sessão da versão candidata (mesmo dia) achou o resto: o cinza dos municípios
apagando o relevo sombreado, o nome SÃO PAULO derrubado pelo motor de rótulos,
a CART020 que contava 3 camadas com 4 desenhadas e o relatório de estilo que
dava a cor do preenchimento a uma camada de pontos.
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
from sigmai.consent import ConsentRequest  # noqa: E402
from sigmai.parameter_introspection import _analyse  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


class LeituraDeParametros(unittest.TestCase):
    def test_outro_dicionario_com_params_no_nome_nao_conta(self):
        """compose_params["map_crs"] contava como leitura de params e fechava a contagem errado."""
        fonte = '''def handler(params, context):
    recipe = _load_recipe(params)
    compose_params = dict(recipe)
    compose_params["map_crs"] = "EPSG:31983"
    return params.get("overrides")
'''
        nomes, fechado = _analyse(fonte)
        self.assertEqual(nomes, ("overrides",))
        self.assertFalse(fechado)  # params vai inteiro para _load_recipe: não dá para saber o que ele lê

    def test_recompor_nao_avisa_que_ignora_o_recipe_path(self):
        from sigmai.parameter_introspection import unread_parameters
        from sigmai.qgis_actions.cartography_engine import recompose_from_recipe

        ignorados, _ = unread_parameters(recompose_from_recipe, {"recipe_path": "/x/r.json", "overrides": {}})
        self.assertEqual(ignorados, [])


class SaidaTemporaria(unittest.TestCase):
    def test_temporary_output_nao_e_caminho(self):
        pedido = ConsentRequest("count_points_in_polygon", "vector_analysis", "safe_write",
                                {"output": "TEMPORARY_OUTPUT", "polygon_layer_id": "a"}, "127.0.0.1")
        self.assertEqual(pedido.output_paths(), [])
        com_arquivo = ConsentRequest("count_points_in_polygon", "vector_analysis", "safe_write",
                                     {"output": "/saida/contagem.gpkg"}, "127.0.0.1")
        self.assertEqual(com_arquivo.output_paths(), ["/saida/contagem.gpkg"])


class LegendaDizAsIsentas(unittest.TestCase):
    def test_cart020_nomeia_o_que_nao_pede_entrada(self):
        observado = {"legend": {"item_id": "l", "layer_names": ["Parque", "Municípios"]},
                     "map": {"visible_layer_names": ["Parque", "Municípios", "Relevo"],
                             "label_only_layer_names": ["Relevo"]}}
        resultado = rulebook._check_legend_covers_visible_layers(observado)
        self.assertEqual(resultado.status, rulebook.STATUS_PASSED)
        self.assertIn("As 2 camadas com algo a explicar", resultado.detail_pt)
        self.assertIn("relevo sombreado, mapa de base ou só rótulos): 'Relevo'", resultado.detail_pt)


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

    def test_simulacao_recusa_rampa_inexistente(self):
        import numpy
        from osgeo import gdal, osr
        from qgis.core import QgsProject, QgsRasterLayer

        from sigmai.qgis_actions.raster_style import apply_raster_style
        from sigmai.validators import ValidationError

        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "r.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 10, 10, 1, gdal.GDT_Float32)
            ds.SetGeoTransform((0, 10, 0, 100, 0, -10))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(31983)
            ds.SetProjection(srs.ExportToWkt())
            ds.GetRasterBand(1).WriteArray(numpy.arange(100, dtype="float32").reshape(10, 10))
            ds = None
            camada = QgsRasterLayer(caminho, "Relevo")
            QgsProject.instance().addMapLayer(camada)
            with self.assertRaises(ValidationError) as recusa:
                apply_raster_style({"layer_id": camada.id(), "color_ramp": "?"}, {"dry_run": True})
            self.assertIn("Rampa de cores desconhecida", str(recusa.exception))
            plano = apply_raster_style({"layer_id": camada.id(), "color_ramp": "Viridis"}, {"dry_run": True})
            self.assertTrue(plano["dry_run"])

    def test_panel_title_num_mapa_so_avisa(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        from sigmai.cartography.compose import compose_map

        parque = QgsVectorLayer("Polygon?crs=EPSG:31983", "Parque", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(520000, 7515000, 545000, 7535000)))
        parque.dataProvider().addFeatures([f])
        parque.updateExtents()
        QgsProject.instance().addMapLayer(parque)
        with pasta_temporaria() as pasta:
            feito = compose_map({"layer_ids": [parque.id()], "title": "Parque", "data_source": "teste",
                                 "panel_title": "A", "output_path": os.path.join(pasta, "p.png"), "format": "png",
                                 "dpi": 72}, {"dry_run": False})
        self.assertTrue(any("panel_title só vale com second_map" in n for n in feito["notes"]), feito["notes"])

    def _poligono(self, nome, wkt):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        camada = QgsVectorLayer("Polygon?crs=EPSG:31983&field=nome:string", nome, "memory")
        f = QgsFeature(camada.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([nome.upper()])
        camada.dataProvider().addFeatures([f])
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        return camada

    def test_relevo_embaixo_deixa_o_contexto_em_contorno_e_o_assunto_preenchido(self):
        import numpy
        from osgeo import gdal, osr
        from qgis.core import QgsProject, QgsRasterLayer
        from qgis.PyQt.QtCore import Qt

        from sigmai.cartography.compose import compose_map
        from sigmai.cartography.qtcompat import qt_enum
        from sigmai.qgis_actions.raster_style import apply_raster_style

        sem_pincel = qt_enum(Qt, "BrushStyle", "NoBrush")
        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "dem.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 120, 100, 1, gdal.GDT_Float32)
            ds.SetGeoTransform((500000, 500, 0, 7550000, 0, -500))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(31983)
            ds.SetProjection(srs.ExportToWkt())
            linhas, colunas = numpy.mgrid[0:100, 0:120]
            ds.GetRasterBand(1).WriteArray((numpy.sin(linhas / 7.0) * numpy.cos(colunas / 9.0) * 800 + 1200).astype("float32"))
            ds = None
            relevo = QgsRasterLayer(caminho, "Relevo")
            QgsProject.instance().addMapLayer(relevo)
            apply_raster_style({"layer_id": relevo.id(), "mode": "hillshade"}, {"dry_run": False})
            municipios = self._poligono("Municípios", "POLYGON((500000 7500000,560000 7500000,560000 7550000,"
                                                      "500000 7550000,500000 7500000))")
            parque = self._poligono("Parque", "POLYGON((520000 7515000,545000 7515000,545000 7535000,"
                                              "520000 7535000,520000 7515000))")
            compose_map({"layer_ids": [parque.id(), municipios.id(), relevo.id()], "subject_layer_id": parque.id(),
                         "title": "Parque", "data_source": "teste", "output_path": os.path.join(pasta, "r.png"),
                         "format": "png", "dpi": 72}, {"dry_run": False})
            self.assertEqual(municipios.renderer().symbol().symbolLayer(0).brushStyle(), sem_pincel)
            self.assertNotEqual(parque.renderer().symbol().symbolLayer(0).brushStyle(), sem_pincel)

    def test_nome_de_regiao_sempre_desenhado(self):
        from qgis.core import Qgis, QgsProject

        from sigmai.cartography.qtcompat import qt_enum
        from sigmai.qgis_actions.context_annotations import add_context_annotations

        estados = self._poligono("Estados", "POLYGON((500000 7500000,560000 7500000,560000 7550000,"
                                            "500000 7550000,500000 7500000))")
        feito = add_context_annotations({"boundary_layer_id": estados.id(), "label_field": "nome"}, {"dry_run": False})
        rotulos = next(c for c in feito["created_layers"] if c["kind"] == "label_only_points")
        ajustes = QgsProject.instance().mapLayer(rotulos["id"]).labeling().settings()
        self.assertEqual(ajustes.placementSettings().overlapHandling(),
                         qt_enum(Qgis, "LabelOverlapHandling", "AllowOverlapIfRequired"))
        self.assertEqual(ajustes.priority, 10)
        from sigmai.cartography.symbology import apply_default_symbology

        relatorio = apply_default_symbology([QgsProject.instance().mapLayer(rotulos["id"])], "missing", dry_run=True)
        self.assertIn("add_context_annotations", relatorio[0]["reason"])  # e não "paleta de uma composição anterior"

    def test_letra_do_painel_nao_e_o_titulo(self):
        """Figura 3 do exemplo: com o título na legenda do texto, a CART001 dizia "Título presente: 'B'"."""
        from sigmai.cartography.compose import compose_map

        parque = self._poligono("Parque", "POLYGON((520000 7515000,545000 7515000,545000 7535000,"
                                          "520000 7535000,520000 7515000))")
        with pasta_temporaria() as pasta:
            feito = compose_map({"layer_ids": [parque.id()], "panel_title": "A",
                                 "second_map": {"layer_ids": [parque.id()], "panel_title": "B"},
                                 "title": "Dois painéis", "title_placement": "caption", "data_source": "teste",
                                 "figure_width_mm": 180, "output_path": os.path.join(pasta, "p.png"), "format": "png",
                                 "dpi": 72}, {"dry_run": False})
        cart001 = next(r for r in feito["audit"]["results"] if r["id"] == "CART001")
        self.assertIn("Título na legenda do texto", cart001["detail_pt"])

    def test_faixa_inferior_pedida_com_paineis_refaz_a_altura_da_figura(self):
        """Figura 3, chamada 95: com arrangement="faixa_inferior", a figura ficava com a altura da coluna lateral."""
        from sigmai.cartography.compose import compose_map

        parque = self._poligono("Parque", "POLYGON((520000 7515000,545000 7515000,545000 7535000,"
                                          "520000 7535000,520000 7515000))")
        pedido = {"layer_ids": [parque.id()], "panel_title": "A", "second_map": {"layer_ids": [parque.id()], "panel_title": "B"},
                  "title": "T", "title_placement": "caption", "data_source": "teste", "figure_width_mm": 180}
        coluna = compose_map({**pedido, "arrangement": "coluna_lateral"}, {"dry_run": True})
        faixa = compose_map({**pedido, "arrangement": "faixa_inferior"}, {"dry_run": True})
        self.assertGreater(faixa["plan"]["page"]["height_mm"], coluna["plan"]["page"]["height_mm"])
        com_escala = compose_map({**pedido, "arrangement": "faixa_inferior", "scale": faixa["scale_denominator"]},
                                 {"dry_run": True})
        self.assertEqual(com_escala["plan"]["page"]["height_mm"], faixa["plan"]["page"]["height_mm"])

    def test_legenda_de_tamanhos_sem_titulo_nao_mostra_o_campo(self):
        """legend_title="" guardava título vazio, e o QGIS desenhava o nome do campo ("records") no lugar."""
        from qgis.core import QgsFeature, QgsGeometry, QgsLayoutItemLegend, QgsPointXY, QgsProject, QgsVectorLayer
        from qgis.PyQt.QtCore import Qt

        from sigmai.cartography.compose import compose_map
        from sigmai.qgis_actions.symbology import apply_proportional_symbol_style

        locais = QgsVectorLayer("Point?crs=EPSG:31983&field=records:integer", "Records per site", "memory")
        feats = []
        for i, n in enumerate((1, 50, 900, 20000, 68881)):
            f = QgsFeature(locais.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(521000 + 5000 * i, 7520000 + 2500 * i)))
            f.setAttribute("records", n)
            feats.append(f)
        locais.dataProvider().addFeatures(feats)
        locais.updateExtents()
        QgsProject.instance().addMapLayer(locais)
        apply_proportional_symbol_style({"layer_id": locais.id(), "field_name": "records", "legend_title": ""},
                                        {"dry_run": False})
        with pasta_temporaria() as pasta:
            feito = compose_map({"layer_ids": [locais.id()], "title": "Locais", "data_source": "teste",
                                 "output_path": os.path.join(pasta, "p.png"), "format": "png", "dpi": 72},
                                {"dry_run": False})
            layout = QgsProject.instance().layoutManager().layoutByName(feito["layout_name"])
            legenda = next(i for i in layout.items() if isinstance(i, QgsLayoutItemLegend))
            modelo = legenda.model()
            no = modelo.rootGroup().findLayer(locais.id())
            textos = [str(n.data(Qt.ItemDataRole.DisplayRole) or "") for n in modelo.layerLegendNodes(no)]
        self.assertNotIn("records", textos)

    def test_utm_automatico_segue_o_datum_do_assunto_e_nao_o_do_projeto(self):
        """Depois de fechar o QGIS, o projeto refeito ficou em EPSG:4326 e a Figura 3 saiu em WGS 84 / UTM 23S."""
        from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        from sigmai.cartography.compose import compose_map

        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        parque = QgsVectorLayer("Polygon?crs=EPSG:4674", "Parque", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((-44.77 -22.47,-44.55 -22.47,-44.55 -22.24,-44.77 -22.24,-44.77 -22.47))"))
        parque.dataProvider().addFeatures([f])
        parque.updateExtents()
        QgsProject.instance().addMapLayer(parque)
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        plano = compose_map({"layer_ids": [parque.id()], "title": "Parque", "data_source": "teste"}, {"dry_run": True})
        self.assertEqual(plano["map_crs"], "EPSG:31983")

    def _raster_de_classes(self, pasta, valores=(10, 20, 30)):
        import numpy
        from osgeo import gdal, osr
        from qgis.core import QgsProject, QgsRasterLayer

        caminho = os.path.join(pasta, "classes.tif")
        ds = gdal.GetDriverByName("GTiff").Create(caminho, 30, 30, 1, gdal.GDT_Byte)
        ds.SetGeoTransform((520000, 100, 0, 7535000, 0, -100))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(31983)
        ds.SetProjection(srs.ExportToWkt())
        grade = numpy.zeros((30, 30), dtype="uint8")
        for k, valor in enumerate(valores):
            grade[:, k * 10:(k + 1) * 10] = valor
        ds.GetRasterBand(1).WriteArray(grade)
        ds = None
        camada = QgsRasterLayer(caminho, "Cobertura")
        QgsProject.instance().addMapLayer(camada)
        return camada

    def test_cores_dadas_valem_em_unique_values_e_classes(self):
        """Figura S2: unique_values ignorava colors em silêncio; classes com colors respondia color_ramp "Viridis"."""
        from sigmai.qgis_actions.raster_style import apply_raster_style
        from sigmai.validators import ValidationError

        with pasta_temporaria() as pasta:
            camada = self._raster_de_classes(pasta)
            apply_raster_style({"layer_id": camada.id(), "mode": "unique_values",
                                "colors": {"10": "#E69F00", "20": "#009E73", "30.0": "#0072B2"}}, {"dry_run": False})
            self.assertEqual([c.color.name() for c in camada.renderer().classes()], ["#e69f00", "#009e73", "#0072b2"])
            apply_raster_style({"layer_id": camada.id(), "mode": "unique_values", "colors": ["#000000", "#555555", "#aaaaaa"]},
                               {"dry_run": False})
            self.assertEqual([c.color.name() for c in camada.renderer().classes()], ["#000000", "#555555", "#aaaaaa"])
            with self.assertRaises(ValidationError):
                apply_raster_style({"layer_id": camada.id(), "mode": "unique_values", "colors": {"40": "#000000"}}, {"dry_run": False})
            plano = apply_raster_style({"layer_id": camada.id(), "mode": "classes", "breaks": [0, 15, 25, 40],
                                        "colors": ["#E69F00", "#009E73", "#0072B2"]}, {"dry_run": True})
            self.assertIsNone(plano["color_ramp"])
            with self.assertRaises(ValidationError):
                apply_raster_style({"layer_id": camada.id(), "mode": "pseudocolor", "colors": ["#000000"]}, {"dry_run": True})

    def test_opacidade_e_estilo_de_raster(self):
        """Figura S1: set_layer_opacity e inspect_layer_style recusavam raster."""
        from sigmai.qgis_actions.raster_style import apply_raster_style
        from sigmai.qgis_actions.symbology import inspect_layer_style, set_layer_opacity

        with pasta_temporaria() as pasta:
            camada = self._raster_de_classes(pasta)
            apply_raster_style({"layer_id": camada.id(), "mode": "unique_values"}, {"dry_run": False})
            set_layer_opacity({"layer_id": camada.id(), "opacity": 0.35}, {"dry_run": False})
            self.assertAlmostEqual(camada.renderer().opacity(), 0.35)
            estilo = inspect_layer_style({"layer_id": camada.id()}, {})
            self.assertEqual((estilo["renderer_type"], estilo["class_count"], estilo["blend_mode"]), ("paletted", 3, "normal"))
            self.assertAlmostEqual(estilo["opacity"], 0.35)

    def test_cart070_ve_as_classes_de_um_raster_de_categorias(self):
        """Figura S2: com as cores oficiais do WorldCover, a CART070 contava "1 par" e não olhava as classes."""
        from sigmai.cartography.inspector import _layer_colours
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            camada = self._raster_de_classes(pasta)
            apply_raster_style({"layer_id": camada.id(), "mode": "unique_values", "colors": ["#FA0000", "#006400", "#0064C8"]},
                               {"dry_run": False})
            cores = _layer_colours([camada])
        self.assertEqual(cores[0]["family"], "raster")
        self.assertEqual([c["colour"] for c in cores[0]["classes"]], ["#fa0000", "#006400", "#0064c8"])

    def test_expressao_conta_a_camada_inteira(self):
        """Figura S3: a simulação de extract_by_expression lia só as 100.000 primeiras feições."""
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        from sigmai.qgis_actions.selection import extract_by_expression, select_by_expression

        pontos = QgsVectorLayer("Point?crs=EPSG:31983&field=year:integer", "Registros", "memory")
        feats = []
        for i in range(120000):
            f = QgsFeature(pontos.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(520000 + i % 1000, 7520000 + i // 1000)))
            f.setAttribute(0, 2010 if i < 100000 else 2020)
            feats.append(f)
        pontos.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(pontos)
        plano = extract_by_expression({"layer_id": pontos.id(), "expression": '"year" >= 2015'}, {"dry_run": True})
        self.assertEqual(plano["would_extract_count"], 20000)
        feito = select_by_expression({"layer_id": pontos.id(), "expression": '"year" >= 2015'}, {"dry_run": False})
        self.assertEqual(feito["selected_count"], 20000)
        cortado = select_by_expression({"layer_id": pontos.id(), "expression": '"year" >= 2015', "max_features": 110000},
                                       {"dry_run": True})
        self.assertTrue(cortado["truncated_at_max_features"])

    def test_relevo_opaco_por_cima_das_cores_avisa(self):
        """Figura S1: o relevo sombreado opaco cobria as cores hipsométricas, e só a CART021 avisava."""
        import numpy
        from osgeo import gdal, osr
        from qgis.core import QgsProject, QgsRasterLayer

        from sigmai.cartography.compose import compose_map
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "dem.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 60, 60, 1, gdal.GDT_Float32)
            ds.SetGeoTransform((520000, 400, 0, 7540000, 0, -400))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(31983)
            ds.SetProjection(srs.ExportToWkt())
            linhas, colunas = numpy.mgrid[0:60, 0:60]
            ds.GetRasterBand(1).WriteArray((numpy.sin(linhas / 6.0) * numpy.cos(colunas / 8.0) * 700 + 1500).astype("float32"))
            ds = None
            cores = QgsRasterLayer(caminho, "Elevation")
            relevo = QgsRasterLayer(caminho, "Shaded relief")
            QgsProject.instance().addMapLayers([cores, relevo])
            apply_raster_style({"layer_id": cores.id(), "mode": "pseudocolor"}, {"dry_run": False})
            apply_raster_style({"layer_id": relevo.id(), "mode": "hillshade"}, {"dry_run": False})
            pedido = {"layer_ids": [cores.id(), relevo.id()], "title": "Relevo", "data_source": "teste"}
            plano = compose_map(pedido, {"dry_run": True})
            self.assertTrue(any("o cobre" in n for n in plano["notes"]), plano["notes"])
            apply_raster_style({"layer_id": relevo.id(), "mode": "hillshade", "blend_mode": "multiply"}, {"dry_run": False})
            plano = compose_map(pedido, {"dry_run": True})
            self.assertFalse(any("o cobre" in n for n in plano["notes"]))

    def test_escala_da_resposta_na_lingua_do_mapa(self):
        """Figura S1: em inglês, a resposta dizia "1:370.000" e o mapa, "Scale 1:370,000"."""
        from sigmai.cartography.compose import compose_map

        parque = self._poligono("Parque", "POLYGON((520000 7515000,545000 7515000,545000 7535000,"
                                          "520000 7535000,520000 7515000))")
        plano = compose_map({"layer_ids": [parque.id()], "title": "Park", "data_source": "test", "map_language": "en"},
                            {"dry_run": True})
        self.assertIn(",", plano["scale"])
        self.assertNotIn(".", plano["scale"])

    def test_fonte_da_camada_do_inserto_entra_na_legenda(self):
        """compose_map recusava a fonte de uma camada que só aparece no inserto."""
        from sigmai.cartography.compose import compose_map

        parque = self._poligono("Parque", "POLYGON((520000 7515000,545000 7515000,545000 7535000,"
                                          "520000 7535000,520000 7515000))")
        brasil = self._poligono("Brasil", "POLYGON((300000 7300000,800000 7300000,800000 7800000,"
                                          "300000 7800000,300000 7300000))")
        with pasta_temporaria() as pasta:
            feito = compose_map({"layer_ids": [parque.id()], "title": "Parque", "title_placement": "caption",
                                 "include_inset": True, "inset_layer_ids": [brasil.id()],
                                 "data_source": {parque.id(): "CNUC/MMA (2025)", brasil.id(): "IBGE (2024)"},
                                 "output_path": os.path.join(pasta, "p.png"), "format": "png", "dpi": 72},
                                {"dry_run": False})
        self.assertIn("CNUC/MMA (2025) [Parque]; IBGE (2024) [Brasil]", feito["caption"])

    def test_relatorio_de_estilo_da_cor_do_ponto(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        from sigmai.cartography.compose import compose_map

        pontos = QgsVectorLayer("Point?crs=EPSG:31983", "Locais", "memory")
        feats = []
        for i in range(5):
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(521000 + 4000 * i, 7516000 + 3000 * i)))
            feats.append(f)
        pontos.dataProvider().addFeatures(feats)
        pontos.updateExtents()
        QgsProject.instance().addMapLayer(pontos)
        with pasta_temporaria() as pasta:
            plano = compose_map({"layer_ids": [pontos.id()], "title": "Locais", "data_source": "teste",
                                 "output_path": os.path.join(pasta, "p.png"), "format": "png", "dpi": 72},
                                {"dry_run": True})
        estilo = next(e for e in plano["styling_preview"] if e["layer"] == "Locais")
        self.assertEqual(estilo["color"], estilo["accent"])


if __name__ == "__main__":
    unittest.main()
