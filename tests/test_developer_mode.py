from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.qgis_actions.dev_tools import execute_qgis_python  # noqa: E402
from sigmai.validators import ValidationError, validate_command  # noqa: E402


class DeveloperModeTests(unittest.TestCase):
    def test_dev_python_requires_unsafe_mode_in_validator(self):
        with self.assertRaises(ValidationError) as cm:
            validate_command({"action": "dev_execute_qgis_python", "params": {"code": "print(1)"}})
        self.assertEqual(cm.exception.code, "DEV_MODE_REQUIRED")

    def test_dev_python_accepts_dry_run_when_mode_enabled(self):
        command = validate_command(
            {"action": "dev_execute_qgis_python", "dry_run": True, "params": {"code": "print(1)"}},
            unsafe_developer_mode=True,
        )
        self.assertEqual(command["action"], "dev_execute_qgis_python")

    def test_dev_python_requires_sim_confirmation_for_real_run(self):
        with self.assertRaises(ValidationError) as cm:
            validate_command(
                {"action": "dev_execute_qgis_python", "params": {"code": "print(1)"}},
                unsafe_developer_mode=True,
            )
        self.assertEqual(cm.exception.code, "CONFIRMATION_REQUIRED")

    def test_dev_python_confirmation_sim_allows_validator(self):
        command = validate_command(
            {"action": "dev_execute_qgis_python", "params": {"code": "print(1)", "confirm_dev_python": "SIM"}},
            unsafe_developer_mode=True,
        )
        self.assertEqual(command["params"]["confirm_dev_python"], "SIM")

    def test_dev_tool_blocks_os_shell_markers_even_in_dev(self):
        with self.assertRaises(ValidationError) as cm:
            execute_qgis_python(
                {"code": "import subprocess\nresult = 1", "confirm_dev_python": "SIM"},
                {"unsafe_developer_mode": True},
            )
        self.assertEqual(cm.exception.code, "DEV_TOKEN_BLOCKED")

    def test_dev_tool_dry_run_preview(self):
        result = execute_qgis_python(
            {"code": "result = 42"},
            {"unsafe_developer_mode": True, "dry_run": True},
        )
        self.assertTrue(result["dry_run"])
        self.assertIn("result = 42", result["code_preview"])


if __name__ == "__main__":
    unittest.main()
