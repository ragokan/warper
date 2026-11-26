#!/usr/bin/env python3
"""Check an unpacked Warper.app without running it."""

import argparse
import json
from pathlib import Path
import plistlib
import re
import struct
import subprocess


def verify(root):
    contents = root / "Contents"
    with (contents / "Info.plist").open("rb") as stream:
        plist = plistlib.load(stream)
    assert plist["CFBundleIdentifier"] == "dev.warp.WarpOss", plist
    assert plist["CFBundleName"] == "Warper", plist
    assert plist["CFBundleDisplayName"] == "Warper", plist
    assert plist["CFBundleExecutable"] == "warp-oss", plist
    assert plist["CFBundlePackageType"] == "APPL", plist
    assert re.fullmatch(r"\d+\.\d+\.\d+", plist["CFBundleVersion"]), plist
    assert any(
        "warposs" in item.get("CFBundleURLSchemes", [])
        for item in plist.get("CFBundleURLTypes", [])
    ), "Missing warposs URL scheme"
    assert any(
        "public.folder" in item.get("LSItemContentTypes", [])
        for item in plist.get("CFBundleDocumentTypes", [])
    ), "Missing folder document type"
    assert {"openTab", "openWindow"} <= {
        item.get("NSMessage") for item in plist.get("NSServices", [])
    }, "Missing terminal services"
    assert "dev.warp.WarpOss" in plist.get("SMAuthorizedClients", []), "Missing authorized client"
    assert plist.get("LSBackgroundOnly") is False, "Expected foreground app"
    assert plist.get("UIDesignRequiresCompatibility") is True, "Missing compatibility setting"
    for permission in (
        "AppleEvents", "Camera", "Microphone", "Contacts", "Calendars",
        "CalendarsFullAccess", "Reminders", "RemindersFullAccess", "Location",
        "PhotoLibrary",
    ):
        key = f"NS{permission}UsageDescription"
        assert isinstance(plist.get(key), str) and plist[key], f"Missing {key}"
    binary = contents / "MacOS" / plist["CFBundleExecutable"]
    resources = contents / "Resources"
    updater = resources / "warper-update"
    assert not (resources / "bin").exists(), "CLI wrappers must not ship in the lean bundle"
    assert (resources / plist["CFBundleIconFile"]).stat().st_size > 0
    plugin = contents / "PlugIns" / plist["NSDockTilePlugIn"]
    assert (plugin / "Contents/MacOS/WarpDockTilePlugin").stat().st_size > 0
    with binary.open("rb") as stream:
        magic, cpu = struct.unpack("<II", stream.read(8))
    assert (magic, cpu) == (0xFEEDFACF, 0x0100000C), "Expected arm64 Mach-O"
    print(json.dumps(plist, indent=2))
    assert binary.stat().st_mode & 0o111, "Binary is not executable"
    assert updater.is_file() and updater.stat().st_mode & 0o111, "Update script missing or not executable"
    assert (resources / "bundled").is_dir(), "Bundled resources missing"
    assert (resources / "THIRD_PARTY_LICENSES.txt").stat().st_size > 0
    with (resources / "settings_schema.json").open() as stream:
        assert isinstance(json.load(stream), dict), "Expected settings schema object"
    strings = subprocess.check_output(["strings", "-a", str(binary)])
    markers = sum(bool(re.search(rb"lean-(ci|v[0-9])", line)) for line in strings.splitlines())
    print(f"Lean release markers in binary: {markers}")
    assert markers == 0, "Lean release marker embedded in binary"
    print(f"Verified macOS arm64 package: {root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="the unpacked Warper.app")
    args = parser.parse_args()
    verify(args.root)
