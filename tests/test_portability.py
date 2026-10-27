"""O que a primeira rodada da suíte no QGIS em Linux e no macOS mostrou (1.3.0).

* Sem a biblioteca de estilos do QGIS (QGIS sem interface, em Linux), as
  rampas "Spectral" e "Viridis" eram recusadas, e o estilo categorizado com
  mais classes que as cores qualitativas quebrava.
* No QGIS 4 das imagens oficiais em Linux o Qt não tinha o plugin de TIFF, e
  a exportação em TIFF, que as revistas pedem, falhava.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qgis_temp import pasta_temporaria  # noqa: E402

HAS_QGIS = importlib.util.find_spec("qgis") is not None


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

    def test_rampas_comuns_sem_a_biblioteca_de_estilos(self):
        import qgis.core

        from sigmai.qgis_actions.raster_style import qgis_ramp
        from sigmai.validators import ValidationError

        with mock.patch.object(qgis.core.QgsStyle, "defaultStyle", return_value=qgis.core.QgsStyle()):
            self.assertEqual(qgis_ramp("Spectral").color(0.0).name(), "#d7191c")
            self.assertEqual(qgis_ramp("viridis").color(1.0).name(), "#fde725")
            with self.assertRaises(ValidationError):
                qgis_ramp("NaoExiste")

    def test_tiff_pelo_gdal_quando_o_qt_nao_grava_tiff(self):
        from osgeo import gdal  # type: ignore
        from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

        import sigmai.cartography.compose as compose

        QgsProject.instance().clear()
        QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:31983"))
        camada = QgsVectorLayer("Polygon?crs=EPSG:31983", "Park", "memory")
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt("POLYGON((520000 7515000,545000 7515000,545000 7535000,520000 7535000,"
                                          "520000 7515000))"))
        camada.dataProvider().addFeatures([f])
        camada.updateExtents()
        QgsProject.instance().addMapLayer(camada)
        with pasta_temporaria() as pasta, mock.patch.object(compose, "_qt_writes_tiff", return_value=False):
            saida = os.path.join(pasta, "figura.tif")
            resultado = compose.compose_map({
                "layer_ids": [camada.id()], "title": "Park", "data_source": "CNUC/MMA", "map_language": "en",
                "figure_width_mm": 88, "title_placement": "caption", "output_path": saida, "dpi": 150,
            }, {"dry_run": False})
            imagem = gdal.Open(saida)
            resolucao = imagem.GetMetadataItem("TIFFTAG_XRESOLUTION")
            largura = imagem.RasterXSize
            imagem = None
            sobras = [n for n in os.listdir(pasta) if "sigmai-tmp" in n]
        self.assertTrue(resultado["export"]["exists"])
        self.assertEqual(float(resolucao), 150.0)
        self.assertAlmostEqual(largura, round(88 / 25.4 * 150), delta=2)
        self.assertEqual(sobras, [])


if __name__ == "__main__":
    unittest.main()
