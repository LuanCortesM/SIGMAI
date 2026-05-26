import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qgis_plugin.command_registry import CommandRegistry  # noqa: E402


def sample_handler(params, context):
    return {"params": params, "dry_run": context.get("dry_run")}


class CommandRegistryTests(unittest.TestCase):
    def test_response_envelope_has_protocol_metadata(self):
        registry = CommandRegistry({"qgis_version": "test"})
        registry.register("get_capabilities", sample_handler)
        response = registry.execute({"action": "get_capabilities", "request_id": "req-1"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["schema_version"], "0.2")
        self.assertEqual(response["request_id"], "req-1")
        self.assertEqual(response["meta"]["permission_level"], "read_only")

    def test_unknown_action_returns_structured_error(self):
        registry = CommandRegistry({})
        response = registry.execute({"action": "unknown"})
        self.assertFalse(response["ok"])
        self.assertEqual(response["errors"][0]["code"], "ACTION_NOT_ALLOWED")


if __name__ == "__main__":
    unittest.main()
