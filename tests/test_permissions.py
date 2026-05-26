import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qgis_plugin.permissions import PLUGIN_WRITE, READ_ONLY, allowed_actions, capabilities_payload, permission_for  # noqa: E402
from qgis_plugin.validators import ValidationError, validate_command  # noqa: E402


class PermissionTests(unittest.TestCase):
    def test_capabilities_include_new_commands(self):
        payload = capabilities_payload()
        self.assertIn("system", payload["groups"])
        self.assertIn("get_capabilities", payload["groups"]["system"])
        self.assertIn("plugin_management", payload["groups"])
        self.assertIn("inspect_plugin", payload["groups"]["plugin_management"])
        self.assertIn("self_management", payload["groups"])
        self.assertEqual(payload["display_name"], "SIGMAI")
        self.assertIn("diagnose_crs", payload["groups"]["crs_quality"])
        self.assertIn("buffer", payload["groups"]["vector_tools"])

    def test_permission_lookup(self):
        permission = permission_for("inspect_plugin")
        self.assertIsNotNone(permission)
        self.assertEqual(permission.permission_level, READ_ONLY)

    def test_plugin_write_requires_confirmation(self):
        permission = permission_for("update_plugin_from_folder")
        self.assertIsNotNone(permission)
        self.assertEqual(permission.permission_level, PLUGIN_WRITE)
        with self.assertRaises(ValidationError):
            validate_command({"action": "update_plugin_from_folder", "params": {"source_folder": "C:/tmp/example"}})
        normalized = validate_command({"action": "update_plugin_from_folder", "dry_run": True, "params": {"source_folder": "C:/tmp/example"}})
        self.assertTrue(normalized["dry_run"])

    def test_symbology_actions_are_allowed_after_implementation(self):
        self.assertIn("apply_single_symbol", allowed_actions())
        payload = capabilities_payload()
        self.assertIn("symbology", payload["groups"])
        self.assertIn("apply_single_symbol", payload["groups"]["symbology"])

    def test_raster_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("raster", payload["groups"])
        self.assertIn("raster_info", payload["groups"]["raster"])
        self.assertIn("raster_hillshade", payload["groups"]["raster"])
        self.assertIn("raster_hillshade", payload["dry_run_supported"])
        self.assertIn("raster_hillshade", payload["raster_capabilities"])

    def test_workflow_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("workflows", payload["groups"])
        self.assertIn("plan_workflow", payload["groups"]["workflows"])
        self.assertIn("execute_workflow", payload["dry_run_supported"])
        self.assertIn("generate_workflow_report", payload["workflow_capabilities"])

    def test_user_profile_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("user_profile", payload["groups"])
        self.assertIn("get_user_profile", payload["groups"]["user_profile"])
        self.assertIn("set_user_profile", payload["dry_run_supported"])

    def test_job_queue_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("job_queue", payload["groups"])
        self.assertIn("start_job", payload["groups"]["job_queue"])
        self.assertIn("get_job_status", payload["groups"]["job_queue"])
        self.assertIn("run_workflow_job", payload["dry_run_supported"])
        self.assertIn("start_job", payload["job_queue_capabilities"])

    def test_execute_workflow_action_name_is_not_blocked_by_exec_token(self):
        normalized = validate_command({"action": "execute_workflow", "dry_run": True, "params": {"steps": [{"action": "status"}]}})
        self.assertEqual(normalized["action"], "execute_workflow")

    def test_exec_token_still_blocked_in_free_text(self):
        with self.assertRaises(ValidationError):
            validate_command({"action": "status", "params": {"note": "please exec this"}})

    def test_atlas_report_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("atlas_reports", payload["groups"])
        self.assertIn("create_atlas", payload["groups"]["atlas_reports"])
        self.assertIn("export_report_html", payload["groups"]["atlas_reports"])
        self.assertIn("create_atlas", payload["dry_run_supported"])
        self.assertIn("create_atlas", payload["atlas_report_capabilities"])

    def test_data_source_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("data_sources", payload["groups"])
        self.assertIn("inspect_data_source", payload["groups"]["data_sources"])
        self.assertIn("gps_gpx", payload["groups"])
        self.assertIn("load_gpx", payload["groups"]["gps_gpx"])
        self.assertIn("databases", payload["groups"])
        self.assertIn("load_gpx", payload["dry_run_supported"])
        self.assertIn("inspect_data_source", payload["data_source_capabilities"])

    def test_layer_hygiene_actions_are_capability_wrapped(self):
        payload = capabilities_payload()
        self.assertIn("layer_tree", payload["groups"])
        for action in (
            "list_duplicate_layers",
            "remove_layer",
            "remove_layers_by_name",
            "remove_layers_by_source_path",
            "clear_sigmai_temporary_layers",
            "deduplicate_layers",
            "create_clean_test_project",
        ):
            self.assertIn(action, payload["groups"]["layer_tree"])
        self.assertIn("deduplicate_layers", payload["dry_run_supported"])
        self.assertIn("create_clean_test_project", payload["requires_confirmation"])

    def test_read_only_commands_accept_dry_run_for_safe_audits(self):
        for action in ("status", "list_ogc_connections", "validate_service_url", "list_gpx_layers"):
            params = {"url": "https://example.com/wms"} if action == "validate_service_url" else {}
            normalized = validate_command({"action": action, "dry_run": True, "params": params})
            self.assertTrue(normalized["dry_run"])


if __name__ == "__main__":
    unittest.main()
