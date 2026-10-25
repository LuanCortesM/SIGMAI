"""Defeitos achados pela bateria de tipos de mapa da 1.2.0 (dados públicos reais, QGIS dirigido pelo MCP).

Cada teste reproduz, em miniatura, um mapa que saiu errado: a fazenda que
cobria a própria APP, a APA que escondia os municípios, a legenda cortada,
as rodovias de classes diferentes na mesma cor, a água laranja, o rio sem
nome, o imóvel cortado na borda do mapa de campanha, a faixa de "0 m" de um
recorte além do raster, a regra de quadro vazio num mapa de linhas.
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
from sigmai.cartography.vision import confusable_pairs  # noqa: E402
from sigmai.qgis_actions.raster_style import (  # noqa: E402
    QUALITATIVE, SEMANTIC_COLOURS, interpolate_hex, lightness_positions, semantic_colour,
)
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


class PaletasSemConfusao(unittest.TestCase):
    def test_qualitativas_distinguiveis_para_daltonicos(self):
        self.assertEqual(confusable_pairs([(c, c) for c in QUALITATIVE]), [])

    def test_cores_com_significado_distinguiveis(self):
        cores = sorted({c for _, c in SEMANTIC_COLOURS})
        self.assertEqual(confusable_pairs([(c, c) for c in cores]), [])

    def test_classes_pelo_nome(self):
        self.assertEqual(semantic_colour("Corpo d´Água Continental"), "#0072B2")
        self.assertEqual(semantic_colour("Vegetação Florestal"), "#009E73")
        self.assertEqual(semantic_colour("Mosaico de Ocupações em Área Florestal"), "#D55E00")
        self.assertEqual(semantic_colour("Built-up"), "#B2182B")
        self.assertIsNone(semantic_colour("Pimenteiras"))

    def test_graduado_em_passos_iguais_de_claridade(self):
        greens = ["#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"]
        samples = [interpolate_hex(greens, k / 40) for k in range(41)]
        cores = [interpolate_hex(greens, p) for p in lightness_positions(samples, 5)]
        self.assertEqual(confusable_pairs([(c, c) for c in cores]), [])


class QuadroVazioPelaTintaDosDados(unittest.TestCase):
    """CART069: um mapa de hidrografia é feito de linhas; a área dos polígonos não o mede."""

    def _regra(self):
        return next(rule for rule in rulebook.RULES if rule.id == "CART069")

    def test_linhas_ocupam_a_faixa(self):
        vazio = [[0.0, 0.0, 0.0]] * 3
        tinta = [[0.06, 0.05, 0.07]] * 3
        obs = {"map": {"polygon_coverage": {"fraction": 0.01, "cells": vazio}, "data_ink_grid": tinta}}
        self.assertEqual(self._regra().check(obs).status, rulebook.STATUS_PASSED)

    def test_trilha_fina_ocupa_a_faixa(self):
        """Uma trilha de 1 px atravessando a faixa norte é dado, não papel em branco."""
        cobertura = [[0.0, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.5, 0.0]]
        tinta = [[0.0, 0.002, 0.001], [0.01, 0.4, 0.01], [0.01, 0.4, 0.01]]
        obs = {"map": {"polygon_coverage": {"fraction": 0.2, "cells": cobertura}, "data_ink_grid": tinta}}
        self.assertNotIn("linha norte", self._regra().check(obs).detail_pt)

    def test_faixa_sem_area_e_sem_tinta_continua_vazia(self):
        cobertura = [[0.0, 0.6, 0.0]] * 3
        tinta = [[0.0001, 0.4, 0.0001]] * 3
        obs = {"map": {"polygon_coverage": {"fraction": 0.2, "cells": cobertura}, "data_ink_grid": tinta}}
        resultado = self._regra().check(obs)
        self.assertEqual(resultado.status, rulebook.STATUS_FAIL)
        self.assertIn("coluna oeste", resultado.detail_pt)


class CreditoSemRepeticao(unittest.TestCase):
    def test_atribuicao_do_mapa_de_base_ja_declarada_nao_se_repete(self):
        from sigmai.cartography.compose import _credit_line

        linha = _credit_line({"map_author": "T", "data_source": "GBIF.org; © OpenStreetMap contributors"}, "EPSG:31984",
                             "25/10/2026", "en", basemap_credits=["© OpenStreetMap contributors (ODbL)"])
        self.assertEqual(linha.count("OpenStreetMap contributors"), 1, linha)
        nova = _credit_line({"map_author": "T", "data_source": "GBIF.org"}, "EPSG:31984", "25/10/2026", "en",
                            basemap_credits=["© OpenStreetMap contributors (ODbL)"])
        self.assertIn("(ODbL)", nova)


class BuscaDePlugin(unittest.TestCase):
    def test_pacote_e_nome_de_exibicao_casam(self):
        from sigmai.qgis_actions.plugin_tools import _select_repository_plugin

        plugins = [{"name": "Edit Tool", "package_name": "edittool"}, {"name": "Shape Tools", "package_name": "shapetools"}]
        for pedido in ("shapetools", "Shape Tools", "shape_tools", "SHAPE-TOOLS"):
            self.assertEqual(_select_repository_plugin(plugins, pedido)["name"], "Shape Tools", pedido)


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
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31984"))

    def _camada(self, nome, geometrias, tipo="Polygon", campo=None):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        uri = f"{tipo}?crs=EPSG:31984" + (f"&field={campo}:string" if campo else "")
        layer = QgsVectorLayer(uri, nome, "memory")
        feats = []
        for item in geometrias:
            wkt, valor = item if isinstance(item, tuple) else (item, None)
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            if campo:
                feature.setAttribute(campo, valor)
            feats.append(feature)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def _quadrado(x, y, lado):
        return f"POLYGON(({x} {y},{x + lado} {y},{x + lado} {y + lado},{x} {y + lado},{x} {y}))"

    def _compor(self, pasta, layers, subject, **extra):
        from sigmai.cartography.compose import compose_map

        params = {"layer_ids": [layer.id() for layer in layers], "subject_layer_id": subject.id(), "title": "T",
                  "map_author": "T", "data_source": "teste", "map_language": "pt-BR",
                  "output_path": os.path.join(pasta, "m.png"), "format": "png", "dpi": 72}
        params.update(extra)
        return compose_map(params, {"dry_run": False})

    @staticmethod
    def _sem_preenchimento(layer):
        symbol = layer.renderer().symbol()
        return symbol.symbolLayer(0).color().alpha() == 0 or symbol.color().alpha() == 0

    def test_uri_de_mapa_de_base_volta_inteira_ao_provedor(self):
        """Codificada à mão, a URL do XYZ não era decodificada pelo QGIS 3.40 e o mapa de base saía em branco."""
        from qgis.core import QgsDataSourceUri

        from sigmai.qgis_actions.data_sources import provider_uri

        url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        uri = provider_uri([("type", "xyz"), ("url", url), ("zmin", "0"), ("zmax", "19")])
        lida = QgsDataSourceUri()
        lida.setEncodedUri(uri)
        self.assertEqual(lida.param("url"), url)
        self.assertEqual(lida.param("type"), "xyz")
        wms = provider_uri([("crs", "EPSG:4326"), ("layers", "a"), ("layers", "b"), ("url", "https://x.org/wms?SERVICE=WMS")])
        lida.setEncodedUri(wms)
        self.assertEqual(lida.params("layers"), ["a", "b"])
        self.assertEqual(lida.param("url"), "https://x.org/wms?SERVICE=WMS")

    def test_plugin_instala_no_perfil_em_uso(self):
        """Um caminho fixo para o perfil default do QGIS 3 vinha por último e recebia a instalação."""
        from qgis.core import QgsApplication

        from sigmai.qgis_actions.plugin_tools import _active_profile_plugins, _plugin_roots

        esperado = (Path(QgsApplication.qgisSettingsDirPath()) / "python" / "plugins").resolve()
        self.assertEqual(_active_profile_plugins(), esperado)
        fixo = (Path(os.environ.get("APPDATA", "")) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins")
        if os.environ.get("APPDATA") and fixo.resolve() != esperado:
            self.assertNotIn(fixo.resolve(), _plugin_roots())

    def test_imovel_nao_cobre_a_propria_app(self):
        with pasta_temporaria() as pasta:
            fazenda = self._camada("Fazenda", [self._quadrado(500000, 9000000, 2000)])
            app = self._camada("APP", ["POLYGON((499500 9000900,502500 9000900,502500 9000960,499500 9000960,499500 9000900))"])
            self._compor(pasta, [fazenda, app], fazenda)
            self.assertTrue(self._sem_preenchimento(fazenda))

    def test_subdivisao_que_forra_o_quadro_vira_contorno_sobre_outra_que_forra(self):
        with pasta_temporaria() as pasta:
            parque = self._camada("Parque", [self._quadrado(503000, 9003000, 2000)])
            # A APA cobre só parte da malha municipal (não a contém, como um
            # estado conteria): as duas forram o quadro em volta do parque.
            apa = self._camada("APA", [self._quadrado(495000, 8995000, 15000)])
            municipios = self._camada("Municipios", [self._quadrado(490000 + 5000 * i, 8990000 + 5000 * j, 5000)
                                                     for i in range(6) for j in range(6)])
            resultado = self._compor(pasta, [parque, apa, municipios], parque)
            self.assertTrue(self._sem_preenchimento(municipios))
            self.assertFalse(self._sem_preenchimento(apa))
            regras = {r["id"]: r["status"] for r in resultado["audit"]["results"]}
            self.assertNotEqual(regras["CART021"], rulebook.STATUS_FAIL)

    def test_massas_dagua_nao_viram_contorno_por_envelope(self):
        from sigmai.cartography.compose import _container_polygon_ids, _imports

        agua = self._camada("Agua", [self._quadrado(500000, 9000000, 500), self._quadrado(510000, 9010000, 500)])
        urbano = self._camada("Urbano", [self._quadrado(505000, 9005000, 300), self._quadrado(505500, 9005500, 300),
                                         self._quadrado(506000, 9006000, 300)])
        self.assertNotIn(agua.id(), _container_polygon_ids([agua, urbano], _imports()))

    def test_categorizado_de_linhas_pinta_o_traco(self):
        from sigmai.qgis_actions.symbology import apply_categorized_style

        vias = self._camada("Vias", [("LINESTRING(0 0,1 1)", "Federal"), ("LINESTRING(0 1,1 0)", "Estadual"),
                                     ("LINESTRING(0 2,1 2)", "Municipal")], tipo="LineString", campo="jur")
        apply_categorized_style({"layer_id": vias.id(), "field_name": "jur"}, {"dry_run": False})
        cores = {c.symbol().color().name() for c in vias.renderer().categories()}
        self.assertEqual(len(cores), 3)

    def test_categorizado_com_cor_de_sentido_e_ordenado(self):
        from sigmai.qgis_actions.symbology import apply_categorized_style

        uso = self._camada("Uso", [(self._quadrado(0, 0, 1), "Vegetação Florestal"), (self._quadrado(1, 0, 1), "Corpo d'Água"),
                                   (self._quadrado(2, 0, 1), "Área Urbana")], campo="classe")
        apply_categorized_style({"layer_id": uso.id(), "field_name": "classe"}, {"dry_run": False})
        por_classe = {c.label(): c.symbol().color().name().upper() for c in uso.renderer().categories()}
        self.assertEqual(por_classe["Corpo d'Água"], "#0072B2")
        self.assertEqual(por_classe["Vegetação Florestal"], "#009E73")
        self.assertEqual([c.label() for c in uso.renderer().categories()], sorted(por_classe, key=str.casefold))

    def test_rotulo_de_rio_acompanha_a_linha(self):
        from qgis.core import Qgis

        from sigmai.qgis_actions.symbology import create_labels

        rio = self._camada("Cursos d'água", [("LINESTRING(0 0,100 50,200 0)", "Rio Piracuruca")], tipo="LineString",
                           campo="nome")
        out = create_labels({"layer_id": rio.id(), "field_name": "nome"}, {"dry_run": False})
        settings = rio.labeling().settings()
        curved = getattr(getattr(Qgis, "LabelPlacement", None), "Curved", None)
        if curved is not None:
            self.assertEqual(settings.placement, curved)
        self.assertTrue(settings.lineSettings().mergeLines())
        self.assertTrue(settings.format().font().italic())
        self.assertTrue(out.get("notes"))

    def test_recorte_alem_do_raster_e_limitado(self):
        import struct

        from osgeo import gdal, osr  # type: ignore
        from qgis.core import QgsProject, QgsRasterLayer

        from sigmai.qgis_actions.raster import raster_clip_by_extent

        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "dem.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 10, 10, 1, gdal.GDT_Float32)
            ds.SetGeoTransform((-42.0, 0.1, 0, -4.0, 0, -0.1))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            ds.SetProjection(srs.ExportToWkt())
            ds.GetRasterBand(1).WriteRaster(0, 0, 10, 10, struct.pack("f" * 100, *([100.0] * 100)))
            ds = None
            layer = QgsRasterLayer(caminho, "dem")
            QgsProject.instance().addMapLayer(layer)
            out = raster_clip_by_extent({"layer_id": layer.id(), "extent": "-41.95,-41.45,-4.45,-3.90 [EPSG:4326]"},
                                        {"dry_run": True})
            self.assertIn("-4.0", out["parameters"]["PROJWIN"])
            self.assertTrue(any("passa da extensão" in w for w in out.get("warnings", [])))

    def test_relevo_sombreado_fora_da_legenda_e_sem_reprovar(self):
        import struct

        from osgeo import gdal, osr  # type: ignore
        from qgis.core import QgsProject, QgsRasterLayer

        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            caminho = os.path.join(pasta, "dem.tif")
            ds = gdal.GetDriverByName("GTiff").Create(caminho, 30, 30, 1, gdal.GDT_Float32)
            ds.SetGeoTransform((480000, 100, 0, 9003000, 0, -100))
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(31984)
            ds.SetProjection(srs.ExportToWkt())
            ds.GetRasterBand(1).WriteRaster(0, 0, 30, 30, struct.pack("f" * 900, *[float((r * 7 + c * 3) % 50) for r in range(30)
                                                                                      for c in range(30)]))
            ds = None
            dem = QgsRasterLayer(caminho, "Elevação")
            sombra = QgsRasterLayer(caminho, "Relevo sombreado")
            QgsProject.instance().addMapLayers([dem, sombra])
            apply_raster_style({"layer_id": dem.id(), "unit": "m"}, {"dry_run": False})
            apply_raster_style({"layer_id": sombra.id(), "mode": "hillshade", "blend_mode": "multiply", "opacity": 0.5},
                               {"dry_run": False})
            resultado = self._compor(pasta, [sombra, dem], dem)
            legenda = resultado["audit"]["observation"]["legend"]["layer_names"]
            self.assertNotIn("Relevo sombreado", legenda)
            regras = {r["id"]: r["status"] for r in resultado["audit"]["results"]}
            self.assertEqual(regras["CART020"], rulebook.STATUS_PASSED)
            self.assertNotEqual(regras["CART021"], rulebook.STATUS_FAIL)

    def test_contexto_dentro_do_assunto_tematico_vira_contorno(self):
        """O parque dentro da geologia ficava escondido sob as classes; vira contorno por cima delas."""
        from sigmai.qgis_actions.symbology import apply_categorized_style

        with pasta_temporaria() as pasta:
            geo = self._camada("Geologia", [(self._quadrado(500000 + 4000 * k, 9000000, 4000), f"Unidade {k}") for k in range(3)],
                               campo="unidade")
            apply_categorized_style({"layer_id": geo.id(), "field_name": "unidade"}, {"dry_run": False})
            parque = self._camada("Parque", [self._quadrado(503000, 9001000, 1500)])
            self._compor(pasta, [parque, geo], geo)
            self.assertTrue(self._sem_preenchimento(parque))
            self.assertEqual(str(geo.renderer().type()), "categorizedSymbol")

    def test_quebra_de_linha_da_legenda_sempre_ligada(self):
        """Sem setWrapString os nomes quebrados saíam numa linha só, 97 mm numa caixa de 80."""
        from qgis.core import QgsProject

        from sigmai.cartography.compose import LEGEND_WRAP
        from sigmai.qgis_actions.symbology import apply_categorized_style

        with pasta_temporaria() as pasta:
            nomes = ["Cobertura Detrito-Laterítica Neogênica", "Cobertura Detrito-Laterítica Paleogênica",
                     "Depósitos Coluviais Holocênicos", "Depósitos Coluviais Pleistocênicos", "Cabeças", "Pimenteiras",
                     "Serra Grande", "Sardinha", "Poti", "Jaicós"]
            geo = self._camada("Unidades geológicas", [(self._quadrado(500000 + 3000 * k, 9000000 + 2000 * (k % 3), 3000), n)
                                                       for k, n in enumerate(nomes)], campo="unidade")
            apply_categorized_style({"layer_id": geo.id(), "field_name": "unidade"}, {"dry_run": False})
            resultado = self._compor(pasta, [geo], geo, journal_column="double")
            layout = QgsProject.instance().layoutManager().layoutByName(resultado["layout_name"])
            self.assertEqual(layout.itemById("legend").wrapString(), LEGEND_WRAP)
            regras = {r["id"]: r["status"] for r in resultado["audit"]["results"]}
            self.assertEqual(regras["CART072"], rulebook.STATUS_PASSED, resultado.get("notes"))

    def test_legenda_de_muitas_classes_usa_colunas_e_cabe(self):
        from sigmai.qgis_actions.symbology import apply_categorized_style

        with pasta_temporaria() as pasta:
            nomes = [f"Unidade geológica de nome bem comprido número {k}" for k in range(9)]
            geo = self._camada("Geologia", [(self._quadrado(500000 + 2000 * k, 9000000, 2000), n) for k, n in enumerate(nomes)],
                               campo="unidade")
            apply_categorized_style({"layer_id": geo.id(), "field_name": "unidade"}, {"dry_run": False})
            resultado = self._compor(pasta, [geo], geo, page="A4 portrait")
            regras = {r["id"]: r["status"] for r in resultado["audit"]["results"]}
            self.assertEqual(regras["CART072"], rulebook.STATUS_PASSED, resultado.get("notes"))


if __name__ == "__main__":
    unittest.main()
