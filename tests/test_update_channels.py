from datetime import datetime, timezone
import io
from pathlib import Path
import plistlib
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET
import zipfile

from scripts import update_channels as updater


def listing(entries, token=None):
    root = ET.Element("ListBucketResult", xmlns=updater.NS["s"])
    ET.SubElement(root, "IsTruncated").text = "true" if token else "false"
    if token:
        ET.SubElement(root, "NextContinuationToken").text = token
    for key, modified, size in entries:
        entry = ET.SubElement(root, "Contents")
        for name, value in (("Key", key), ("LastModified", modified), ("Size", size)):
            ET.SubElement(entry, name).text = str(value)
    return ET.tostring(root)


def archive(commit, bundle_id="com.flyinghead.Flycast"):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as output:
        output.writestr("Flycast.app/Contents/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": bundle_id, "CFBundleVersion": commit[:9],
        }))
        output.writestr("Flycast.app/Contents/MacOS/Flycast", b"test executable")
    return data.getvalue()


def build(channel, commit, size):
    return updater.Build(channel, commit,
                         f"osx/heads/{channel}-{commit}/flycast.app.zip",
                         datetime(2026, 9, 9, tzinfo=timezone.utc), size)


class ChannelUpdaterTests(unittest.TestCase):
    def test_pagination_selects_newest_upload_not_lexically_largest_commit(self):
        older = f"osx/heads/master-{'f' * 40}/flycast.app.zip"
        newer = f"osx/heads/master-{'a' * 40}/flycast.app.zip"
        dev = f"osx/heads/dev-{'b' * 40}/flycast.app.zip"
        pages = [listing([(older, "2026-09-07T00:00:00Z", 10)], "next+/="),
                 listing([(newer, "2026-09-09T00:00:00Z", 10),
                          (dev, "2026-09-08T00:00:00Z", 10),
                          (newer + ".partial", "2026-09-10T00:00:00Z", 10),
                          (f"osx/heads/master-{'c' * 40}/flycast.app.zip",
                           "2026-09-10T00:00:00Z", 0)])]
        requests = []

        def fetch(url):
            requests.append(url)
            return pages[len(requests) - 1]

        latest = updater.latest_builds(updater.list_builds(fetch))
        self.assertEqual(latest["master"].key, newer)
        self.assertEqual(latest["dev"].key, dev)
        self.assertEqual(parse_qs(urlparse(requests[1]).query)["continuation-token"], ["next+/="])

    def test_repeated_pagination_token_fails(self):
        with self.assertRaisesRegex(ValueError, "pagination"):
            updater.list_builds(lambda _: listing([], "same-token"))

    def test_missing_channel_fails(self):
        with self.assertRaisesRegex(ValueError, "dev"):
            updater.latest_builds([build("master", "a" * 40, 10)])

    def test_archive_identity_commit_and_size_are_checked(self):
        commit = "a" * 40
        payload = archive(commit)
        candidate = build("master", commit, len(payload))
        self.assertEqual(len(updater.archive_sha(candidate, payload)), 64)
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            updater.archive_sha(candidate, payload[:-1])
        wrong_commit = archive("b" * 40)
        with self.assertRaisesRegex(ValueError, "commit mismatch"):
            updater.archive_sha(build("master", commit, len(wrong_commit)), wrong_commit)
        wrong_id = archive(commit, "org.example.OtherApp")
        with self.assertRaisesRegex(ValueError, "identifier"):
            updater.archive_sha(build("master", commit, len(wrong_id)), wrong_id)

    def test_failed_second_download_leaves_both_casks_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Casks").mkdir()
            (root / "Casks/flycast.rb").write_text('cask "flycast" do\n  depends_on :macos\nend\n')
            for channel in updater.CHANNELS:
                (root / f"Casks/flycast@{channel}.rb").write_text("unchanged\n")
            master = archive("a" * 40)
            dev = archive("b" * 40)
            entries = [(build("master", "a" * 40, len(master)).key, "2026-09-09T00:00:00Z", len(master)),
                       (build("dev", "b" * 40, len(dev)).key, "2026-09-09T00:00:00Z", len(dev))]

            def fetch(url):
                if "?" in url:
                    return listing(entries)
                if "/master-" in url:
                    return master
                raise OSError("download failed")

            with self.assertRaisesRegex(OSError, "download failed"):
                updater.prepare_development_updates(root, fetch)
            for channel in updater.CHANNELS:
                self.assertEqual((root / f"Casks/flycast@{channel}.rb").read_text(), "unchanged\n")

    def test_updater_rejects_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Casks").mkdir()
            (root / "Casks/flycast.rb").write_text('  depends_on :macos\n')
            (root / "Casks/flycast@master.rb").write_text('  version "2026.09.10.000000,old"\n')
            entries = [(build(channel, "a" * 40, 10).key, "2026-09-09T00:00:00Z", 10)
                       for channel in updater.CHANNELS]
            with self.assertRaisesRegex(ValueError, "older build"):
                updater.prepare_development_updates(root, lambda _: listing(entries))

    def test_generated_casks_are_idempotent_and_reject_changed_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Casks").mkdir()
            stable = 'cask "flycast" do\n  depends_on :macos\n  app "Flycast.app"\nend\n'
            (root / "Casks/flycast.rb").write_text(stable)
            payloads = {channel: archive(commit * 40)
                        for channel, commit in (("master", "a"), ("dev", "b"))}
            builds = [build(channel, commit * 40, len(payloads[channel]))
                      for channel, commit in (("master", "a"), ("dev", "b"))]
            entries = [(candidate.key, "2026-09-09T00:00:00Z", candidate.size)
                       for candidate in builds]

            def fetch(url):
                if "?" in url:
                    return listing(entries)
                return payloads["master" if "/master-" in url else "dev"]

            updates = updater.prepare_development_updates(root, fetch)
            self.assertEqual(len(updates), 2)
            for path, content in updates.items():
                path.write_text(content)
            self.assertEqual(updater.prepare_development_updates(root, fetch), {})
            # Same bundle metadata, size, and version, but different executable bytes.
            data = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(payloads["master"])) as original:
                with zipfile.ZipFile(data, "w") as changed:
                    for entry in original.infolist():
                        content = original.read(entry)
                        if entry.filename.endswith("/MacOS/Flycast"):
                            content = b"TEST executable"
                        changed.writestr(entry, content)
            payloads["master"] = data.getvalue()
            with self.assertRaisesRegex(ValueError, "changed without a version change"):
                updater.prepare_development_updates(root, fetch)


if __name__ == "__main__":
    unittest.main()
