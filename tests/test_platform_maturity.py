from __future__ import annotations

import unittest

from qgis_plugin.permissions import COMMAND_PERMISSIONS
from qgis_plugin.qgis_actions.platform import evaluate_sigmai_maturity


class PlatformMaturityTests(unittest.TestCase):
    def test_permission_registered(self):
        self.assertIn("evaluate_sigmai_maturity", COMMAND_PERMISSIONS)
        self.assertEqual(COMMAND_PERMISSIONS["evaluate_sigmai_maturity"].permission_level, "read_only")

    def test_evaluate_maturity_shape(self):
        context = {"registered_actions": sorted(COMMAND_PERMISSIONS)}
        result = evaluate_sigmai_maturity({}, context)
        self.assertIn("highest_validated_level", result)
        self.assertIn("levels", result)
        self.assertIn("rules", result)
        self.assertGreaterEqual(result["highest_claimed_level"], 14)


if __name__ == "__main__":
    unittest.main()
