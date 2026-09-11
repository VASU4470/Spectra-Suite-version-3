"""Pure version and release-response tests for the update checker."""

from __future__ import annotations

import unittest

from update_logic import is_newer_release, release_summary, version_tuple


class UpdateTests(unittest.TestCase):
    def test_semantic_versions_compare_numerically(self):
        self.assertEqual(version_tuple("v3.1"), (3, 1, 0))
        self.assertTrue(is_newer_release("v3.1.1", "3.1.0"))
        self.assertTrue(is_newer_release("v3.2.0", "3.1.9"))
        self.assertFalse(is_newer_release("v3.1.0", "3.1.0"))
        self.assertFalse(is_newer_release("v3.0.12", "3.1.0"))

    def test_release_payload_is_normalized(self):
        release = release_summary({
            "tag_name": "v3.1.1", "name": "Version 3.1.1",
            "body": "Fixes", "html_url": "https://example.test/release",
        })
        self.assertEqual(release["tag"], "v3.1.1")
        self.assertEqual(release["notes"], "Fixes")


if __name__ == "__main__":
    unittest.main()
