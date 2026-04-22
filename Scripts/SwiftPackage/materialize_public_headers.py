#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT_PUBLIC_HEADERS = (
    "mvk_config.h",
    "mvk_datatypes.h",
    "mvk_deprecated_api.h",
    "mvk_private_api.h",
    "mvk_vulkan.h",
    "vk_mvk_moltenvk.h",
)

MODULEMAP = """framework module MoltenVK {
  header "mvk_config.h"
  header "mvk_datatypes.h"
  header "mvk_deprecated_api.h"
  header "mvk_private_api.h"
  header "mvk_vulkan.h"
  header "vk_mvk_moltenvk.h"
  export *
}
"""


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.exists():
        shutil.rmtree(path)


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"missing required header source directory: {source}")
    remove_path(destination)
    shutil.copytree(source, destination, symlinks=False)


def ensure_no_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"public header staging must not contain symlinks: {path}")


def materialize_public_headers(moltenvk_api_dir: Path, vulkan_headers_root: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(moltenvk_api_dir, output_dir / "MoltenVK")
    copy_tree(vulkan_headers_root / "vulkan", output_dir / "vulkan")
    copy_tree(vulkan_headers_root / "vk_video", output_dir / "vk_video")
    ensure_no_symlinks(output_dir)


def framework_header_root(framework_path: Path) -> tuple[Path, Path, tuple[Path, Path] | None]:
    version_a = framework_path / "Versions" / "A"
    if version_a.is_dir():
        headers_dir = version_a / "Headers"
        modules_dir = version_a / "Modules"
        return headers_dir, modules_dir, (framework_path / "Headers", framework_path / "Modules")
    return framework_path / "Headers", framework_path / "Modules", None


def rewrite_framework_includes(headers_dir: Path) -> None:
    for header_name in ROOT_PUBLIC_HEADERS:
        header_path = headers_dir / header_name
        text = header_path.read_text()
        text = text.replace("<vulkan/", "<MoltenVK/vulkan/")
        text = text.replace("<vk_video/", "<MoltenVK/vk_video/")
        header_path.write_text(text)


def stage_framework_interface(public_headers_root: Path, framework_path: Path) -> None:
    headers_dir, modules_dir, top_level_links = framework_header_root(framework_path)
    headers_dir.mkdir(parents=True, exist_ok=True)
    modules_dir.mkdir(parents=True, exist_ok=True)

    for header_name in ROOT_PUBLIC_HEADERS:
        shutil.copy2(public_headers_root / "MoltenVK" / header_name, headers_dir / header_name)
    copy_tree(public_headers_root / "vulkan", headers_dir / "vulkan")
    copy_tree(public_headers_root / "vk_video", headers_dir / "vk_video")

    vk_video_link = headers_dir / "vulkan" / "vk_video"
    remove_path(vk_video_link)
    vk_video_link.symlink_to("../vk_video", target_is_directory=True)

    rewrite_framework_includes(headers_dir)
    (modules_dir / "module.modulemap").write_text(MODULEMAP)

    if top_level_links is None:
        return

    top_level_headers, top_level_modules = top_level_links
    remove_path(top_level_headers)
    top_level_headers.symlink_to("Versions/Current/Headers", target_is_directory=True)
    remove_path(top_level_modules)
    top_level_modules.symlink_to("Versions/Current/Modules", target_is_directory=True)


def stage_xcframework_interface(public_headers_root: Path, xcframework_path: Path) -> None:
    framework_paths = sorted(xcframework_path.glob("*/*.framework"))
    if not framework_paths:
        raise RuntimeError(f"xcframework does not contain any framework slices: {xcframework_path}")
    for framework_path in framework_paths:
        stage_framework_interface(public_headers_root, framework_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize MoltenVK public headers for release assets and stage the import surface into XCFramework slices."
    )
    parser.add_argument("--moltenvk-api-dir", required=True, help="Path to the upstream MoltenVK API headers directory.")
    parser.add_argument(
        "--vulkan-headers-root",
        required=True,
        help="Path to the upstream Vulkan-Headers include directory that contains vulkan/ and vk_video/.",
    )
    parser.add_argument("--output-dir", required=True, help="Destination include directory for the public headers asset.")
    parser.add_argument(
        "--xcframework-path",
        help="Optional MoltenVK.xcframework path whose framework slices should receive Headers and Modules/module.modulemap.",
    )
    args = parser.parse_args()

    moltenvk_api_dir = Path(args.moltenvk_api_dir).resolve()
    vulkan_headers_root = Path(args.vulkan_headers_root).resolve()
    output_dir = Path(args.output_dir).resolve()

    try:
        materialize_public_headers(moltenvk_api_dir, vulkan_headers_root, output_dir)
        if args.xcframework_path:
            stage_xcframework_interface(output_dir, Path(args.xcframework_path).resolve())
    except RuntimeError as error:
        parser.exit(1, f"error: {error}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
