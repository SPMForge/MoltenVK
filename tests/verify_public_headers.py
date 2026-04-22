#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HEADERS_ARCHIVE = REPO_ROOT / "Artifacts" / "MoltenVKHeaders.zip"

EXPECTED_DIRECTORIES = ("MoltenVK", "vulkan", "vk_video")
EXPECTED_FILES = (
    Path("MoltenVK/mvk_vulkan.h"),
    Path("vulkan/vulkan.h"),
    Path("vk_video/vulkan_video_codecs_common.h"),
)


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def assert_self_contained_header_tree(root: Path, context: str) -> None:
    if not root.is_dir():
        raise RuntimeError(f"{context} is missing header root: {root}")

    for directory_name in EXPECTED_DIRECTORIES:
        directory_path = root / directory_name
        if not directory_path.exists():
            raise RuntimeError(f"{context} is missing expected public header directory: {directory_path}")
        if directory_path.is_symlink():
            raise RuntimeError(f"{context} still exposes a symlinked public header directory: {directory_path}")
        if not directory_path.is_dir():
            raise RuntimeError(f"{context} expected a directory but found something else: {directory_path}")

    for file_path in EXPECTED_FILES:
        full_path = root / file_path
        if not full_path.is_file():
            raise RuntimeError(f"{context} is missing representative public header: {full_path}")

    for path in root.rglob("*"):
        if path.name.startswith("._"):
            raise RuntimeError(f"{context} contains AppleDouble metadata instead of clean headers: {path}")
        if path.is_symlink():
            raise RuntimeError(f"{context} contains symlinked public headers instead of copied files: {path}")


def extract_headers_archive(destination: Path) -> Path:
    if not HEADERS_ARCHIVE.is_file():
        raise RuntimeError(f"missing headers archive: {HEADERS_ARCHIVE}")

    subprocess.run(
        ["ditto", "-x", "-k", str(HEADERS_ARCHIVE), str(destination)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    extracted_root = destination / "include"
    if not extracted_root.is_dir():
        raise RuntimeError(f"headers archive did not extract an include/ directory: {HEADERS_ARCHIVE}")
    return extracted_root


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="moltenvk-public-headers.") as temp_dir:
            extracted_root = extract_headers_archive(Path(temp_dir))
            assert_self_contained_header_tree(extracted_root, "MoltenVKHeaders.zip")
    except RuntimeError as error:
        return fail(str(error))

    print("MoltenVKHeaders.zip contains a self-contained public header tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
