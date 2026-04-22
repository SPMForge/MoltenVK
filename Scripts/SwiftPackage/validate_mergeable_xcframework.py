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
from pathlib import PurePosixPath

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from platform_config import expected_vtool_platforms, load_platform_config

EXPECTED_VTOOL_PLATFORMS = expected_vtool_platforms(load_platform_config())
PUBLIC_HEADER_SUFFIXES = {".h", ".hpp", ".cppm"}
INCLUDE_DIRECTIVE_RE = re.compile(r'^(?P<prefix>\s*#\s*(?:include|import)\s*)(?P<open>[<"])(?P<target>[^>"]+)(?P<close>[>"])')
MAX_FRAMEWORK_INCLUDE_ISSUES = 25


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


def macos_framework_layout_issues(framework_path: Path, binary_path: Path) -> list[str]:
    framework_name = framework_path.stem
    versions_dir = framework_path / "Versions"
    current_version = versions_dir / "Current"
    version_a_dir = versions_dir / "A"
    versioned_binary = version_a_dir / framework_name
    top_level_binary = framework_path / framework_name
    versioned_resources = version_a_dir / "Resources"
    top_level_resources = framework_path / "Resources"
    versioned_info = versioned_resources / "Info.plist"

    issues: list[str] = []

    if not versions_dir.is_dir():
        issues.append(f"macos: missing versioned framework directory {versions_dir}")
    if not version_a_dir.is_dir():
        issues.append(f"macos: missing versioned framework directory {version_a_dir}")
    if not current_version.is_symlink():
        issues.append(f"macos: missing version symlink {current_version}")
    elif current_version.resolve() != version_a_dir.resolve():
        issues.append(f"macos: {current_version} does not resolve to {version_a_dir}")

    if not versioned_binary.exists():
        issues.append(f"macos: missing versioned framework binary {versioned_binary}")
    if binary_path.resolve() != versioned_binary.resolve():
        issues.append(f"macos: binary path {binary_path} does not resolve to {versioned_binary}")
    if not top_level_binary.is_symlink():
        issues.append(f"macos: top-level framework binary is not a symlink ({top_level_binary})")
    elif top_level_binary.resolve() != versioned_binary.resolve():
        issues.append(f"macos: top-level framework binary does not resolve to {versioned_binary}")

    if not versioned_info.is_file():
        issues.append(f"macos: missing versioned framework Info.plist {versioned_info}")
    if not top_level_resources.is_symlink():
        issues.append(f"macos: top-level Resources is not a symlink ({top_level_resources})")
    elif top_level_resources.resolve() != versioned_resources.resolve():
        issues.append(f"macos: top-level Resources does not resolve to {versioned_resources}")

    return issues


def normalize_logical_path(path: PurePosixPath) -> PurePosixPath | None:
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return PurePosixPath(*parts)


def framework_public_header_index(headers_dir: Path) -> set[PurePosixPath]:
    index: set[PurePosixPath] = set()
    for path in headers_dir.rglob("*"):
        if path.is_file():
            index.add(PurePosixPath(path.relative_to(headers_dir).as_posix()))
    return index


def expected_framework_include(
    include_target: str,
    delimiter: str,
    logical_parent: PurePosixPath,
    public_headers: set[PurePosixPath],
) -> str | None:
    if delimiter == "<":
        if include_target.startswith("MoltenVK/"):
            return None
        if include_target.startswith("vulkan/") or include_target.startswith("vk_video/"):
            return f"MoltenVK/{include_target}"
        target_path = normalize_logical_path(PurePosixPath(include_target))
        if target_path is not None and target_path in public_headers:
            return f"MoltenVK/{target_path.as_posix()}"
        return None

    if include_target.startswith("vulkan/") or include_target.startswith("vk_video/"):
        return f"MoltenVK/{include_target}"

    target_path = normalize_logical_path(logical_parent / include_target)
    if target_path is None:
        return None
    if target_path in public_headers:
        return f"MoltenVK/{target_path.as_posix()}"
    if target_path.suffix in PUBLIC_HEADER_SUFFIXES and (
        len(target_path.parts) == 1 or target_path.parts[0] in {"vulkan", "vk_video"}
    ):
        return f"MoltenVK/{target_path.as_posix()}"
    return None


def framework_header_include_issues(platform: str, framework_path: Path, headers_dir: Path) -> list[str]:
    public_headers = framework_public_header_index(headers_dir)
    issues: list[str] = []

    for path in sorted(headers_dir.rglob("*")):
        if not path.is_file() or path.suffix not in PUBLIC_HEADER_SUFFIXES:
            continue

        logical_parent = PurePosixPath(path.relative_to(headers_dir).parent.as_posix())
        display_path = path.relative_to(framework_path).as_posix()

        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            match = INCLUDE_DIRECTIVE_RE.match(line)
            if not match:
                continue

            target = match.group("target")
            expected_target = expected_framework_include(
                target,
                match.group("open"),
                logical_parent,
                public_headers,
            )
            if expected_target is None:
                continue

            issues.append(
                f'{platform}: non-modular framework include {display_path}:{line_number} uses '
                f'{match.group("open")}{target}{match.group("close")} instead of <{expected_target}>'
            )
            if len(issues) == MAX_FRAMEWORK_INCLUDE_ISSUES:
                issues.append(f"{platform}: additional non-modular framework include issues omitted")
                return issues

    return issues


def framework_interface_issues(platform: str, framework_path: Path) -> list[str]:
    issues: list[str] = []

    if platform == "macos":
        version_a_dir = framework_path / "Versions" / "A"
        headers_dir = version_a_dir / "Headers"
        modules_dir = version_a_dir / "Modules"
        top_level_headers = framework_path / "Headers"
        top_level_modules = framework_path / "Modules"

        if not headers_dir.is_dir():
            issues.append(f"{platform}: missing versioned framework headers directory {headers_dir}")
        if not modules_dir.is_dir():
            issues.append(f"{platform}: missing versioned framework modules directory {modules_dir}")
        if not (modules_dir / "module.modulemap").is_file():
            issues.append(f"{platform}: missing versioned framework module map {(modules_dir / 'module.modulemap')}")
        if not (headers_dir / "mvk_vulkan.h").is_file():
            issues.append(f"{platform}: missing framework public header {(headers_dir / 'mvk_vulkan.h')}")
        if not top_level_headers.is_symlink():
            issues.append(f"{platform}: top-level Headers is not a symlink ({top_level_headers})")
        elif headers_dir.exists() and top_level_headers.resolve() != headers_dir.resolve():
            issues.append(f"{platform}: top-level Headers does not resolve to {headers_dir}")
        if not top_level_modules.is_symlink():
            issues.append(f"{platform}: top-level Modules is not a symlink ({top_level_modules})")
        elif modules_dir.exists() and top_level_modules.resolve() != modules_dir.resolve():
            issues.append(f"{platform}: top-level Modules does not resolve to {modules_dir}")
        if headers_dir.is_dir():
            issues.extend(framework_header_include_issues(platform, framework_path, headers_dir))
        return issues

    headers_dir = framework_path / "Headers"
    modules_dir = framework_path / "Modules"
    modulemap_path = modules_dir / "module.modulemap"

    if not headers_dir.is_dir():
        issues.append(f"{platform}: missing framework headers directory {headers_dir}")
    if not modules_dir.is_dir():
        issues.append(f"{platform}: missing framework modules directory {modules_dir}")
    if not modulemap_path.is_file():
        issues.append(f"{platform}: missing framework module map {modulemap_path}")
    if not (headers_dir / "mvk_vulkan.h").is_file():
        issues.append(f"{platform}: missing framework public header {(headers_dir / 'mvk_vulkan.h')}")
    if headers_dir.is_dir():
        issues.extend(framework_header_include_issues(platform, framework_path, headers_dir))
    return issues


def inspect_entry(xcframework_path: Path, entry: dict[str, object]) -> dict[str, object]:
    library_identifier = entry.get("LibraryIdentifier")
    library_name = entry.get("LibraryPath")
    binary_name = entry.get("BinaryPath") or entry.get("LibraryPath")
    library_path = (
        xcframework_path / str(library_identifier) / str(library_name)
        if isinstance(library_identifier, str) and isinstance(library_name, str)
        else None
    )
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
        "library_path": str(library_path) if library_path is not None else None,
        "library_exists": bool(library_path and library_path.exists()),
        "binary_path": str(binary_path) if binary_path is not None else None,
        "binary_exists": bool(binary_path and binary_path.exists()),
        "expected_vtool_platform": expected_vtool_platform,
    }

    if binary_path is None or not binary_path.exists():
        return result

    if platform == "macos" and library_path is not None and library_path.suffix == ".framework" and library_path.exists():
        result["macos_framework_layout_issues"] = macos_framework_layout_issues(library_path, binary_path)
    if library_path is not None and library_path.suffix == ".framework" and library_path.exists():
        result["framework_interface_issues"] = framework_interface_issues(platform, library_path)

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

    macos_framework_layout_issues = entry.get("macos_framework_layout_issues")
    if isinstance(macos_framework_layout_issues, list):
        issues.extend(str(issue) for issue in macos_framework_layout_issues)

    framework_interface_issues = entry.get("framework_interface_issues")
    if isinstance(framework_interface_issues, list):
        issues.extend(str(issue) for issue in framework_interface_issues)

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
    parser = argparse.ArgumentParser(description="Validate mergeable XCFramework metadata, slice binaries, and framework interface surface.")
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
