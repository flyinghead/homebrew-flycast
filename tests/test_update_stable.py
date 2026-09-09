import hashlib
import io
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import update_channels as updater


def release_fixture(version="2.10", bundle_version=None, bundle_id="com.flyinghead.Flycast"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("Flycast.app/Contents/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": bundle_id,
            "CFBundleShortVersionString": bundle_version or f"v{version}",
        }))
        archive.writestr("Flycast.app/Contents/MacOS/Flycast", b"test executable")
    payload = output.getvalue()
    name = f"flycast-macOS-{version}.zip"
    metadata = {
        "tag_name": f"v{version}", "draft": False, "prerelease": False,
        "assets": [{
            "name": name, "state": "uploaded", "size": len(payload),
            "browser_download_url": f"https://github.com/flyinghead/flycast/releases/download/v{version}/{name}",
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }],
    }

    def fetch(url):
        if url == updater.LATEST_RELEASE:
            return json.dumps(metadata).encode()
        if url == metadata["assets"][0]["browser_download_url"]:
            return payload
        raise AssertionError(f"Unexpected URL: {url}")

    return metadata, payload, fetch


STABLE = ('cask "flycast" do\n  version "2.7"\n  sha256 "' + "a" * 64
          + '"\n  depends_on :macos\n  app "Flycast.app"\nend\n')


class StableUpdaterTests(unittest.TestCase):
    def test_new_release_updates_only_version_and_checksum_and_is_idempotent(self):
        _, payload, fetch = release_fixture()
        expected = STABLE.replace('version "2.7"', 'version "2.10"').replace(
            "a" * 64, hashlib.sha256(payload).hexdigest())
        self.assertEqual(updater.update_stable_source(STABLE, fetch), expected)
        self.assertEqual(updater.update_stable_source(expected, fetch), expected)

    def test_draft_prerelease_and_unsupported_tags_are_rejected(self):
        for field, value in (("draft", True), ("prerelease", True), ("tag_name", "v2.10-rc1")):
            with self.subTest(field=field):
                metadata, _, fetch = release_fixture()
                metadata[field] = value
                with self.assertRaises(ValueError):
                    updater.update_stable_source(STABLE, fetch)

    def test_older_release_is_rejected(self):
        _, _, fetch = release_fixture("2.6")
        with self.assertRaisesRegex(ValueError, "older release"):
            updater.update_stable_source(STABLE, fetch)

    def test_missing_or_unfinished_macos_asset_is_rejected(self):
        for assets in ([], [{"name": "flycast-macOS-2.10.zip", "state": "new"}]):
            with self.subTest(assets=assets):
                metadata, _, fetch = release_fixture()
                metadata["assets"] = assets
                with self.assertRaisesRegex(ValueError, "uploaded macOS"):
                    updater.update_stable_source(STABLE, fetch)

    def test_archive_url_size_and_digest_are_checked(self):
        for field, value, error in (
            ("browser_download_url", "https://example.com/app.zip", "URL"),
            ("size", 1, "size mismatch"),
            ("digest", "sha256:" + "0" * 64, "digest mismatch"),
        ):
            with self.subTest(field=field):
                metadata, _, fetch = release_fixture()
                metadata["assets"][0][field] = value
                with self.assertRaisesRegex(ValueError, error):
                    updater.update_stable_source(STABLE, fetch)

    def test_bundle_identity_and_version_are_checked(self):
        for options, error in (({"bundle_id": "org.example.OtherApp"}, "identifier"),
                               ({"bundle_version": "v2.9"}, "version mismatch")):
            with self.subTest(options=options):
                _, _, fetch = release_fixture(**options)
                with self.assertRaisesRegex(ValueError, error):
                    updater.update_stable_source(STABLE, fetch)

    def test_changed_archive_for_same_version_is_rejected(self):
        _, _, fetch = release_fixture("2.7")
        with self.assertRaisesRegex(ValueError, "changed without a version change"):
            updater.update_stable_source(STABLE, fetch)

    def test_combined_updates_include_stable_and_write_nothing_on_failure(self):
        _, _, fetch = release_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "Casks/flycast.rb"
            path.parent.mkdir()
            path.write_text(STABLE)
            development = {root / f"Casks/flycast@{channel}.rb": channel
                           for channel in updater.CHANNELS}
            with patch.object(updater, "prepare_development_updates", return_value=development.copy()) as prepare:
                updates = updater.prepare_updates(root, fetch)
                self.assertEqual(set(updates), {path, *development})
                self.assertIn('version "2.10"', updates[path])
                prepare.assert_called_once_with(root, fetch, updates[path])
            with patch.object(updater, "prepare_development_updates", side_effect=OSError("download failed")):
                with self.assertRaisesRegex(OSError, "download failed"):
                    updater.prepare_updates(root, fetch)
            self.assertEqual(path.read_text(), STABLE)
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
