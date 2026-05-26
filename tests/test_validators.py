import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.validators import ValidationError, validate_command  # noqa: E402


class ValidatorTests(unittest.TestCase):
    def test_accepts_known_action(self):
        command = validate_command({"action": "status"})
        self.assertEqual(command["action"], "status")
        self.assertEqual(command["params"], {})
        self.assertEqual(command["schema_version"], "0.2")
        self.assertFalse(command["dry_run"])

    def test_accepts_request_id(self):
        command = validate_command({"action": "get_capabilities", "request_id": "abc"})
        self.assertEqual(command["request_id"], "abc")

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValidationError) as raised:
            validate_command({"action": "do_anything"})
        self.assertEqual(raised.exception.code, "ACTION_NOT_ALLOWED")

    def test_rejects_dangerous_token(self):
        with self.assertRaises(ValidationError) as raised:
            validate_command({"action": "status", "params": {"code": "print(1)"}})
        self.assertEqual(raised.exception.code, "DANGEROUS_COMMAND")

    def test_allows_safe_action_name_containing_eval(self):
        command = validate_command(
            {
                "action": "evaluate_layout_cartographic_completeness",
                "request_id": "fulltest-evaluate_layout_cartographic_completeness-123",
                "params": {"layout_name": "Layout", "output_path": r"D:\QGISProfile\python\plugins\sigmai\test_outputs\map.png"},
            }
        )
        self.assertEqual(command["action"], "evaluate_layout_cartographic_completeness")

    def test_allows_local_python_plugin_paths_in_path_parameters(self):
        command = validate_command(
            {
                "action": "generate_basic_map",
                "dry_run": True,
                "params": {
                    "layer_id": "layer",
                    "output_path": r"D:\QGISProfile\python\plugins\sigmai\test_outputs\map.pdf",
                    "logo_path": r"D:\QGISProfile\python\plugins\sigmai\icons\sigmai_logo_full.png",
                },
            }
        )
        self.assertEqual(command["action"], "generate_basic_map")

    def test_allows_processing_input_output_paths(self):
        command = validate_command(
            {
                "action": "run_processing",
                "dry_run": True,
                "params": {
                    "algorithm": "topotrail:topotrail",
                    "parameters": {
                        "INPUT_DEM": r"D:\SIGMAI_TEST_DATA\22S465ZN.tif",
                        "INPUT_SLOPE": r"D:\SIGMAI_TEST_DATA\22S465SN.tif",
                        "OUTPUT_FILE": r"D:\SIGMAI_OUTPUTS\topotrail.gpkg",
                    },
                    "confirm_overwrite": True,
                },
            }
        )
        self.assertEqual(command["action"], "run_processing")

    def test_rejects_invalid_dry_run(self):
        with self.assertRaises(ValidationError) as raised:
            validate_command({"action": "status", "dry_run": "yes"})
        self.assertEqual(raised.exception.code, "BAD_REQUEST")

    def test_rejects_unsupported_dry_run(self):
        with self.assertRaises(ValidationError) as raised:
            validate_command({"action": "check_plugin_menu_actions", "dry_run": True})
        self.assertEqual(raised.exception.code, "DRY_RUN_NOT_SUPPORTED")

    def test_read_only_dry_run_is_a_safe_noop(self):
        command = validate_command({"action": "status", "dry_run": True})
        self.assertTrue(command["dry_run"])


if __name__ == "__main__":
    unittest.main()
