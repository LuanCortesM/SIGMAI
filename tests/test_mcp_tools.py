from __future__ import annotations

import unittest

from mcp_server import tools


class McpToolsTests(unittest.TestCase):
    def test_manifest_does_not_expose_token(self):
        manifest = tools.sigmai_tool_manifest({})
        self.assertTrue(manifest["ok"])
        text = str(manifest)
        self.assertNotIn("Bearer ", text)
        self.assertIn("token_exposed_to_model", manifest["security"])

    def test_dangerous_actions_blocked_by_mcp_proxy(self):
        result = tools.sigmai_command({"action": "self_apply_update", "params": {}, "dry_run": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "MCP_BLOCKED_ACTION")

    def test_unknown_action_not_allowlisted(self):
        result = tools.sigmai_command({"action": "not_a_real_action", "params": {}, "dry_run": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "MCP_ACTION_NOT_ALLOWLISTED")

    def test_core_tools_registered(self):
        for name in [
            "sigmai_tool_manifest",
            "sigmai_health",
            "sigmai_status",
            "sigmai_get_capabilities",
            "sigmai_list_layers",
            "sigmai_generate_professional_map_dry_run",
            "sigmai_plugin_inventory",
            "sigmai_processing_providers",
        ]:
            self.assertIn(name, tools.TOOLS)


if __name__ == "__main__":
    unittest.main()
