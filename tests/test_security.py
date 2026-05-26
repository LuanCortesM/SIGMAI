import unittest

from qgis_plugin.security import is_localhost, validate_bearer_header


class SecurityTests(unittest.TestCase):
    def test_localhost_only(self):
        self.assertTrue(is_localhost("127.0.0.1"))
        self.assertTrue(is_localhost("::1"))
        self.assertFalse(is_localhost("192.168.0.10"))

    def test_bearer_header(self):
        self.assertTrue(validate_bearer_header("Bearer abc", "abc"))
        self.assertFalse(validate_bearer_header("Bearer abc", "def"))
        self.assertFalse(validate_bearer_header(None, "abc"))


if __name__ == "__main__":
    unittest.main()
