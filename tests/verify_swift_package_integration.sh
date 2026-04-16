#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

assert_file() {
    [[ -f "$ROOT_DIR/$1" ]] || { echo "missing file: $1" >&2; exit 1; }
}

assert_missing() {
    [[ ! -e "$ROOT_DIR/$1" ]] || { echo "unexpected path: $1" >&2; exit 1; }
}

assert_contains() {
    grep -Fq -- "$2" "$ROOT_DIR/$1" || { echo "missing pattern '$2' in $1" >&2; exit 1; }
}

assert_file "Package.swift"
assert_contains "Package.swift" "name: \"MoltenVK\""
assert_contains "Package.swift" "SwiftPackage/PackageVersion.txt"
assert_contains "Package.swift" "Artifacts/MoltenVK.xcframework.checksum"
assert_contains "Package.swift" "releases/download/MoltenVK-v"
assert_contains "Package.swift" ".binaryTarget("
assert_contains "Package.swift" "Artifacts/MoltenVK.xcframework"

assert_file "Scripts/SwiftPackage/build_swift_package.sh"
assert_file "Scripts/SwiftPackage/build_swift_package_dependencies.sh"
assert_contains "Scripts/SwiftPackage/build_swift_package_dependencies.sh" "fetchDependencies"
assert_contains "Scripts/SwiftPackage/build_swift_package_dependencies.sh" "Prewarmed MoltenVK dependencies"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "fetchDependencies"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "SKIP_DEPENDENCY_FETCH"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "MVK_USE_METAL_PRIVATE_API=0"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "MoltenVK-static.xcframework"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "MoltenVK.xcframework"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "MoltenVK.xcframework.zip"
assert_contains "Scripts/SwiftPackage/build_swift_package.sh" "swift package compute-checksum"

assert_file "SwiftPackage/PackageVersion.txt"
assert_file "SwiftPackage/package-lock.json"
assert_file "Artifacts/MoltenVK.xcframework.checksum"
assert_file "Artifacts/MoltenVK-static.xcframework.checksum"
assert_file "Artifacts/MoltenVKHeaders.checksum"

assert_file "Artifacts/README.md"
assert_file "SwiftPackage/package.json"
assert_contains "SwiftPackage/package.json" "\"semantic-release\""
assert_contains "SwiftPackage/package.json" "\"@semantic-release/commit-analyzer\""
assert_contains "SwiftPackage/package.json" "\"@semantic-release/release-notes-generator\""
assert_contains "SwiftPackage/package.json" "\"@semantic-release/exec\""
assert_contains "SwiftPackage/package.json" "\"@semantic-release/git\""
assert_contains "SwiftPackage/package.json" "\"@semantic-release/github\""
assert_file "SwiftPackage/release.config.cjs"
assert_contains "SwiftPackage/release.config.cjs" "branches: [\"main\"]"
assert_contains "SwiftPackage/release.config.cjs" "tagFormat: \"MoltenVK-v\${version}\""
assert_contains "SwiftPackage/release.config.cjs" "@semantic-release/exec"
assert_contains "SwiftPackage/release.config.cjs" "@semantic-release/git"
assert_contains "SwiftPackage/release.config.cjs" "@semantic-release/github"
assert_contains "SwiftPackage/release.config.cjs" "./Scripts/SwiftPackage/prepare_semantic_release.sh \${nextRelease.version}"
assert_file "Scripts/SwiftPackage/prepare_semantic_release.sh"
assert_contains "Scripts/SwiftPackage/prepare_semantic_release.sh" "SwiftPackage/PackageVersion.txt"
assert_contains "Scripts/SwiftPackage/prepare_semantic_release.sh" "./Scripts/SwiftPackage/build_swift_package.sh"
assert_file ".github/workflows/CI.yml"
assert_contains ".github/workflows/CI.yml" "name: MoltenVK CI"
assert_contains ".github/workflows/CI.yml" "Prewarm MoltenVK dependencies"
assert_contains ".github/workflows/CI.yml" "Build Swift Package artifacts"
assert_contains ".github/workflows/CI.yml" "Upload package artifacts"
assert_file ".github/workflows/moltenvk-spm-release.yml"
assert_contains ".github/workflows/moltenvk-spm-release.yml" "branches:"
assert_contains ".github/workflows/moltenvk-spm-release.yml" "- main"
assert_contains ".github/workflows/moltenvk-spm-release.yml" "fetch-depth: 0"
assert_contains ".github/workflows/moltenvk-spm-release.yml" "actions/setup-node@v4"
assert_contains ".github/workflows/moltenvk-spm-release.yml" "npm ci --prefix SwiftPackage"
assert_contains ".github/workflows/moltenvk-spm-release.yml" "npx --prefix SwiftPackage semantic-release --extends ./SwiftPackage/release.config.cjs"

assert_missing "PackageVersion.txt"
assert_missing "package.json"
assert_missing "package-lock.json"
assert_missing "release.config.cjs"
assert_missing "build_swift_package.sh"
assert_missing "build_swift_package_dependencies.sh"
assert_missing "Scripts/prepare_semantic_release.sh"

echo "MoltenVK Swift package integration layout verified"
