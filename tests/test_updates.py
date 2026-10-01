"""Pure version and release-response tests for the update checker."""

from __future__ import annotations

import unittest
from urllib.parse import urlparse

from app_version import PRIVACY_POLICY_URL, UPDATE_SIGNUP_URL
from update_logic import (
    checksum_from_manifest,
    is_newer_release,
    release_summary,
    select_update_assets,
    sha256_file,
    version_tuple,
)
from qt_update_installer import _BackupWorker, _preserve_platform_download_warning


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

    def test_release_summary_preserves_download_asset_metadata(self):
        release = release_summary({
            "tag_name": "v3.4.1",
            "assets": [{"name": "package.dmg", "browser_download_url": "https://github.com/a/b", "size": 42}],
        })
        self.assertEqual(release["assets"][0]["name"], "package.dmg")
        self.assertEqual(release["assets"][0]["size"], 42)

    def test_select_update_assets_matches_platform_and_checksum_manifest(self):
        release = {
            "tag": "v3.4.1",
            "assets": [
                {"name": "SpectraSuite-3.4.1-windows-x64-unsigned-setup.exe", "url": "https://github.com/a/b"},
                {"name": "SHA256SUMS-windows-amd64.txt", "url": "https://github.com/a/c"},
                {"name": "SpectraSuite-3.4.1-macos-arm64-unsigned-update.pkg", "url": "https://github.com/a/d"},
                {"name": "SHA256SUMS-darwin-arm64.txt", "url": "https://github.com/a/e"},
            ],
        }
        selected = select_update_assets(release, system="Windows", machine="AMD64")
        self.assertEqual(selected[0]["name"], "SpectraSuite-3.4.1-windows-x64-unsigned-setup.exe")
        selected = select_update_assets(release, system="Darwin", machine="arm64")
        self.assertEqual(selected[0]["name"], "SpectraSuite-3.4.1-macos-arm64-unsigned-update.pkg")
        self.assertIsNone(select_update_assets(release, system="Darwin", machine="ppc"))

    def test_checksum_manifest_requires_one_exact_filename_and_sha256(self):
        digest = "a" * 64
        self.assertEqual(
            checksum_from_manifest(f"{digest}  installer.exe\n", "installer.exe"),
            digest,
        )
        with self.assertRaises(ValueError):
            checksum_from_manifest(f"{digest}  ../installer.exe\n", "installer.exe")
        with self.assertRaises(ValueError):
            checksum_from_manifest(f"{digest}  installer.exe\n{digest}  installer.exe\n", "installer.exe")

    def test_sha256_file_reads_binary_file(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as folder:
            path = Path(folder) / "payload.bin"
            path.write_bytes(b"SpectraSuite update")
            self.assertEqual(sha256_file(path), "432f53ab077203cc24ae58023e509c5d5d622e3476920687590a725cbc6c26ed")

    def test_previous_install_backup_copies_application_files(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "installed"
            source.mkdir()
            (source / "SpectraSuite.exe").write_bytes(b"previous build")
            destination = root / "backup" / "SpectraSuite"
            copied = []
            errors = []
            worker = _BackupWorker(source, destination)
            worker.completed.connect(copied.append)
            worker.failed.connect(errors.append)
            worker.run()
            self.assertEqual(errors, [])
            self.assertEqual(copied, [str(destination)])
            self.assertEqual((destination / "SpectraSuite.exe").read_bytes(), b"previous build")

    def test_macos_download_must_keep_quarantine_for_gatekeeper(self):
        from unittest.mock import patch

        with patch("qt_update_installer.sys.platform", "darwin"), patch(
            "qt_update_installer.os.getxattr", side_effect=OSError("attribute missing")
        ):
            self.assertFalse(_preserve_platform_download_warning("update.pkg"))
        with patch("qt_update_installer.sys.platform", "darwin"), patch(
            "qt_update_installer.os.getxattr", return_value=b"quarantine metadata"
        ):
            self.assertTrue(_preserve_platform_download_warning("update.pkg"))

    def test_existing_mac_disk_image_release_has_no_update_package(self):
        release = {
            "tag": "v3.4.0-rc.1",
            "assets": [
                {"name": "SpectraSuite-3.4.0-macos-arm64-unsigned.dmg", "url": "https://github.com/a/d"},
                {"name": "SHA256SUMS-darwin-arm64.txt", "url": "https://github.com/a/e"},
            ],
        }
        self.assertIsNone(select_update_assets(release, system="Darwin", machine="arm64"))

    def test_optional_email_signup_uses_secure_brevo_form(self):
        parsed = urlparse(UPDATE_SIGNUP_URL)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.hostname, "3bf8234d.sibforms.com")
        self.assertTrue(parsed.path.startswith("/serve/"))
        self.assertFalse(parsed.username)
        self.assertFalse(parsed.password)

        privacy = urlparse(PRIVACY_POLICY_URL)
        self.assertEqual(privacy.scheme, "https")
        self.assertEqual(privacy.hostname, "github.com")
        self.assertTrue(privacy.path.endswith("/PRIVACY.md"))


if __name__ == "__main__":
    unittest.main()
