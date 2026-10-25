"""Regressões da revisão da 1.2.0: cada defeito confirmado ganhou um teste.

- rótulos da barra de escala que se sobrepunham (par vizinho mais largo);
- raster como assunto escondido sob os municípios, com nota A (CART075);
- camada dependente de escala acusada como fantasma (CART021);
- contorno do estado reprovando CART070 contra o contexto;
- figura em cinza que apagava as classes do mapa temático;
- legenda de raster com "Band 1 (Gray)" e seis casas decimais;
- faixa inferior de altura fixa e seta de norte gigante;
- orientação paisagem para um recorte alto quando ninguém a escolheu.
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
from sigmai.cartography.layoutgrid import (  # noqa: E402
    NORTH_MAX_PAGE_FRACTION, SUPPORT_BAND_MIN_MM, solve_layout,
)
from sigmai.cartography.pagespec import page_states_orientation  # noqa: E402
from sigmai.cartography.scaling import (  # noqa: E402
    scalebar_label_space, scalebar_labels, scalebar_labels_fit, scalebar_spec,
)
from sigmai.qgis_actions.symbology import GRADUATED_METHODS, _class_breaks, _jenks_cuts  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None
HAS_NUMPY = importlib.util.find_spec("numpy") is not None


def _regra(rule_id):
    return next(rule for rule in rulebook.RULES if rule.id == rule_id)


class RotulosDaBarraPorParVizinho(unittest.TestCase):
    def test_rotulos_da_esquerda_para_a_direita(self):
        self.assertEqual(scalebar_labels(500, 2, 1), ["500", "0", "500", "1,000"])

    def test_par_mais_largo_nao_e_sempre_o_da_ponta(self):
        # "0.25"+"0.5" pede mais que "0.75"+"1": a ponta não é o par mais apertado.
        _segment, _needed, par = scalebar_label_space(0.25, 4, 0, 60.0, 8.0)
        self.assertNotEqual(par, ("0.75", "1"))
        self.assertIn(par, [("0.25", "0.5"), ("0.5", "0.75")])

    def test_varredura_sem_sobreposicao(self):
        """Toda barra que o SIGMAI escolhe cabe os rótulos sem encostar."""
        for denominador in (1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 1000000, 5000000):
            for largura in (45.0, 60.0, 85.0, 120.0, 175.0, 277.0):
                for fonte in (6.0, 8.0, 10.0):
                    spec = scalebar_spec(denominador, largura, label_font_pt=fonte)
                    bar_mm = spec.bar_width_mm
                    self.assertTrue(
                        scalebar_labels_fit(spec.units_per_segment, spec.segments_right, spec.segments_left, bar_mm, fonte),
                        (denominador, largura, fonte, spec),
                    )

    def test_coluna_de_revista_a_50_mil(self):
        spec = scalebar_spec(50000, 85.0, label_font_pt=8.0)
        labels = scalebar_labels(spec.units_per_segment, spec.segments_right, spec.segments_left)
        self.assertLessEqual(len(labels), 3, labels)


class AssuntoAVista(unittest.TestCase):
    def test_sem_assunto_nao_avalia(self):
        self.assertEqual(_regra("CART075").check({"map": {}}).status, rulebook.STATUS_SKIP)

    def test_limiar(self):
        limite = rulebook.SUBJECT_VISIBLE_MIN
        passa = _regra("CART075").check({"map": {"subject_layer_ids": ["a"], "subject_visible_fraction": limite}})
        reprova = _regra("CART075").check({"map": {"subject_layer_ids": ["a"], "subject_visible_fraction": 0.05}})
        self.assertEqual(passa.status, rulebook.STATUS_PASSED)
        self.assertEqual(reprova.status, rulebook.STATUS_FAIL)
        self.assertIn("contorno", reprova.detail_pt)

    def test_e_erro(self):
        self.assertEqual(_regra("CART075").severity, rulebook.SEVERITY_ERROR)


class FantasmaVazioOuCoberto(unittest.TestCase):
    def _obs(self, **map_info):
        return {
            "legend": {"item_id": "legend", "layer_names": ["Municipios", "Parque"]},
            "map": {"visible_layer_names": ["Municipios", "Parque"], **map_info},
            "map_frames": [{}],
        }

    def test_vazia_e_coberta_tem_mensagens_proprias(self):
        regra = _regra("CART021")
        vazia = regra.check(self._obs(empty_layer_names=["Parque"], hidden_layer_names=[]))
        coberta = regra.check(self._obs(empty_layer_names=[], hidden_layer_names=["Municipios"]))
        self.assertEqual(vazia.status, rulebook.STATUS_FAIL)
        self.assertIn("sem nenhuma feição", vazia.detail_pt)
        self.assertEqual(coberta.status, rulebook.STATUS_FAIL)
        self.assertIn("coberta", coberta.detail_pt)

    def test_nada_vazio_nem_coberto_passa(self):
        self.assertEqual(_regra("CART021").check(self._obs(empty_layer_names=[], hidden_layer_names=[])).status,
                         rulebook.STATUS_PASSED)


@unittest.skipUnless(HAS_NUMPY, "numpy indisponível")
class LascaDeContorno(unittest.TestCase):
    def test_erosao_apaga_linha_e_mantem_mancha(self):
        import numpy as np

        from sigmai.cartography.inspector import _erode

        linha = np.zeros((20, 20), dtype=bool)
        linha[10, :] = True
        mancha = np.zeros((20, 20), dtype=bool)
        mancha[4:12, 4:12] = True
        self.assertEqual(int(_erode(linha).sum()), 0)
        self.assertEqual(int(_erode(mancha).sum()), 36)


class FaixaInferiorPeloConteudo(unittest.TestCase):
    def _faixa(self, plan):
        return plan.slots["legend"].height

    def test_legenda_curta_devolve_altura_ao_mapa(self):
        fixa = solve_layout(page="A4 portrait")
        medida = solve_layout(page="A4 portrait", support_content_mm=18.0)
        self.assertEqual(fixa.arrangement, "faixa_inferior")
        self.assertAlmostEqual(self._faixa(medida), SUPPORT_BAND_MIN_MM)
        self.assertGreater(medida.map_frame().height, fixa.map_frame().height + 20.0)

    def test_legenda_longa_cresce_ate_o_teto(self):
        fixa = solve_layout(page="A4 portrait")
        longa = solve_layout(page="A4 portrait", support_content_mm=500.0)
        self.assertGreaterEqual(self._faixa(longa), self._faixa(fixa))

    def test_com_inserto_a_faixa_fica_fixa(self):
        fixa = solve_layout(page="A4 portrait", include_inset=True)
        medida = solve_layout(page="A4 portrait", include_inset=True, support_content_mm=18.0)
        self.assertAlmostEqual(self._faixa(medida), self._faixa(fixa))

    def test_seta_de_norte_proporcional_a_folha(self):
        for page in ("A4 portrait", "A4 landscape", "A3 portrait", "A0 landscape", "A5 portrait"):
            plan = solve_layout(page=page)
            lado = min(plan.page.width_mm, plan.page.height_mm)
            self.assertLessEqual(plan.slots["north"].height, max(11.0, lado * NORTH_MAX_PAGE_FRACTION) + 1e-6, page)


class OrientacaoNaoDita(unittest.TestCase):
    def test_pagina_que_ja_diz_a_orientacao(self):
        self.assertTrue(page_states_orientation("A4 retrato"))
        self.assertTrue(page_states_orientation("a3 landscape"))
        self.assertTrue(page_states_orientation({"width_mm": 85, "height_mm": 120}))
        self.assertTrue(page_states_orientation({"name": "A4", "orientation": "portrait"}))
        self.assertFalse(page_states_orientation("A4"))
        self.assertFalse(page_states_orientation(None))
        self.assertFalse(page_states_orientation({"name": "A3"}))


class MetodosDeClassificacao(unittest.TestCase):
    def test_metodos_publicados(self):
        self.assertEqual(GRADUATED_METHODS, ("equal_interval", "quantile", "jenks", "pretty"))

    def test_quantis_repartem_as_feicoes(self):
        valores = sorted(float((i * 37) % 101) for i in range(180))
        quebras = _class_breaks(valores, 4, "quantile")
        contagens = [sum(1 for v in valores if (quebras[k] < v <= quebras[k + 1]) or (k == 0 and v == quebras[0]))
                     for k in range(len(quebras) - 1)]
        self.assertLessEqual(max(contagens) - min(contagens), 4, (quebras, contagens))

    def test_jenks_separa_grupos_obvios(self):
        valores = sorted([1, 2, 2, 3, 3, 50, 51, 52, 53, 200, 201, 202])
        cortes = _jenks_cuts([float(v) for v in valores], 3)
        self.assertEqual(len(cortes), 2, cortes)
        self.assertTrue(3 <= cortes[0] < 50 and 53 <= cortes[1] < 200, cortes)

    def test_pretty_sao_numeros_redondos(self):
        valores = sorted([3.2, 17.9, 44.1, 58.0, 76.4, 97.3])
        for limite in _class_breaks(valores, 5, "pretty")[1:-1]:
            self.assertEqual(limite, round(limite), limite)


class RepositorioDePluginsComVersao(unittest.TestCase):
    """plugins.qgis.org responde 404 a plugins.xml sem ?qgis=; a busca e a instalação falhavam."""

    def test_url_sempre_leva_a_versao(self):
        from sigmai.qgis_actions.plugin_tools import _safe_repository_url

        self.assertIn("qgis=", _safe_repository_url())
        self.assertIn("qgis=3.34", _safe_repository_url(qgis_version="3.34"))
        self.assertIn("qgis=4.0", _safe_repository_url("https://plugins.qgis.org/plugins/plugins.xml?qgis=4.0"))


class IdiomaDoMapaNoMcp(unittest.TestCase):
    def _mcp(self):
        spec = importlib.util.spec_from_file_location("sigmai_mcp_review", ROOT / "sigmai" / "mcp" / "sigmai_mcp.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def test_obrigatorio_no_esquema(self):
        tools = {tool["name"]: tool for tool in self._mcp().TOOLS}
        self.assertIn("map_language", tools["sigmai_compose_map"]["inputSchema"]["required"])
        self.assertIn("map_language", tools["sigmai_plan_map"]["inputSchema"]["required"])

    def test_aviso_quando_falta(self):
        mcp = self._mcp()
        com = mcp._with_language_warning({"map_language": "en"}, {"ok": True})
        sem = mcp._with_language_warning({}, {"ok": True, "warnings": ["x"]})
        self.assertNotIn("warnings", com)
        self.assertIn("map_language", sem["warnings"][0])
        self.assertEqual(sem["warnings"][1], "x")


@unittest.skipUnless(HAS_QGIS, "PyQGIS indisponível")
class RevisaoNoQgis(unittest.TestCase):
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

    # --- dados sintéticos -------------------------------------------------
    def _poligonos(self, nome, celulas, campo_valor=None):
        from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=nome:string&field=valor:double", nome, "memory")
        feats = []
        for i, (x0, y0, lado) in enumerate(celulas):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(x0, y0, x0 + lado, y0 + lado)))
            feature.setAttribute("nome", f"{nome} {i}")
            feature.setAttribute("valor", float(i * 10 + 1))
            feats.append(feature)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _raster(self, pasta, nome="Elevacao", paleta=False):
        from osgeo import gdal, osr  # type: ignore
        from qgis.core import QgsProject, QgsRasterLayer

        caminho = os.path.join(pasta, f"{nome}.tif")
        ds = gdal.GetDriverByName("GTiff").Create(caminho, 60, 60, 1, gdal.GDT_Byte if paleta else gdal.GDT_Float32)
        ds.SetGeoTransform((480000, 500, 0, 9030000, 0, -500))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(31984)
        ds.SetProjection(srs.ExportToWkt())
        band = ds.GetRasterBand(1)
        import struct

        linhas = []
        for row in range(60):
            for col in range(60):
                linhas.append((row // 15) + 1 if paleta else 40.0 + row * 13.7 + col * 0.31)
        band.WriteRaster(0, 0, 60, 60, struct.pack(("B" if paleta else "f") * 3600, *linhas))
        band.FlushCache()
        ds = None
        layer = QgsRasterLayer(caminho, nome)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _compor(self, pasta, layers, subject, **extra):
        from sigmai.cartography.compose import compose_map

        params = {"layer_ids": [layer.id() for layer in layers], "subject_layer_id": subject.id(), "title": "Teste",
                  "map_author": "T", "data_source": "teste", "map_language": "en",
                  "output_path": os.path.join(pasta, "m.png"), "format": "png", "dpi": 96}
        params.update(extra)
        return compose_map(params, {"dry_run": False})

    @staticmethod
    def _status(resultado, rule_id):
        regras = resultado["audit"].get("results") or resultado["audit"].get("rules")
        return next(entry for entry in regras if entry["id"] == rule_id)["status"]

    # --- casos --------------------------------------------------------------
    def test_raster_assunto_fica_a_vista_sob_os_municipios(self):
        with pasta_temporaria() as pasta:
            dem = self._raster(pasta)
            muni = self._poligonos("Municipios", [(480000 + 10000 * i, 9000000 + 10000 * j, 10000)
                                                  for i in range(3) for j in range(3)])
            resultado = self._compor(pasta, [dem, muni], dem)
            self.assertEqual(self._status(resultado, "CART075"), rulebook.STATUS_PASSED)
            self.assertGreaterEqual(resultado["audit"]["observation"]["map"]["subject_visible_fraction"],
                                    rulebook.SUBJECT_VISIBLE_MIN)

    def test_legenda_do_raster_sem_nome_da_banda_e_com_extremos_redondos(self):
        from qgis.core import QgsSimpleLegendNode

        with pasta_temporaria() as pasta:
            dem = self._raster(pasta)
            muni = self._poligonos("Municipios", [(480000, 9000000, 30000)])
            self._compor(pasta, [dem, muni], dem)
            from qgis.core import QgsProject

            layout = QgsProject.instance().layoutManager().layouts()[-1]
            legend = next(item for item in layout.items() if getattr(item, "id", lambda: "")() == "legend")
            node = next(n for n in legend.model().rootGroup().findLayers() if n.layer().id() == dem.id())
            nodes = legend.model().layerLegendNodes(node)
            self.assertFalse(any(isinstance(n, QgsSimpleLegendNode) for n in nodes))
            fmt = dem.renderer().legendSettings().numericFormat()
            self.assertEqual(fmt.formatDouble(867.538, _contexto_numerico()), "868")

    def test_camada_dependente_de_escala_nao_e_fantasma(self):
        with pasta_temporaria() as pasta:
            parcelas = self._poligonos("Parcelas", [(480000, 9000000, 8000)])
            parcelas.setScaleBasedVisibility(True)
            parcelas.setMinimumScale(100000)
            parcelas.setMaximumScale(0)
            resultado = self._compor(pasta, [parcelas], parcelas, scale=50000, page="A3 landscape")
            self.assertEqual(self._status(resultado, "CART021"), rulebook.STATUS_PASSED)

    def test_contorno_do_estado_nao_reprova_cart070(self):
        with pasta_temporaria() as pasta:
            estado = self._poligonos("Estado", [(300000, 8800000, 400000)])
            muni = self._poligonos("Municipios", [(320000 + 60000 * i, 8820000 + 60000 * j, 60000)
                                                  for i in range(5) for j in range(5)])
            parque = self._poligonos("Parque", [(480000, 9000000, 20000)])
            resultado = self._compor(pasta, [estado, muni, parque], muni)
            self.assertNotEqual(self._status(resultado, "CART070"), rulebook.STATUS_FAIL)

    def test_cinza_mantem_as_classes_graduadas(self):
        from qgis.core import QgsFillSymbol, QgsGraduatedSymbolRenderer, QgsRendererRange

        with pasta_temporaria() as pasta:
            muni = self._poligonos("Municipios", [(480000 + 10000 * i, 9000000, 10000) for i in range(5)])
            cores = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"]
            faixas = []
            for i, cor in enumerate(cores):
                simbolo = QgsFillSymbol.createSimple({"color": cor})
                faixas.append(QgsRendererRange(i * 10, i * 10 + 10, simbolo, f"c{i}"))
            muni.setRenderer(QgsGraduatedSymbolRenderer("valor", faixas))
            from sigmai.cartography.symbology import mark_style_origin, STYLE_ORIGIN_USER

            mark_style_origin(muni, STYLE_ORIGIN_USER)
            resultado = self._compor(pasta, [muni], muni, colour_mode="greyscale")
            cinzas = [r.symbol().color() for r in muni.renderer().ranges()]
            self.assertEqual(len({c.name() for c in cinzas}), 5)
            for c in cinzas:
                self.assertTrue(c.red() == c.green() == c.blue(), c.name())
            lum = [c.red() for c in cinzas]
            self.assertEqual(lum, sorted(lum, reverse=True))
            self.assertEqual(self._status(resultado, "CART073"), rulebook.STATUS_PASSED)

    def test_cinza_mantem_as_classes_do_raster_paletado(self):
        from qgis.core import QgsPalettedRasterRenderer
        from qgis.PyQt.QtGui import QColor

        with pasta_temporaria() as pasta:
            uso = self._raster(pasta, "Uso", paleta=True)
            classes = [QgsPalettedRasterRenderer.Class(v, QColor(c), f"classe {v}")
                       for v, c in ((1, "#1b9e77"), (2, "#d95f02"), (3, "#7570b3"), (4, "#e7298a"))]
            uso.setRenderer(QgsPalettedRasterRenderer(uso.dataProvider(), 1, classes))
            self._compor(pasta, [uso], uso, colour_mode="greyscale")
            cinzas = [c.color for c in uso.renderer().classes()]
            self.assertEqual(len({c.name() for c in cinzas}), 4)
            for c in cinzas:
                self.assertTrue(c.red() == c.green() == c.blue(), c.name())

    def test_recorte_alto_sai_em_retrato_sem_orientacao_pedida(self):
        with pasta_temporaria() as pasta:
            alto = self._poligonos("Alto", [(480000, 9000000 + 20000 * k, 20000) for k in range(6)])
            resultado = self._compor(pasta, [alto], alto)
            self.assertEqual(resultado["page"]["orientation"], "portrait")


def _contexto_numerico():
    from qgis.core import QgsNumericFormatContext

    return QgsNumericFormatContext()


if __name__ == "__main__":
    unittest.main()
