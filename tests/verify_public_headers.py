#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_VERSION = (REPO_ROOT / "SwiftPackage" / "PackageVersion.txt").read_text().strip()
HEADERS_ARCHIVE_NAME = f"MoltenVKHeaders-{PACKAGE_VERSION}.zip"
HEADERS_ARCHIVE = REPO_ROOT / "Artifacts" / HEADERS_ARCHIVE_NAME

EXPECTED_DIRECTORIES = (
    "MoltenVK",
    "MoltenVK/vk_video",
    "MoltenVK/vulkan",
    "vk_video",
    "vulkan",
)
EXPECTED_FILES = (
    Path("MoltenVK/mvk_vulkan.h"),
    Path("MoltenVK/vk_video/vulkan_video_codecs_common.h"),
    Path("MoltenVK/vulkan/vk_platform.h"),
    Path("MoltenVK/vulkan/vulkan.h"),
    Path("vulkan/vulkan.h"),
    Path("vk_video/vulkan_video_codecs_common.h"),
)

C_PROBES = {
    "vulkan-sdk-style": """\
#include <vulkan/vulkan.h>
int main(void) { return 0; }
""",
    "moltenvk-framework-style": """\
#include <MoltenVK/vulkan/vk_platform.h>
int main(void) { return 0; }
""",
    "combined-vulkan-and-framework-style": """\
#include <vulkan/vulkan.h>
#include <MoltenVK/vulkan/vk_platform.h>
int main(void) { return 0; }
""",
}

CXX_PROBE = """\
#include <vulkan/vulkan.h>
#include <MoltenVK/vulkan/vk_platform.h>
int main() { return 0; }
"""


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


def compile_probe(compiler: str, arguments: list[str], source: Path, include_root: Path, context: str) -> None:
    resolved_compiler = shutil.which(compiler)
    if resolved_compiler is None:
        raise RuntimeError(f"missing required compiler for {context}: {compiler}")

    completed = subprocess.run(
        [resolved_compiler, "-fsyntax-only", "-I", str(include_root), *arguments, str(source)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{context} failed to compile with include root {include_root}: {details}")


def assert_build_time_include_contract(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="moltenvk-include-probes.") as probe_dir:
        probe_root = Path(probe_dir)

        for name, source_text in C_PROBES.items():
            source_path = probe_root / f"{name}.c"
            source_path.write_text(source_text, encoding="utf-8")
            compile_probe("clang", [], source_path, root, name)

        cxx_source_path = probe_root / "combined-vulkan-and-framework-style.cpp"
        cxx_source_path.write_text(CXX_PROBE, encoding="utf-8")
        compile_probe("clang++", ["-std=c++17"], cxx_source_path, root, "combined C++ Vulkan include probe")


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
            assert_self_contained_header_tree(extracted_root, HEADERS_ARCHIVE_NAME)
            assert_build_time_include_contract(extracted_root)
    except RuntimeError as error:
        return fail(str(error))

    print(f"{HEADERS_ARCHIVE_NAME} contains a self-contained public header tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
