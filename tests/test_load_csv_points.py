"""Planilha de pontos (CSV) vira camada: sítios de campanha raramente chegam como shapefile.

Na emulação da 1.1.0 o assistente remoto não tinha como pôr no mapa os
sítios de coleta de uma planilha — load_vector_layer só aceitava OGR.
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

from sigmai.qgis_actions.load_layers import delimited_text_uri  # noqa: E402
from sigmai.validators import ValidationError  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


def _escreve(pasta: str, nome: str, texto: str, encoding: str = "utf-8") -> Path:
    caminho = Path(pasta) / nome
    caminho.write_text(texto, encoding=encoding)
    return caminho


class DeteccaoDaPlanilha(unittest.TestCase):
    def test_lon_lat_com_virgula_assume_wgs84(self):
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "sitios.csv", "codigo,sitio,lon,lat\nS1,Cachoeira,-45.07,-22.49\nS2,Mirante,-45.06,-22.49\n")
            d = delimited_text_uri(csv_path)
            self.assertEqual((d["x_field"], d["y_field"], d["crs"], d["delimiter"], d["decimal"]), ("lon", "lat", "EPSG:4326", ",", "."))
            self.assertIn("xField=lon&yField=lat&crs=EPSG:4326", d["uri"])
            self.assertTrue(d["uri"].startswith("file:///"))

    def test_ponto_e_virgula_com_decimal_brasileiro(self):
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "sitios.csv", "Sítio;Longitude;Latitude\nBrejo;-45,059;-22,493\nCapão;-45,035;-22,487\n")
            d = delimited_text_uri(csv_path)
            self.assertEqual((d["x_field"], d["y_field"], d["delimiter"], d["decimal"]), ("Longitude", "Latitude", ";", ","))
            self.assertIn("delimiter=;", d["uri"]); self.assertIn("decimalPoint=,", d["uri"])

    def test_utm_sem_crs_e_recusado_com_nome_das_colunas(self):
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "utm.csv", "id,este,norte\n1,262000,9640000\n")
            with self.assertRaises(ValidationError) as ctx:
                delimited_text_uri(csv_path)
            self.assertEqual(ctx.exception.code, "CRS_REQUIRED")
            self.assertIn("este", str(ctx.exception))
            d = delimited_text_uri(csv_path, crs="EPSG:31984")
            self.assertEqual((d["x_field"], d["y_field"], d["crs"]), ("este", "norte", "EPSG:31984"))

    def test_sem_coluna_de_coordenada_ou_coluna_errada(self):
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "x.csv", "id,nome,altitude\n1,a,900\n")
            with self.assertRaises(ValidationError) as ctx:
                delimited_text_uri(csv_path)
            self.assertEqual(ctx.exception.code, "COORDINATE_FIELDS_NOT_FOUND")
            with self.assertRaises(ValidationError) as ctx:
                delimited_text_uri(csv_path, x_field="lon", y_field="lat")
            self.assertEqual(ctx.exception.code, "FIELD_NOT_FOUND")

    def test_latin1_e_detectado(self):
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "l.csv", "sitio,lon,lat\nCapão,-45.0,-22.4\n", encoding="ISO-8859-1")
            d = delimited_text_uri(csv_path)
            self.assertEqual(d["encoding"], "ISO-8859-1")


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class PlanilhaNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def test_carrega_csv_e_compoe_mapa_de_campanha(self):
        from qgis.core import QgsProject

        from sigmai.qgis_actions.campaign import compose_campaign_map
        from sigmai.qgis_actions.load_layers import handle as load_vector_layer

        QgsProject.instance().clear()
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "sitios.csv", "Sítio;Longitude;Latitude\nBrejo;-45,059;-22,493\nCapão;-45,035;-22,487\nMirante;-45,065;-22,495\n")
            plano = load_vector_layer({"path": str(csv_path), "name": "Sítios"}, {"dry_run": True})
            self.assertTrue(plano["dry_run"])
            self.assertEqual(plano["detected"]["decimal"], ",")
            self.assertEqual(len(QgsProject.instance().mapLayers()), 0)

            r = load_vector_layer({"path": str(csv_path), "name": "Sítios"}, {"dry_run": False})
            self.assertEqual(r["provider"], "delimitedtext")
            self.assertEqual(r["feature_count"], 3)
            self.assertEqual(r["crs"], "EPSG:4326")
            camada = QgsProject.instance().mapLayer(r["layer_id"])
            nomes = sorted(f["Sítio"] for f in camada.getFeatures())
            self.assertEqual(nomes, ["Brejo", "Capão", "Mirante"])
            x = [f.geometry().asPoint().x() for f in camada.getFeatures()][0]
            self.assertLess(x, -45.0)

            c = compose_campaign_map({"points_layer_id": r["layer_id"], "title": "Campanha", "map_author": "T",
                                      "data_source": "GPS", "output_path": os.path.join(pasta, "c.png"), "dpi": 72},
                                     {"dry_run": False})
            self.assertEqual(c["campaign"]["resolved"]["label_field"], "Sítio")
            self.assertEqual((c["audit"]["observation"]["map"].get("labels") or {}).get("placed"), 3)

    def test_csv_com_coordenadas_erradas_nao_vira_camada_vazia_em_silencio(self):
        from qgis.core import QgsProject

        from sigmai.qgis_actions.load_layers import handle as load_vector_layer

        QgsProject.instance().clear()
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = _escreve(pasta, "ruim.csv", "id,lon,lat\n1,abc,def\n")
            with self.assertRaises(ValidationError) as ctx:
                load_vector_layer({"path": str(csv_path)}, {"dry_run": False})
            self.assertIn(ctx.exception.code, ("EMPTY_LAYER", "INVALID_VECTOR_LAYER"))
            self.assertEqual(len(QgsProject.instance().mapLayers()), 0)


if __name__ == "__main__":
    unittest.main()
