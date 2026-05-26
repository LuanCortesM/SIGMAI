import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProtocolFileTests(unittest.TestCase):
    def test_core_schemas_are_valid_json(self):
        for path in (ROOT / "core" / "schemas").rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))

    def test_examples_are_valid_json(self):
        for path in (ROOT / "core" / "examples").glob("*.json"):
            with self.subTest(path=path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("action", payload)

    def test_command_schema_mentions_capabilities(self):
        schema = json.loads((ROOT / "core" / "schemas" / "command.schema.json").read_text(encoding="utf-8"))
        actions = schema["properties"]["action"]["enum"]
        self.assertIn("get_capabilities", actions)
        self.assertIn("inspect_plugin", actions)


if __name__ == "__main__":
    unittest.main()
