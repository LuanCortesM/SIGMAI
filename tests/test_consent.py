"""Controle de consentimento: o que a IA pode fazer, e o que nunca pode."""

import unittest

from sigmai.consent import (
    DECISION_ALLOWED,
    DECISION_DENIED,
    MODE_ALLOW_SESSION,
    MODE_ASK,
    MODE_READ_ONLY,
    NEVER_AUTO_APPROVED,
    ConsentManager,
    ConsentRequest,
)


def request(action="compose_map", group="cartography", **params):
    payload = {"output_path": "/tmp/mapa.png", "title": "Mapa"}
    payload.update(params)
    return ConsentRequest(action, group, "safe_write", payload, "127.0.0.1")


class ModeTests(unittest.TestCase):
    def test_read_only_denies_and_says_how_to_unblock(self):
        manager = ConsentManager()
        decision = manager.evaluate(request())
        self.assertFalse(decision.allowed)
        self.assertIn("dry_run", decision.reason)
        self.assertIn("painel", decision.reason.lower())

    def test_allow_session_permits(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        self.assertTrue(manager.evaluate(request()).allowed)

    def test_ask_uses_the_prompt(self):
        manager = ConsentManager(mode=MODE_ASK)
        seen = []
        manager.set_prompt(lambda req: (seen.append(req.action), (DECISION_ALLOWED, False))[1])
        self.assertTrue(manager.evaluate(request()).allowed)
        self.assertEqual(seen, ["compose_map"])

    def test_ask_without_a_prompt_denies_instead_of_hanging(self):
        manager = ConsentManager(mode=MODE_ASK)
        decision = manager.evaluate(request())
        self.assertFalse(decision.allowed)

    def test_remembering_a_category_skips_later_prompts(self):
        manager = ConsentManager(mode=MODE_ASK)
        manager.set_prompt(lambda req: (DECISION_ALLOWED, True))
        self.assertTrue(manager.evaluate(request()).allowed)
        manager.set_prompt(None)
        self.assertTrue(manager.evaluate(request(action="export_layout")).allowed)

    def test_a_remembered_denial_stops_the_agent_retrying(self):
        manager = ConsentManager(mode=MODE_ASK)
        manager.set_prompt(lambda req: (DECISION_DENIED, True))
        manager.evaluate(request())
        manager.set_prompt(None)
        decision = manager.evaluate(request())
        self.assertFalse(decision.allowed)
        self.assertIn("negou", decision.reason)


class GuardrailTests(unittest.TestCase):
    def test_plugin_and_python_actions_are_never_auto_approved(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        for action in sorted(NEVER_AUTO_APPROVED):
            with self.subTest(action=action):
                decision = manager.evaluate(ConsentRequest(action, "plugin_management", "plugin_write", {}, "127.0.0.1"))
                self.assertFalse(decision.allowed)

    def test_output_sandbox(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        manager.set_output_roots(["/home/usuario/mapas"])
        self.assertFalse(manager.evaluate(request(output_path="/tmp/fora.png")).allowed)
        self.assertTrue(manager.evaluate(request(output_path="/home/usuario/mapas/ok.png")).allowed)

    def test_sandbox_resists_traversal(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        manager.set_output_roots(["/home/usuario/mapas"])
        self.assertFalse(manager.evaluate(request(output_path="/home/usuario/mapas/../../etc/passwd")).allowed)

    def test_session_limits_apply_per_category(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        manager.set_limit("exports_per_session", 2)
        self.assertTrue(manager.evaluate(request()).allowed)
        self.assertTrue(manager.evaluate(request()).allowed)
        self.assertFalse(manager.evaluate(request()).allowed)
        # O teto de exportações não pode bloquear outra categoria.
        self.assertTrue(manager.evaluate(request(action="set_layer_visibility", group="layer_tree")).allowed)

    def test_reset_clears_counters_and_approvals(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        manager.set_limit("exports_per_session", 1)
        manager.evaluate(request())
        self.assertFalse(manager.evaluate(request()).allowed)
        manager.reset_session()
        self.assertTrue(manager.evaluate(request()).allowed)


class AuditTests(unittest.TestCase):
    def test_every_decision_is_recorded(self):
        manager = ConsentManager()
        manager.evaluate(request())
        events = [entry["event"] for entry in manager.recent_audit(10)]
        self.assertIn("denied_read_only", events)

    def test_audit_never_carries_a_token(self):
        manager = ConsentManager(mode=MODE_ALLOW_SESSION)
        manager.evaluate(request(token="segredo-que-nao-pode-vazar"))
        blob = repr(manager.recent_audit(10))
        self.assertNotIn("segredo-que-nao-pode-vazar", blob)

    def test_request_summary_lists_the_files_it_would_write(self):
        self.assertIn("/tmp/mapa.png", request().output_paths())
        self.assertIn("/tmp/mapa.png", request().summary())


if __name__ == "__main__":
    unittest.main()
