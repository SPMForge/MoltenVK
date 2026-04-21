#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from platform_config import expected_vtool_platforms, load_platform_config

EXPECTED_VTOOL_PLATFORMS = expected_vtool_platforms(load_platform_config())


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

    platform = platform_key(entry)
    expected_vtool_platform = EXPECTED_VTOOL_PLATFORMS.get(platform)

    result = {
        "platform": platform,
        "architectures": entry.get("SupportedArchitectures") or [],
        "mergeable_metadata": entry.get("MergeableMetadata") is True,
        "binary_path": str(binary_path) if binary_path is not None else None,
        "binary_exists": bool(binary_path and binary_path.exists()),
        "expected_vtool_platform": expected_vtool_platform,
    }

    if binary_path is None or not binary_path.exists():
        return result

    if not shutil.which("xcrun"):
        result["vtool_error"] = "xcrun is unavailable"
        return result

    try:
        output = command_output(["xcrun", "vtool", "-show-build", str(binary_path)])
        result["vtool_platforms"] = sorted(set(re.findall(r"platform\s+([A-Z0-9_]+)", output)))
    except subprocess.CalledProcessError as error:
        result["vtool_error"] = error.output.strip() if error.output else str(error)

    return result


def entry_issues(entry: dict[str, object]) -> list[str]:
    issues: list[str] = []

    platform = str(entry.get("platform", "unknown"))
    if not entry.get("mergeable_metadata"):
        issues.append(f"{platform}: missing MergeableMetadata")
    if not entry.get("binary_exists"):
        issues.append(f"{platform}: missing binary at declared path")
        return issues

    expected_vtool_platform = entry.get("expected_vtool_platform")
    if not isinstance(expected_vtool_platform, str):
        issues.append(f"{platform}: unsupported vtool platform mapping")
        return issues

    vtool_error = entry.get("vtool_error")
    if isinstance(vtool_error, str) and vtool_error:
        issues.append(f"{platform}: unable to read vtool platform ({vtool_error})")
        return issues

    vtool_platforms = entry.get("vtool_platforms")
    if not isinstance(vtool_platforms, list) or not vtool_platforms:
        issues.append(f"{platform}: missing vtool platform output")
        return issues

    if expected_vtool_platform not in vtool_platforms:
        issues.append(
            f"{platform}: expected vtool platform {expected_vtool_platform}, got {', '.join(str(value) for value in vtool_platforms)}"
        )

    return issues


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
        issues.extend(entry_issues(entry))

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
