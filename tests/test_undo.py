"""Desfazer: snapshot antes de cada escrita no projeto, restauração depois."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sigmai.permissions import COMMAND_PERMISSIONS  # noqa: E402
from sigmai.undo import EXCLUDED_ACTIONS, LAYER_KEYS, UndoStack, _collect_ids, _collect_paths  # noqa: E402
from qgis_temp import pasta_temporaria  # noqa: E402


def _pyqgis_disponivel() -> bool:
    return importlib.util.find_spec("qgis") is not None


class ColetaDeReferencias(unittest.TestCase):
    def test_ids_de_camada_em_qualquer_profundidade(self):
        params = {"layer_ids": ["a", "b"], "subject_layer_id": "a", "second_map": {"layer_ids": ["c"]},
                  "panels": [{"layer_ids": ["d"]}], "title": "x", "inset_layer_ids": ["e"]}
        self.assertEqual(_collect_ids(params, LAYER_KEYS), ["a", "b", "c", "d", "e"])

    def test_caminhos_de_saida(self):
        params = {"output_path": "/x/m.png", "recipe_path": "/x/m.json", "output_gpkg": "/x/c.gpkg", "title": "/nao"}
        self.assertEqual(_collect_paths(params), ["/x/m.png", "/x/m.json", "/x/c.gpkg"])

    def test_acoes_de_desfazer_nao_entram_na_pilha(self):
        self.assertIn("undo_last_action", EXCLUDED_ACTIONS)
        self.assertEqual(COMMAND_PERMISSIONS["undo_last_action"].permission_level, "safe_write")
        self.assertEqual(COMMAND_PERMISSIONS["list_undo_history"].permission_level, "read_only")

    def test_pilha_vazia_diz_que_nao_ha_nada(self):
        stack = UndoStack()
        self.assertEqual(stack.history(), [])
        resultado = stack.undo_last()
        self.assertFalse(resultado["undone"])
        stack.commit(None, "ok")  # snapshot indisponível não quebra nada
        self.assertEqual(stack.history(), [])


@unittest.skipUnless(_pyqgis_disponivel(), "PyQGIS ausente: só existe dentro de uma instalação do QGIS")
class DesfazerNoQgis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")  # offscreen no Windows não tem fontes
        from qgis.core import QgsApplication

        cls.app = QgsApplication.instance() or QgsApplication([], False)
        if not getattr(cls.app, "_sigmai_iniciado", False):
            cls.app.initQgis()
            cls.app._sigmai_iniciado = True

    def _registro(self):
        from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer

        from sigmai.command_registry import CommandRegistry
        from sigmai.qgis_actions import register_actions

        project = QgsProject.instance()
        project.clear()
        layer = QgsVectorLayer("Polygon?crs=EPSG:31984&field=n:string", "Quadrado", "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1000, 1000)))
        f.setAttributes(["q"])
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        project.addMapLayer(layer)
        registry = CommandRegistry({"qgis_version": "3.34"})
        register_actions(registry)
        return registry, layer

    def _run(self, registry, action, params, dry_run=False):
        response = registry.execute({"schema_version": "0.3", "action": action, "params": params, "dry_run": dry_run})
        self.assertTrue(response["ok"], response.get("errors"))
        return response["data"]

    def test_estilo_layout_e_substituicao_sao_desfeitos(self):
        from qgis.core import QgsProject

        registry, layer = self._registro()
        cor_original = layer.renderer().symbol().color().name()
        self._run(registry, "apply_single_symbol", {"layer_id": layer.id(), "fill_color": "#FF0000"})
        self.assertEqual(layer.renderer().symbol().color().name(), "#ff0000")
        historico = self._run(registry, "list_undo_history", {})
        self.assertEqual(historico["entries"][0]["action"], "apply_single_symbol")
        self.assertEqual(historico["entries"][0]["touched_layers"], ["Quadrado"])

        with pasta_temporaria() as pasta:
            saida = os.path.join(pasta, "m.png")
            self._run(registry, "compose_map", {"layer_ids": [layer.id()], "title": "Primeiro", "map_author": "a", "data_source": "s",
                                                "output_path": saida, "format": "png", "dpi": 72, "layout_name": "L"})
            self.assertIsNotNone(QgsProject.instance().layoutManager().layoutByName("L"))
            self._run(registry, "compose_map", {"layer_ids": [layer.id()], "title": "Segundo", "map_author": "a", "data_source": "s",
                                                "layout_name": "L"})
            # dry_run não entra na pilha
            self._run(registry, "compose_map", {"layer_ids": [layer.id()], "title": "Seco", "layout_name": "L"}, dry_run=True)
            self.assertEqual(len(self._run(registry, "list_undo_history", {})["entries"]), 3)

            desfeito = self._run(registry, "undo_last_action", {})
            self.assertTrue(desfeito["undone"])
            self.assertEqual(desfeito["restored_layouts"], ["L"])
            titulo = [i.text() for i in QgsProject.instance().layoutManager().layoutByName("L").items()
                      if type(i).__name__ == "QgsLayoutItemLabel" and i.id() == "title"]
            self.assertEqual(titulo, ["Primeiro"])

            desfeito = self._run(registry, "undo_last_action", {})
            self.assertEqual(desfeito["removed_layouts"], ["L"])
            self.assertEqual(desfeito["files_kept"], [saida])
            self.assertTrue(os.path.exists(saida))
            self.assertIsNone(QgsProject.instance().layoutManager().layoutByName("L"))

            desfeito = self._run(registry, "undo_last_action", {})
            self.assertEqual(desfeito["restored_layers"], ["Quadrado"])
            self.assertEqual(layer.renderer().symbol().color().name(), cor_original)

            nada = self._run(registry, "undo_last_action", {})
            self.assertFalse(nada["undone"])

    def test_camadas_criadas_sao_removidas(self):
        from qgis.core import QgsProject

        registry, layer = self._registro()
        criado = self._run(registry, "add_context_annotations", {"boundary_layer_id": layer.id(), "label_text": "Q"})
        ids = [c["id"] for c in criado["created_layers"]]
        self.assertTrue(all(QgsProject.instance().mapLayer(i) is not None for i in ids))
        desfeito = self._run(registry, "undo_last_action", {})
        self.assertEqual(sorted(desfeito["removed_layers"]), sorted(["Divisa — Quadrado", "Nomes — Quadrado"]))
        self.assertTrue(all(QgsProject.instance().mapLayer(i) is None for i in ids))


if __name__ == "__main__":
    unittest.main()
