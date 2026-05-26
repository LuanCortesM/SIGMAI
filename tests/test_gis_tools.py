import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qgis_plugin.qgis_actions.gis_tools import PROCESSING_ALLOWLIST  # noqa: E402
from qgis_plugin.permissions import permission_for  # noqa: E402


class GisToolsTests(unittest.TestCase):
    def test_processing_allowlist_contains_only_expected_safe_algorithms(self):
        self.assertIn("native:buffer", PROCESSING_ALLOWLIST)
        self.assertIn("native:clip", PROCESSING_ALLOWLIST)
        self.assertIn("native:fixgeometries", PROCESSING_ALLOWLIST)
        self.assertNotIn("qgis:executesql", PROCESSING_ALLOWLIST)

    def test_high_level_gis_commands_support_dry_run(self):
        for action in ["fix_geometries", "buffer", "clip", "dissolve", "reproject_layer", "export_layer"]:
            permission = permission_for(action)
            self.assertIsNotNone(permission)
            self.assertTrue(permission.supports_dry_run)


if __name__ == "__main__":
    unittest.main()
