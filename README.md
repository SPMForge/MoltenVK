MoltenVK SwiftPM Wrapper
========================

This repository is an independent wrapper repo for distributing MoltenVK as a Swift Package binary package backed by GitHub Releases.

Repository architecture
-----------------------

- The wrapper repo owns the Swift Package contract, release workflows, validation workflows, and generated remote-only `Package.swift`.
- Upstream source ownership remains with [KhronosGroup/MoltenVK](https://github.com/KhronosGroup/MoltenVK).
- CI does not treat this checkout as the source of truth for MoltenVK source code.
- CI fetches upstream tags into `refs/upstream-tags/*`, exports the requested upstream snapshot, and builds release artifacts from that exported snapshot.
- The in-repo upstream source tree has been removed; if local debugging against upstream source is needed, fetch or clone upstream separately.

Package contract
----------------

- Package name: `MoltenVK`
- Product name: `MoltenVK`
- Binary target: `MoltenVK`
- Supported SwiftPM platform families: `iOS`, `macOS`, `tvOS`, and `visionOS`
- Release tag format: `<version>` (plain SemVer, no prefix)
- Historical `MoltenVK-v<version>` tags are treated as legacy-only inputs during alpha-version discovery and duplicate-release checks.
- Primary SwiftPM asset: `MoltenVK-<version>.xcframework.zip`
- Additional release assets:
  - `MoltenVK-static-<version>.xcframework.zip`
  - `MoltenVKHeaders-<version>.zip`
- Current generated manifest path: `Package.swift`
- Runtime dependency model: `none`
  - The distributed `MoltenVK.framework` depends only on its own install name and Apple system frameworks/libraries such as Metal, Foundation, UIKit/AppKit, IOSurface, libc++, and libSystem.
  - This package is a Vulkan-over-Metal provider framework. It does not ship a `libvulkan.dylib` loader and does not promise a `libvulkan.1.dylib` alias.
  - Consumers that require a Vulkan loader name must satisfy that loader contract in their own package or app runtime closure; the MoltenVK SwiftPM package should not hide that gap with app-side `dlopen()` behavior.

Source acquisition contract
---------------------------

- Upstream repository: `SwiftPackage/UpstreamRepository.txt`
- Upstream source ref used by the current package metadata: `SwiftPackage/UpstreamSourceRef.txt`
- Release asset host repository: `SwiftPackage/ReleaseRepository.txt`
- Published package version: `SwiftPackage/PackageVersion.txt`

Build and release flow
----------------------

- `Scripts/SwiftPackage/build_swift_package_dependencies.sh`
  - exports the requested upstream snapshot and prewarms external dependencies there
- `Scripts/SwiftPackage/build_swift_package.sh`
  - exports the requested upstream snapshot
  - patches the exported `MoltenVK.xcodeproj` so tvOS mergeable framework archives do not inherit the upstream `-ld_classic` linker mode
  - builds mergeable dynamic MoltenVK archives
  - stages the public headers and explicit `module.modulemap` inside each `MoltenVK.framework` slice in the final `MoltenVK.xcframework`
  - rewrites same-framework public header dependencies to framework-style `<MoltenVK/...>` imports before publication
  - materializes `MoltenVKHeaders-<version>.zip` as the C/C++ build-time include contract without storing those headers in the wrapper repository
  - assembles XCFramework artifacts
  - computes checksums from the final zip archives
  - renders `Package.swift`
- `Scripts/SwiftPackage/publish_release.sh`
  - creates a `release/<package_tag>` commit containing the generated metadata for that package version
  - Alpha publishes create and tag a release/ commit without updating the default branch
  - the default branch can be fast-forwarded only from the manual stable path by setting `publish_to_default_branch=true`
  - creates the plain-SemVer package tag from that generated-metadata commit
  - creates the GitHub Release

Public headers contract
-----------------------

- The SwiftPM package no longer relies on a wrapper source target, repo-local `publicHeadersPath`, or checkout-state local artifact fallback in the committed `Package.swift`.
- The importable `MoltenVK` module surface lives inside each `MoltenVK.framework` slice as framework-internal `Headers` plus `Modules/module.modulemap`.
- Those framework-internal public headers must use framework-style same-module imports such as `<MoltenVK/vulkan/vulkan.h>`, not quoted or relative includes.
- `Artifacts/MoltenVKHeaders-<version>.zip` is the documented C/C++ build-time include contract built from temporary staging, not from checked-in wrapper headers.
- After extracting `MoltenVKHeaders-<version>.zip`, the documented include root is the extracted `include/` directory.
- That include root exposes both Vulkan SDK-style paths such as `<vulkan/vulkan.h>` and framework-style MoltenVK paths such as `<MoltenVK/vulkan/vk_platform.h>` and `<MoltenVK/vk_video/vulkan_video_codecs_common.h>`.
- CMake-style native consumers should pass `Vulkan_INCLUDE_DIR=<extracted>/include` and `Vulkan_LIBRARY=<path-to-MoltenVK.framework/MoltenVK>`.
- Native consumers should not assume `MoltenVK.framework/Headers` alone is a sufficient CMake include root.
- The wrapper repository must not keep a checked-in `Sources/MoltenVK/include` tree to satisfy SwiftPM import behavior.

CI topology
-----------

- `.github/workflows/validate-apple-release-pipeline.yml`
  - non-publishing validation workflow
  - rebuilds artifacts from an exported upstream snapshot
  - validates manifest, artifacts, and consumer smoke tests
- `.github/workflows/publish-package-release-core.yml`
  - shared reusable release workflow invoked by thin publish entrypoints
- `.github/workflows/publish-latest-upstream-alpha.yml`
  - `schedule` plus `workflow_dispatch` publishes the latest upstream alpha package release
- `.github/workflows/publish-upstream-release-manually.yml`
  - `workflow_dispatch` publishes the requested upstream tag as alpha or stable

Consumer note
-------------

When integrating this package into a Release configuration that enables merged binaries, set `MERGED_BINARY_TYPE=automatic`.

For package consumers, the framework slices carry the public headers and module map internally, so the SwiftPM import surface is defined by the distributed `MoltenVK.xcframework`, not by wrapper-repo checkout headers.

For local smoke tests or operator-only verification against a freshly built checkout artifact, use the explicit local-only manifest helper `Scripts/SwiftPackage/render_local_dev_package_manifest.py` instead of changing the committed `Package.swift`.
