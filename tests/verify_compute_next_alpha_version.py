#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "Scripts" / "SwiftPackage" / "compute_next_alpha_version.py"

spec = importlib.util.spec_from_file_location("compute_next_alpha_version", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ComputeNextAlphaVersionTests(unittest.TestCase):
    def test_parse_release_identifiers_accepts_plain_semver_tags(self) -> None:
        parsed = module.parse_release_identifiers(["1.2.3-alpha.4"], [""])
        self.assertEqual([str(version) for _, version in parsed], ["1.2.3-alpha.4"])

    def test_parse_release_identifiers_accepts_legacy_prefixed_tags(self) -> None:
        parsed = module.parse_release_identifiers(["MoltenVK-v1.2.3-alpha.4"], list(module.DEFAULT_TAG_PREFIXES))
        self.assertEqual([str(version) for _, version in parsed], ["1.2.3-alpha.4"])

    def test_parse_release_identifiers_ignores_duplicate_identifiers(self) -> None:
        parsed = module.parse_release_identifiers(
            ["1.2.3-alpha.4", "1.2.3-alpha.4", "MoltenVK-v1.2.3-alpha.3"],
            list(module.DEFAULT_TAG_PREFIXES),
        )
        self.assertEqual([str(version) for _, version in parsed], ["1.2.3-alpha.4", "1.2.3-alpha.3"])

    def test_parse_tag_as_version_checks_legacy_prefix_after_plain_semver(self) -> None:
        parsed = module.parse_tag_as_version("MoltenVK-v1.2.3", list(module.DEFAULT_TAG_PREFIXES))
        self.assertIsNotNone(parsed)
        self.assertEqual(str(parsed), "1.2.3")


if __name__ == "__main__":
    unittest.main()
