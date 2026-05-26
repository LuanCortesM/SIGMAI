import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "codex_plugin" / "client"))

from sigmai_client import payload_for_args  # noqa: E402


class Args:
    def __init__(self, command_name, **kwargs):
        self.command_name = command_name
        self.__dict__.update(kwargs)


class ClientPayloadTests(unittest.TestCase):
    def test_status_payload(self):
        self.assertEqual(payload_for_args(Args("status")), {"action": "status"})

    def test_capabilities_payload(self):
        self.assertEqual(payload_for_args(Args("capabilities")), {"action": "get_capabilities"})

    def test_inspect_plugin_payload(self):
        payload = payload_for_args(Args("inspect-plugin", plugin_name="TopoTrail"))
        self.assertEqual(payload["action"], "inspect_plugin")
        self.assertEqual(payload["params"]["plugin_name"], "TopoTrail")

    def test_layer_info_payload(self):
        payload = payload_for_args(Args("layer-info", layer_id="abc"))
        self.assertEqual(payload["action"], "get_layer_info")
        self.assertEqual(payload["params"]["layer_id"], "abc")

    def test_raw_command_payload(self):
        payload = payload_for_args(Args("command", json='{"action":"status"}'))
        self.assertEqual(payload["action"], "status")


if __name__ == "__main__":
    unittest.main()
