"""Mapa de campanha (pontos + trilha + área + contexto + inserto) e tabela de coordenadas."""

from __future__ import annotations

import csv
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.cartography.layoutgrid import TEMPLATES  # noqa: E402
from sigmai.permissions import COMMAND_PERMISSIONS  # noqa: E402
from sigmai.qgis_actions.campaign import MAX_AUTO_LABELLED_POINTS, build_campaign_params  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


class ParametrosDeCampanha(unittest.TestCase):
    RESOLVED = {
        "points": {"id": "p", "name": "Sítios"}, "track": {"id": "t", "name": "Trilha"},
        "areas": [{"id": "a", "name": "UC"}], "context": [{"id": "c", "name": "Municípios"}],
        "inset": [{"id": "i", "name": "Estado"}], "label_field": "nome", "subject_ids": ["p", "t"],
    }

    def test_ordem_das_camadas_e_assunto(self):
        compose = build_campaign_params({"title": "Campanha", "campaign_dates": "mar/2025", "dpi": 300, "page": "A4"}, self.RESOLVED)
        self.assertEqual(compose["layer_ids"], ["p", "t", "a", "c"])
        self.assertEqual(compose["subject_layer_id"], ["p", "t"])
        self.assertEqual(compose["template"], "campanha")
        self.assertTrue(compose["include_inset"])
        self.assertEqual(compose["inset_layer_ids"], ["i"])
        self.assertEqual(compose["label_field"], "nome")
        self.assertEqual(compose["label_layer_id"], "p")
        self.assertEqual(compose["subtitle"], "Campanha de campo: mar/2025")
        self.assertEqual(compose["dpi"], 300)
        self.assertEqual(compose["page"], "A4")

    def test_sem_trilha_nem_inserto(self):
        resolved = {**self.RESOLVED, "track": None, "inset": [], "subject_ids": ["p"], "label_field": None}
        compose = build_campaign_params({}, resolved)
        self.assertEqual(compose["layer_ids"], ["p", "a", "c"])
        self.assertFalse(compose["include_inset"])
        self.assertNotIn("label_field", compose)
        self.assertEqual(compose["title"], "Pontos de coleta — Sítios")

    def test_template_e_catalogo(self):
        self.assertIn("campanha", TEMPLATES)
        self.assertEqual(COMMAND_PERMISSIONS["compose_campaign_map"].permission_level, "safe_write")
        self.assertEqual(COMMAND_PERMISSIONS["export_coordinate_table"].permission_level, "safe_write")


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class CampanhaNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _cenario(self, n_points: int = 4):
        from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle, QgsVectorLayer

        project = QgsProject.instance()
        project.clear()
        pontos = QgsVectorLayer("Point?crs=EPSG:31984&field=sitio:string&field=track_fid:integer", "Sítios", "memory")
        feats = []
        for i in range(n_points):
            f = QgsFeature(pontos.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1000 + i * 300, 1000 + (i % 2) * 200)))
            f.setAttributes([f"S{i + 1}", 0])
            feats.append(f)
        pontos.dataProvider().addFeatures(feats)
        pontos.updateExtents()
        trilha = QgsVectorLayer("LineString?crs=EPSG:31984&field=n:string", "Trilha", "memory")
        f = QgsFeature(trilha.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(800, 900), QgsPointXY(3000, 1500), QgsPointXY(4000, 900)]))
        f.setAttributes(["t"])
        trilha.dataProvider().addFeatures([f])
        trilha.updateExtents()
        area = QgsVectorLayer("Polygon?crs=EPSG:31984&field=n:string", "UC", "memory")
        f = QgsFeature(area.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 5000, 3000)))
        f.setAttributes(["UC"])
        area.dataProvider().addFeatures([f])
        area.updateExtents()
        project.addMapLayers([pontos, trilha, area])
        return pontos, trilha, area

    def test_compoe_com_pontos_trilha_area_e_tabela(self):
        from sigmai.qgis_actions.campaign import compose_campaign_map

        pontos, trilha, area = self._cenario()
        with tempfile.TemporaryDirectory() as pasta:
            r = compose_campaign_map({
                "points_layer_id": pontos.id(), "track_layer_id": trilha.id(), "area_layer_ids": [area.id()],
                "title": "Campanha", "map_author": "T", "data_source": "GPS 2025", "campaign_dates": "março de 2025",
                "output_path": os.path.join(pasta, "c.png"), "dpi": 72,
                "coordinate_table_path": os.path.join(pasta, "pontos.csv"), "table_crs": "EPSG:4674",
            }, {"dry_run": False})
            self.assertEqual(r["template"], "campanha")
            self.assertEqual(r["campaign"]["compose_params"]["subject_layer_id"], [pontos.id(), trilha.id()])
            self.assertEqual(r["campaign"]["resolved"]["label_field"], "sitio")
            labels = r["audit"]["observation"]["map"].get("labels") or {}
            self.assertEqual(labels.get("placed"), 4)
            # A trilha vai além dos pontos: o recorte contém os dois.
            extent = r["extent"]
            self.assertLessEqual(extent["xmin"], 800)
            self.assertGreaterEqual(extent["xmax"], 4000)
            tabela = r["coordinate_table"]
            self.assertEqual(tabela["rows"], 4)
            with open(os.path.join(pasta, "pontos.csv"), encoding="utf-8-sig", newline="") as handle:
                linhas = list(csv.reader(handle))
            self.assertEqual(linhas[0][:2], ["fid", "sitio"])
            self.assertIn("lon (EPSG:4674)", linhas[0])
            self.assertIn("latitude (EPSG:4326)", linhas[0])
            self.assertEqual(len(linhas), 5)
            self.assertEqual(linhas[1][1], "S1")

    def test_muitos_pontos_nao_sao_rotulados_sozinhos(self):
        from sigmai.qgis_actions.campaign import compose_campaign_map

        pontos, _, _ = self._cenario(n_points=MAX_AUTO_LABELLED_POINTS + 5)
        r = compose_campaign_map({"points_layer_id": pontos.id(), "title": "x", "map_author": "t", "data_source": "s"}, {"dry_run": True})
        self.assertIsNone(r["campaign"]["resolved"]["label_field"])
        self.assertTrue(any("sem rótulo" in n for n in r["notes"]))
        r = compose_campaign_map({"points_layer_id": pontos.id(), "label_field": "sitio", "title": "x", "map_author": "t", "data_source": "s"}, {"dry_run": True})
        self.assertEqual(r["campaign"]["resolved"]["label_field"], "sitio")

    def test_recusas(self):
        from sigmai.qgis_actions.campaign import compose_campaign_map, export_coordinate_table
        from sigmai.validators import ValidationError

        pontos, trilha, area = self._cenario()
        with self.assertRaises(ValidationError) as ctx:
            compose_campaign_map({"points_layer_id": trilha.id(), "title": "x"}, {"dry_run": True})
        self.assertEqual(ctx.exception.code, "GEOMETRY_TYPE_MISMATCH")
        with self.assertRaises(ValidationError) as ctx:
            compose_campaign_map({"points_layer_id": pontos.id(), "label_field": "nada", "title": "x"}, {"dry_run": True})
        self.assertEqual(ctx.exception.code, "FIELD_NOT_FOUND")
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ValidationError) as ctx:
                export_coordinate_table({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "t.xlsx")}, {})
            self.assertEqual(ctx.exception.code, "BAD_REQUEST")
            with self.assertRaises(ValidationError) as ctx:
                export_coordinate_table({"layer_id": pontos.id(), "output_path": os.path.join(pasta, "t.csv"), "crs": "EPSG:999999"}, {})
            self.assertEqual(ctx.exception.code, "BAD_REQUEST")
            plano = export_coordinate_table({"layer_id": area.id(), "output_path": os.path.join(pasta, "a.csv"), "fields": ["n"]}, {"dry_run": True})
            self.assertTrue(plano["dry_run"])
            self.assertTrue(any("ponto representativo" in n for n in plano["notes"]))
            self.assertFalse(os.path.exists(os.path.join(pasta, "a.csv")))


if __name__ == "__main__":
    unittest.main()
