import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qgis_plugin.qgis_actions import plugin_tools  # noqa: E402
from qgis_plugin.validators import ValidationError  # noqa: E402


def make_plugin(root: Path, name: str = "sample_plugin") -> Path:
    plugin = root / name
    plugin.mkdir()
    (plugin / "metadata.txt").write_text(
        "[general]\nname=Sample Plugin\ndescription=Test\nversion=0.1\nqgisminimumversion=3.28\nauthor=SIGMAI\nexperimental=True\nicon=icons/icon.svg\n",
        encoding="utf-8",
    )
    (plugin / "__init__.py").write_text("from .plugin import classFactory\n", encoding="utf-8")
    (plugin / "plugin.py").write_text("from qgis.PyQt.QtWidgets import QAction\nfrom . import resources\n", encoding="utf-8")
    (plugin / "icons").mkdir()
    (plugin / "icons" / "icon.svg").write_text("<svg></svg>", encoding="utf-8")
    (plugin / "__pycache__").mkdir()
    (plugin / "__pycache__" / "plugin.pyc").write_bytes(b"compiled")
    return plugin


class PluginManagementTests(unittest.TestCase):
    def test_static_import_check_does_not_execute_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_plugin(root)
            with patch.object(plugin_tools, "_plugin_roots", return_value=[root]):
                result = plugin_tools.check_plugin_imports({"plugin_name": "sample_plugin"}, {})
            self.assertTrue(result["valid"])
            self.assertIn("qgis.PyQt.QtWidgets", result["qgis_imports"])
            self.assertTrue(result["relative_imports"])

    def test_package_plugin_zip_dry_run_excludes_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_plugin(root)
            with patch.object(plugin_tools, "_plugin_roots", return_value=[root]):
                result = plugin_tools.package_plugin_zip(
                    {"plugin_name": "sample_plugin", "output_path": str(root / "sample.zip")},
                    {"dry_run": True},
                )
            self.assertTrue(result["dry_run"])
            self.assertFalse(any("__pycache__" in item or item.endswith(".pyc") for item in result["manifest"]))

    def test_direct_update_of_running_bridge_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_plugin(root, "sigmai")
            with patch.object(plugin_tools, "_plugin_roots", return_value=[root]):
                with self.assertRaises(ValidationError) as raised:
                    plugin_tools.update_plugin_from_folder({"source_folder": str(source), "plugin_name": "sigmai"}, {"dry_run": True})
            self.assertEqual(raised.exception.code, "SELF_UPDATE_REQUIRES_SELF_MANAGEMENT")

    def test_repository_search_requires_explicit_network_confirmation(self):
        with self.assertRaises(ValidationError) as raised:
            plugin_tools.search_qgis_plugin_repository({"query": "QuickMapServices"}, {})
        self.assertEqual(raised.exception.code, "NETWORK_CONFIRMATION_REQUIRED")

    def test_repository_url_is_restricted_to_official_qgis_host(self):
        with self.assertRaises(ValidationError) as raised:
            plugin_tools.search_qgis_plugin_repository(
                {"query": "plugin", "repository_url": "https://example.com/plugins.xml", "confirm_network": True},
                {},
            )
        self.assertEqual(raised.exception.code, "PLUGIN_REPOSITORY_URL_BLOCKED")

    def test_plugin_zip_inspection_and_install_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_plugin(root, "repo_probe")
            zip_path = root / "repo_probe.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in source.rglob("*"):
                    archive.write(file_path, file_path.relative_to(root))

            inspection = plugin_tools.inspect_qgis_plugin_zip({"zip_path": str(zip_path)}, {})
            self.assertTrue(inspection["metadata_valid"])
            self.assertEqual(inspection["metadata"]["name"], "Sample Plugin")

            install = plugin_tools.install_plugin_from_zip(
                {"zip_path": str(zip_path), "plugin_name": "repo_probe"},
                {"dry_run": True},
            )
            self.assertTrue(install["dry_run"])
            self.assertTrue(install["plan"]["metadata_valid"])

    def test_generic_plugin_risk_classifier_detects_network_and_output(self):
        risk = plugin_tools._classify_algorithm_risk(
            "quickosm:downloadosmdataextentquery",
            [
                {"name": "SERVER", "description": "Overpass server"},
                {"name": "OUTPUT", "description": "Output layer"},
            ],
            [{"name": "OUTPUT", "description": "Downloaded OSM layer"}],
        )
        self.assertEqual(risk["risk_level"], "medium")
        self.assertIn("network_read", risk["risk_categories"])
        self.assertIn("creates_new_output", risk["risk_categories"])
        self.assertIn("confirm_network", risk["required_confirmations"])

    def test_generic_plugin_algorithm_plan_reports_missing_parameters(self):
        fake_manifest = {
            "id": "demo:algorithm",
            "found": True,
            "parameters": [
                {"name": "INPUT", "optional": False, "default_value": None},
                {"name": "OUTPUT", "optional": True, "default_value": "TEMPORARY_OUTPUT"},
            ],
            "outputs": [],
            "risk": {"risk_level": "low", "generic_execution": "safe_with_validated_outputs", "blockers": []},
        }
        with patch.object(plugin_tools, "_algorithm_manifest", return_value=fake_manifest):
            plan = plugin_tools.dry_run_plugin_algorithm_generic({"algorithm_id": "demo:algorithm", "parameters": {}}, {})
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["missing_required_parameters"], ["INPUT"])
        self.assertFalse(plan["can_attempt_generic_run"])


if __name__ == "__main__":
    unittest.main()
