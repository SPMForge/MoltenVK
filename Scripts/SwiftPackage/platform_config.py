#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path

DEFAULT_PLATFORM_CONFIG_PATH = Path(__file__).resolve().parents[2] / "SwiftPackage" / "platforms.json"
DEPLOYMENT_TARGET_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def validate_deployment_target_version(value: str, family: str) -> str:
    version = value.strip()
    if not DEPLOYMENT_TARGET_RE.fullmatch(version):
        raise ValueError(
            f"deployment target version for {family} must be an explicit major.minor string such as 11.0 or 14.0"
        )
    return version


def load_platform_config(path: str | Path = DEFAULT_PLATFORM_CONFIG_PATH) -> dict:
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"Missing platform config: {config_path}")

    data = json.loads(config_path.read_text())
    deployment_targets = data.get("deployment_targets")
    build_matrix = data.get("build_matrix")

    if not isinstance(deployment_targets, dict) or not deployment_targets:
        raise ValueError("platform config must define a non-empty deployment_targets object")
    if not isinstance(build_matrix, list) or not build_matrix:
        raise ValueError("platform config must define a non-empty build_matrix array")

    seen_build_flags: set[str] = set()
    seen_ids: set[str] = set()

    for family, entry in deployment_targets.items():
        if not isinstance(entry, dict):
            raise ValueError(f"deployment target entry for {family} must be an object")
        version = entry.get("version")
        swiftpm_platform = entry.get("swiftpm_platform")
        xcodebuild_setting = entry.get("xcodebuild_setting")
        if not isinstance(version, str) or not version:
            raise ValueError(f"deployment target version for {family} must be a non-empty string")
        version = validate_deployment_target_version(version, family)
        entry["version"] = version
        if not isinstance(swiftpm_platform, str) or not swiftpm_platform:
            raise ValueError(f"swiftpm_platform for {family} must be a non-empty string")
        if not isinstance(xcodebuild_setting, str) or not xcodebuild_setting:
            raise ValueError(f"xcodebuild_setting for {family} must be a non-empty string")

    required_build_fields = (
        "id",
        "family",
        "build_flag",
        "destination",
        "sdk",
        "validator_key",
        "vtool_platform",
        "consumer_test",
    )
    for entry in build_matrix:
        if not isinstance(entry, dict):
            raise ValueError("build_matrix entries must be objects")
        missing_fields = [field for field in required_build_fields if field not in entry]
        if missing_fields:
            raise ValueError(f"build_matrix entry is missing required fields: {', '.join(missing_fields)}")

        platform_id = entry["id"]
        family = entry["family"]
        build_flag = entry["build_flag"]
        if not isinstance(platform_id, str) or not platform_id:
            raise ValueError("build_matrix id must be a non-empty string")
        if not isinstance(family, str) or family not in deployment_targets:
            raise ValueError(f"build_matrix family for {platform_id} must reference a deployment_targets entry")
        if not isinstance(build_flag, str) or not build_flag.startswith("--"):
            raise ValueError(f"build_flag for {platform_id} must be a CLI flag like --macos")
        if not isinstance(entry["destination"], str) or not entry["destination"]:
            raise ValueError(f"destination for {platform_id} must be a non-empty string")
        if not isinstance(entry["sdk"], str) or not entry["sdk"]:
            raise ValueError(f"sdk for {platform_id} must be a non-empty string")
        if not isinstance(entry["validator_key"], str) or not entry["validator_key"]:
            raise ValueError(f"validator_key for {platform_id} must be a non-empty string")
        if not isinstance(entry["vtool_platform"], str) or not entry["vtool_platform"]:
            raise ValueError(f"vtool_platform for {platform_id} must be a non-empty string")
        if not isinstance(entry["consumer_test"], bool):
            raise ValueError(f"consumer_test for {platform_id} must be a boolean")

        if platform_id in seen_ids:
            raise ValueError(f"duplicate platform id in build_matrix: {platform_id}")
        if build_flag in seen_build_flags:
            raise ValueError(f"duplicate build_flag in build_matrix: {build_flag}")
        seen_ids.add(platform_id)
        seen_build_flags.add(build_flag)

    return data


def manifest_platform_entries(config: dict) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for family, entry in config["deployment_targets"].items():
        entries.append((entry["swiftpm_platform"], entry["version"]))
    return entries


def expected_vtool_platforms(config: dict) -> dict[str, str]:
    return {entry["validator_key"]: entry["vtool_platform"] for entry in config["build_matrix"]}


def expected_validator_deployment_targets(config: dict) -> dict[str, str]:
    deployment_targets = config["deployment_targets"]
    return {entry["validator_key"]: deployment_targets[entry["family"]]["version"] for entry in config["build_matrix"]}


def deployment_target_build_settings(config: dict) -> list[tuple[str, str]]:
    settings: list[tuple[str, str]] = []
    for family, entry in config["deployment_targets"].items():
        settings.append((entry["xcodebuild_setting"], entry["version"]))
    return settings


def bash_array(values: list[str]) -> str:
    return "(" + " ".join(shlex.quote(value) for value in values) + ")"


def render_shell(config: dict) -> str:
    deployment_targets = config["deployment_targets"]
    build_matrix = config["build_matrix"]
    deployment_target_families = list(deployment_targets.keys())
    deployment_target_build_settings_list = deployment_target_build_settings(config)

    lines = [
        f"export MOLTENVK_PACKAGE_IOS_DEPLOYMENT_TARGET={shlex.quote(deployment_targets['ios']['version'])}",
        f"export MOLTENVK_PACKAGE_MACOS_DEPLOYMENT_TARGET={shlex.quote(deployment_targets['macos']['version'])}",
        f"export MOLTENVK_PACKAGE_TVOS_DEPLOYMENT_TARGET={shlex.quote(deployment_targets['tvos']['version'])}",
        f"export MOLTENVK_PACKAGE_VISIONOS_DEPLOYMENT_TARGET={shlex.quote(deployment_targets['visionos']['version'])}",
        f"MOLTENVK_DEPLOYMENT_TARGET_FAMILIES={bash_array(deployment_target_families)}",
        f"MOLTENVK_DEPLOYMENT_TARGET_SWIFTPM_PLATFORMS={bash_array([deployment_targets[family]['swiftpm_platform'] for family in deployment_target_families])}",
        f"MOLTENVK_DEPLOYMENT_TARGET_VERSIONS={bash_array([deployment_targets[family]['version'] for family in deployment_target_families])}",
        f"MOLTENVK_DEPLOYMENT_TARGET_BUILD_SETTINGS={bash_array([f'{setting}={version}' for setting, version in deployment_target_build_settings_list])}",
        f"MOLTENVK_PLATFORM_IDS={bash_array([entry['id'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_FAMILIES={bash_array([entry['family'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_BUILD_FLAGS={bash_array([entry['build_flag'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_DESTINATIONS={bash_array([entry['destination'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_SDKS={bash_array([entry['sdk'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_VALIDATOR_KEYS={bash_array([entry['validator_key'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_VTOOL_CODES={bash_array([entry['vtool_platform'] for entry in build_matrix])}",
        f"MOLTENVK_PLATFORM_CONSUMER_TESTS={bash_array(['1' if entry['consumer_test'] else '0' for entry in build_matrix])}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load and validate the MoltenVK Apple platform config.")
    parser.add_argument(
        "command",
        choices=("render-shell", "print-json"),
        help="Render validated platform config as shell assignments or normalized JSON.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_PLATFORM_CONFIG_PATH),
        help="Path to the platform config JSON file.",
    )
    args = parser.parse_args()

    config = load_platform_config(args.config)
    if args.command == "render-shell":
        print(render_shell(config))
        return 0
    if args.command == "print-json":
        print(json.dumps(config, indent=2))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
