#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
from pathlib import Path


def command_output(arguments: list[str]) -> str:
    return subprocess.check_output(arguments, text=True).strip()


def platform_key(entry: dict[str, object]) -> str:
    platform = entry.get("SupportedPlatform")
    variant = entry.get("SupportedPlatformVariant")
    if not isinstance(platform, str):
        return "unknown"
    if not isinstance(variant, str):
        return platform
    return f"{platform}-{variant}"


def discover_xcframeworks(raw_paths: list[str]) -> list[Path]:
    results: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path).resolve()
        if not path.exists():
            raise SystemExit(f"Path does not exist: {path}")
        if path.is_dir() and path.name.endswith(".xcframework"):
            results.append(path)
            continue
        if path.is_dir():
            results.extend(sorted(child for child in path.glob("*.xcframework") if child.is_dir()))
            continue
        raise SystemExit(f"Unsupported path: {path}")
    if not results:
        raise SystemExit("No XCFrameworks found.")
    return results


def inspect_entry(xcframework_path: Path, entry: dict[str, object]) -> dict[str, object]:
    library_identifier = entry.get("LibraryIdentifier")
    binary_name = entry.get("BinaryPath") or entry.get("LibraryPath")
    binary_path = (
        xcframework_path / str(library_identifier) / str(binary_name)
        if isinstance(library_identifier, str) and isinstance(binary_name, str)
        else None
    )

    result = {
        "platform": platform_key(entry),
        "architectures": entry.get("SupportedArchitectures") or [],
        "mergeable_metadata": entry.get("MergeableMetadata") is True,
        "binary_path": str(binary_path) if binary_path is not None else None,
        "binary_exists": bool(binary_path and binary_path.exists()),
    }

    if binary_path is not None and binary_path.exists() and shutil.which("xcrun"):
        try:
            output = command_output(["xcrun", "vtool", "-show-build", str(binary_path)])
            result["vtool_platforms"] = sorted(set(re.findall(r"platform\s+([A-Z0-9_]+)", output)))
        except subprocess.CalledProcessError as error:
            result["vtool_error"] = error.output.strip() if error.output else str(error)

    return result


def inspect_xcframework(xcframework_path: Path) -> dict[str, object]:
    info_path = xcframework_path / "Info.plist"
    if not info_path.exists():
        return {
            "xcframework": str(xcframework_path),
            "issues": [f"Missing Info.plist: {info_path}"],
            "entries": [],
        }

    info = plistlib.loads(info_path.read_bytes())
    available = info.get("AvailableLibraries")
    if not isinstance(available, list):
        return {
            "xcframework": str(xcframework_path),
            "issues": ["Info.plist missing AvailableLibraries"],
            "entries": [],
        }

    entries = [inspect_entry(xcframework_path, entry) for entry in available if isinstance(entry, dict)]
    issues: list[str] = []
    for entry in entries:
        if not entry["mergeable_metadata"]:
            issues.append(f"{entry['platform']}: missing MergeableMetadata")
        if not entry["binary_exists"]:
            issues.append(f"{entry['platform']}: missing binary at declared path")

    return {
        "xcframework": str(xcframework_path),
        "issues": issues,
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate mergeable XCFramework metadata and binary slices.")
    parser.add_argument("paths", nargs="+", help="XCFramework paths or directories that contain XCFrameworks.")
    parser.add_argument(
        "--require-platform",
        action="append",
        default=[],
        help="Require each XCFramework to contain a platform key such as ios, ios-simulator, ios-maccatalyst, macos, tvos, watchos, or xros.",
    )
    args = parser.parse_args()

    results = [inspect_xcframework(path) for path in discover_xcframeworks(args.paths)]
    required_platforms = sorted(set(args.require_platform))

    exit_code = 0
    for result in results:
        available_platforms = sorted(entry["platform"] for entry in result["entries"])
        missing_platforms = sorted(set(required_platforms) - set(available_platforms))
        if missing_platforms:
            result["issues"].extend(f"missing required platform {platform}" for platform in missing_platforms)
        if result["issues"]:
            exit_code = 1

    print(json.dumps({"xcframeworks": results}, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
