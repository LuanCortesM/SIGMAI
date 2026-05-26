import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sigmai.bridge_server import BridgeLogger, SIGMAIServer  # noqa: E402


class BridgeServerDispatcherTests(unittest.TestCase):
    def test_status_uses_fast_path_when_qgis_queue_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = SIGMAIServer(token="token", log_dir=Path(tmp))
            server._timer = object()

            response = server._execute_or_enqueue({"action": "status", "request_id": "req-status"}, "127.0.0.1")

            self.assertTrue(response["ok"])
            self.assertEqual(response["action"], "status")
            self.assertEqual(response["request_id"], "req-status")
            self.assertEqual(response["data"]["bridge"], "online")
            self.assertIn("registered_command_count", response["data"])

    def test_capabilities_use_fast_path_when_qgis_queue_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = SIGMAIServer(token="token", log_dir=Path(tmp))
            server._timer = object()

            response = server._execute_or_enqueue({"action": "get_capabilities"}, "127.0.0.1")

            self.assertTrue(response["ok"])
            self.assertIn("groups", response["data"])
            self.assertIn("registered_actions", response["data"])

    def test_unknown_action_fails_before_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = SIGMAIServer(token="token", log_dir=Path(tmp))
            server._timer = object()

            response = server._execute_or_enqueue({"action": "not_existing_command"}, "127.0.0.1")

            self.assertFalse(response["ok"])
            self.assertEqual(response["errors"][0]["code"], "ACTION_NOT_ALLOWED")

    def test_confirmation_required_fails_before_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = SIGMAIServer(token="token", log_dir=Path(tmp))
            server._timer = object()

            response = server._execute_or_enqueue({"action": "disable_plugin", "params": {"plugin_name": "sigmai"}}, "127.0.0.1")

            self.assertFalse(response["ok"])
            self.assertEqual(response["errors"][0]["code"], "CONFIRMATION_REQUIRED")

    def test_logger_failure_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory_path = Path(tmp) / "as_directory"
            directory_path.mkdir()
            logger = BridgeLogger(directory_path)

            logger.record("test_event", payload={"x": 1})

            self.assertIn("Error", logger.last_error)

    def test_log_tail_handles_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "sigmai.jsonl"
            log_path.write_text("not-json\n" + json.dumps({"event": "ok"}) + "\n", encoding="utf-8")
            logger = BridgeLogger(log_path)

            records = logger.tail(2)

            self.assertEqual(records[0]["raw"], "not-json")
            self.assertEqual(records[1]["event"], "ok")

    def test_http_command_auth_and_bad_json_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = SIGMAIServer(token="good-token", port=0, log_dir=Path(tmp))
            server.start()
            port = server._httpd.server_address[1]
            try:
                missing_auth = urllib.request.Request(
                    f"http://127.0.0.1:{port}/command",
                    data=b'{"action":"status"}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as missing_auth_error:
                    urllib.request.urlopen(missing_auth, timeout=2)
                self.assertEqual(missing_auth_error.exception.code, 401)
                missing_auth_error.exception.close()

                bad_json = urllib.request.Request(
                    f"http://127.0.0.1:{port}/command",
                    data=b"{ bad json",
                    headers={"Content-Type": "application/json", "Authorization": "Bearer good-token"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as bad_json_error:
                    urllib.request.urlopen(bad_json, timeout=2)
                self.assertEqual(bad_json_error.exception.code, 400)
                bad_json_error.exception.close()
            finally:
                server.stop()

    def test_http_command_status_responds_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = SIGMAIServer(token="good-token", port=0, log_dir=Path(tmp))
            server.start()
            port = server._httpd.server_address[1]
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/command",
                    data=b'{"action":"status","request_id":"http-status"}',
                    headers={"Content-Type": "application/json", "Authorization": "Bearer good-token"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["request_id"], "http-status")
                self.assertEqual(payload["data"]["bridge"], "online")
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
