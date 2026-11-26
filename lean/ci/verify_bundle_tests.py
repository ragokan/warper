import importlib.util
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("verify_bundle", Path(__file__).with_name("verify-bundle.py"))
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class VerifyBundleTests(unittest.TestCase):
    def test_macos_plist_release_version(self):
        source = Path(__file__).with_name("bundle-macos.sh").read_text()
        generator = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        for ref_type, tag, version in (
            ("branch", "lean-ci", "0.1.0"),
            ("tag", "lean-v1.2.3", "1.2.3"),
            ("tag", "lean-v1.2.3-rc.1", "1.2.3"),
            ("tag", "lean-v1.2.3+build.1", "1.2.3"),
            ("tag", "lean-vbad", None),
            ("tag", "lean-v1.2", None),
            ("tag", "lean-v1.2.3-", None),
        ):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "Info.plist"
                result = subprocess.run(
                    [sys.executable, "-", str(path)], input=generator, text=True,
                    capture_output=True,
                    env=dict(os.environ, GITHUB_REF_TYPE=ref_type, GIT_RELEASE_TAG=tag),
                )
                if version is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(path.exists())
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    plist = plistlib.loads(path.read_bytes())
                    self.assertEqual(plist["CFBundleVersion"], version)
                    self.assertEqual(plist["CFBundleName"], "Warper")
                    self.assertEqual(plist["CFBundleDisplayName"], "Warper")
                    self.assertEqual(plist["CFBundleIdentifier"], "dev.warp.WarpOss")
                    self.assertEqual({item["NSMenuItem"]["default"] for item in plist["NSServices"]}, {"New Warper Tab Here", "New Warper Window Here"})

    def test_macos_package_rejects_wrong_arch_and_bundle_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contents = root / "Contents"
            (contents / "MacOS").mkdir(parents=True)
            binary = contents / "MacOS/warp-oss"
            binary.write_bytes(struct.pack("<II", 0xFEEDFACF, 0x0100000C))
            binary.chmod(0o755)
            resources = contents / "Resources"
            (resources / "bundled").mkdir(parents=True)
            (resources / "THIRD_PARTY_LICENSES.txt").write_text("licenses")
            (resources / "settings_schema.json").write_text("{}")
            (resources / "WarpOss.icns").write_bytes(b"icon")
            updater = resources / "warper-update"
            updater.write_text("#!/bin/sh\n")
            updater.chmod(0o755)
            plugin = contents / "PlugIns/WarpDockTilePlugin.docktileplugin/Contents/MacOS"
            plugin.mkdir(parents=True)
            (plugin / "WarpDockTilePlugin").write_bytes(b"plugin")
            plist = {
                "CFBundleName": "Warper",
                "CFBundleDisplayName": "Warper",
                "CFBundleIdentifier": "dev.warp.WarpOss",
                "CFBundleExecutable": "warp-oss",
                "CFBundlePackageType": "APPL",
                "CFBundleVersion": "0.1.0",
                "CFBundleIconFile": "WarpOss.icns",
                "NSDockTilePlugIn": "WarpDockTilePlugin.docktileplugin",
                "CFBundleURLTypes": [{"CFBundleURLSchemes": ["warposs"]}],
                "CFBundleDocumentTypes": [{"LSItemContentTypes": ["public.folder"]}],
                "NSServices": [{"NSMessage": "openTab"}, {"NSMessage": "openWindow"}],
                "SMAuthorizedClients": ["dev.warp.WarpOss"],
                "LSBackgroundOnly": False,
                "UIDesignRequiresCompatibility": True,
            }
            for permission in (
                "AppleEvents", "Camera", "Microphone", "Contacts", "Calendars",
                "CalendarsFullAccess", "Reminders", "RemindersFullAccess", "Location",
                "PhotoLibrary",
            ):
                plist[f"NS{permission}UsageDescription"] = "A program in Warp requests access."
            path = contents / "Info.plist"
            path.write_bytes(plistlib.dumps(plist))
            bundle.verify(root)
            for marker in (b"lean-ci", b"lean-v1.2.3"):
                binary.write_bytes(struct.pack("<II", 0xFEEDFACF, 0x0100000C) + marker)
                with self.subTest(marker=marker), self.assertRaisesRegex(AssertionError, "release marker"):
                    bundle.verify(root)
            binary.write_bytes(struct.pack("<II", 0xFEEDFACF, 0x0100000C))
            for key in (
                "CFBundleURLTypes", "CFBundleDocumentTypes", "NSServices", "SMAuthorizedClients",
                "NSCameraUsageDescription", "UIDesignRequiresCompatibility", "LSBackgroundOnly",
            ):
                with self.subTest(missing=key):
                    incomplete = dict(plist)
                    del incomplete[key]
                    path.write_bytes(plistlib.dumps(incomplete))
                    with self.assertRaises(AssertionError):
                        bundle.verify(root)
            wrong_scheme = dict(plist, CFBundleURLTypes=[{"CFBundleURLSchemes": ["warp"]}])
            path.write_bytes(plistlib.dumps(wrong_scheme))
            with self.assertRaises(AssertionError):
                bundle.verify(root)
            path.write_bytes(plistlib.dumps(plist))
            updater.chmod(0o644)
            with self.assertRaisesRegex(AssertionError, "Update script"):
                bundle.verify(root)
            updater.chmod(0o755)
            (resources / "bin").mkdir()
            wrapper = resources / "bin/warp-oss"
            wrapper.write_text('#!/bin/bash\nexec "$script_dir/../../MacOS/warp-oss" "$@"\n')
            wrapper.chmod(0o755)
            with self.assertRaisesRegex(AssertionError, "CLI"):
                bundle.verify(root)
            wrapper.unlink()
            wrapper.parent.rmdir()
            binary.write_bytes(struct.pack("<II", 0xFEEDFACF, 0x01000007))
            with self.assertRaisesRegex(AssertionError, "arm64"):
                bundle.verify(root)
            binary.write_bytes(struct.pack("<II", 0xFEEDFACF, 0x0100000C))
            plist["CFBundleIdentifier"] = "dev.warp.Warp-Stable"
            path.write_bytes(plistlib.dumps(plist))
            with self.assertRaises(AssertionError):
                bundle.verify(root)
