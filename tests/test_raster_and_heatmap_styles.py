"""apply_raster_style, apply_heatmap_style, rótulos do graduado e declividade em graus.

Sem esses comandos um assistente não fazia hipsometria, declividade por
classes, uso da terra com nomes nem mapa de calor — os mapas mais pedidos em
laudo ambiental.
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

from sigmai.qgis_actions.raster_style import (  # noqa: E402
    SLOPE_PRESETS, blend_mode_name, class_labels, decimals_for, format_number, interpolate_hex, validate_breaks,
)
from sigmai.validators import ValidationError  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


class Puras(unittest.TestCase):
    def test_numero_na_lingua_do_mapa(self):
        self.assertEqual(format_number(15000, 0, "pt-BR"), "15.000")
        self.assertEqual(format_number(15000, 0, "en"), "15,000")
        self.assertEqual(format_number(3.5, 1, "pt-BR"), "3,5")
        self.assertEqual(format_number(3.5, 1, "en"), "3.5")

    def test_rotulos_de_classe(self):
        self.assertEqual(class_labels([0, 3, 8, None], "%", "pt-BR"), ["0–3%", "3–8%", "> 8%"])
        self.assertEqual(class_labels([6323, 15000, 40000], "", "en"), ["6,323–15,000", "15,000–40,000"])
        self.assertEqual(class_labels([0.0, 0.5, 1.0], "m", "pt-BR"), ["0,00–0,50 m", "0,50–1,00 m"])

    def test_casas_pela_largura_da_classe(self):
        self.assertEqual(decimals_for(250), 0)
        self.assertEqual(decimals_for(2.5), 1)
        self.assertEqual(decimals_for(0.25), 2)

    def test_rampa_propria_interpola(self):
        self.assertEqual(interpolate_hex(("#000000", "#ffffff"), 0.5), "#808080")
        self.assertEqual(interpolate_hex(("#000000", "#ffffff"), 1.0), "#ffffff")

    def test_limites_validados(self):
        self.assertEqual(validate_breaks([0, 3, None]), [0.0, 3.0, None])
        for ruim in ([5], [3, 1], [0, None, 5], ["a", 1], [0, float("inf")]):
            with self.assertRaises(ValidationError):
                validate_breaks(ruim)

    def test_modo_de_mistura(self):
        self.assertEqual(blend_mode_name("Multiplicar"), "multiply")
        self.assertEqual(blend_mode_name(None), "normal")
        with self.assertRaises(ValidationError):
            blend_mode_name("dissolve")

    def test_preset_da_embrapa(self):
        preset = SLOPE_PRESETS["declividade_embrapa"]
        self.assertEqual(preset["breaks"], [0.0, 3.0, 8.0, 20.0, 45.0, 75.0, None])
        for language, labels in preset["labels"].items():
            self.assertEqual(len(labels), 6, language)


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
        from qgis.core import QgsProject

        QgsProject.instance().clear()

    def _raster(self, pasta, epsg=31984, categorias=False):
        import struct

        from osgeo import gdal, osr  # type: ignore
        from qgis.core import QgsProject, QgsRasterLayer

        caminho = os.path.join(pasta, f"r{epsg}{int(categorias)}.tif")
        ds = gdal.GetDriverByName("GTiff").Create(caminho, 40, 40, 1, gdal.GDT_Byte if categorias else gdal.GDT_Float32)
        if epsg == 4326:
            ds.SetGeoTransform((-41.8, 0.001, 0, -4.1, 0, -0.001))
        else:
            ds.SetGeoTransform((480000, 100, 0, 9000000, 0, -100))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)
        ds.SetProjection(srs.ExportToWkt())
        valores = [((r // 10) * 10 + 10) if categorias else 40.0 + r * 20.0 + c for r in range(40) for c in range(40)]
        ds.GetRasterBand(1).WriteRaster(0, 0, 40, 40, struct.pack(("B" if categorias else "f") * 1600, *valores))
        ds = None
        layer = QgsRasterLayer(caminho, "r")
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _pontos(self, n=50):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

        layer = QgsVectorLayer("Point?crs=EPSG:31984&field=peso:double", "focos", "memory")
        feats = []
        for i in range(n):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(480000 + (i * 137) % 4000, 9000000 - (i * 89) % 4000)))
            f.setAttribute("peso", float(i % 7))
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_hipsometria_continua_com_legenda_redonda(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            layer = self._raster(pasta)
            out = apply_raster_style({"layer_id": layer.id(), "unit": "m", "map_language": "en"}, {"dry_run": False})
            self.assertEqual(out["mode"], "pseudocolor")
            self.assertEqual(str(layer.renderer().type()), "singlebandpseudocolor")
            settings = layer.renderer().shader().rasterShaderFunction().legendSettings()
            self.assertEqual(settings.suffix(), " m")

    def test_declividade_embrapa_em_ingles(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            layer = self._raster(pasta)
            out = apply_raster_style({"layer_id": layer.id(), "preset": "embrapa", "map_language": "en"}, {"dry_run": False})
            itens = layer.renderer().shader().rasterShaderFunction().colorRampItemList()
            self.assertEqual([i.label for i in itens], SLOPE_PRESETS["declividade_embrapa"]["labels"]["en"])
            self.assertEqual(itens[-1].value, float("inf"))
            self.assertEqual(out["preset"], "declividade_embrapa")

    def test_valores_unicos_com_nomes(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            layer = self._raster(pasta, categorias=True)
            apply_raster_style({"layer_id": layer.id(), "mode": "unique_values",
                                "labels": {"10": "Floresta", "20": "Savana", "30": "Pasto", "40": "Água"}},
                               {"dry_run": False})
            nomes = {c.label for c in layer.renderer().classes()}
            self.assertTrue({"Floresta", "Savana", "Pasto", "Água"} <= nomes, nomes)

    def test_sombreado_em_graus_ganha_fator(self):
        from sigmai.qgis_actions.raster_style import apply_raster_style

        with pasta_temporaria() as pasta:
            layer = self._raster(pasta, epsg=4326)
            out = apply_raster_style({"layer_id": layer.id(), "mode": "hillshade", "blend_mode": "multiply",
                                      "opacity": 0.5}, {"dry_run": False})
            self.assertAlmostEqual(out["z_factor"], 1 / 111120.0)
            self.assertEqual(str(layer.renderer().type()), "hillshade")

    def test_declividade_em_graus_usa_escala(self):
        from sigmai.qgis_actions.raster import raster_slope

        with pasta_temporaria() as pasta:
            layer = self._raster(pasta, epsg=4326)
            out = raster_slope({"layer_id": layer.id(), "as_percent": True}, {"dry_run": True})
            self.assertEqual(out["parameters"]["SCALE"], 111120.0)
            self.assertTrue(out["parameters"]["AS_PERCENT"])

    def test_mapa_de_calor(self):
        from sigmai.qgis_actions.symbology import apply_heatmap_style

        layer = self._pontos()
        out = apply_heatmap_style({"layer_id": layer.id(), "radius": 8, "weight_field": "peso", "map_language": "en"},
                                  {"dry_run": False})
        self.assertEqual(out["style_type"], "heatmap")
        self.assertEqual(str(layer.renderer().type()), "heatmapRenderer")
        self.assertEqual(layer.renderer().legendSettings().maximumLabel(), "Higher density")
        self.assertEqual(layer.renderer().colorRamp().color1().alpha(), 0)

    def test_mapa_de_calor_recusa_poligono(self):
        from qgis.core import QgsProject, QgsVectorLayer

        from sigmai.qgis_actions.symbology import apply_heatmap_style

        layer = QgsVectorLayer("Polygon?crs=EPSG:31984", "p", "memory")
        QgsProject.instance().addMapLayer(layer)
        with self.assertRaises(ValidationError):
            apply_heatmap_style({"layer_id": layer.id()}, {"dry_run": False})

    def test_graduado_com_rotulos_e_rampa(self):
        from sigmai.qgis_actions.symbology import apply_graduated_style

        layer = self._pontos()
        out = apply_graduated_style({"layer_id": layer.id(), "field_name": "peso", "classes": 3, "method": "equal_interval",
                                     "color_ramp": "Viridis", "map_language": "en"}, {"dry_run": False})
        rotulos = [r.label() for r in layer.renderer().ranges()]
        self.assertEqual(rotulos, out["labels"])
        self.assertEqual(rotulos, ["0–2", "2–4", "4–6"])
        cores = [r.symbol().color().name() for r in layer.renderer().ranges()]
        self.assertEqual(len(set(cores)), len(cores))


if __name__ == "__main__":
    unittest.main()
