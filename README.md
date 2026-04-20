MoltenVK SwiftPM Wrapper
========================

This repository is an independent wrapper repo for distributing MoltenVK as a Swift Package binary package backed by GitHub Releases.

Repository architecture
-----------------------

- The wrapper repo owns the Swift Package contract, release workflows, validation workflows, and generated `Package.swift`.
- Upstream source ownership remains with [KhronosGroup/MoltenVK](https://github.com/KhronosGroup/MoltenVK).
- CI does not treat this checkout as the source of truth for MoltenVK source code.
- CI fetches upstream tags into `refs/upstream-tags/*`, exports the requested upstream snapshot, and builds release artifacts from that exported snapshot.
- The in-repo upstream source tree has been removed; if local debugging against upstream source is needed, fetch or clone upstream separately.

Package contract
----------------

- Package name: `MoltenVK`
- Product name: `MoltenVK`
- Binary target: `MoltenVKBinary`
- Release tag format: `MoltenVK-v<version>`
- Primary SwiftPM asset: `MoltenVK.xcframework.zip`
- Additional release assets:
  - `MoltenVK-static.xcframework.zip`
  - `MoltenVKHeaders.zip`
- Current generated manifest path: `Package.swift`

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
  - builds mergeable dynamic MoltenVK archives
  - assembles XCFramework artifacts
  - computes checksums from the final zip archives
  - renders `Package.swift`
- `Scripts/SwiftPackage/publish_release.sh`
  - commits generated metadata
  - creates the package tag
  - creates the GitHub Release

CI topology
-----------

- `.github/workflows/validate-apple-release-pipeline.yml`
  - non-publishing validation workflow
  - rebuilds artifacts from an exported upstream snapshot
  - validates manifest, artifacts, and consumer smoke tests
- `.github/workflows/publish-package-release-core.yml`
  - shared reusable release workflow invoked by thin publish entrypoints
- `.github/workflows/publish-latest-upstream-alpha.yml`
  - `push` to `main` publishes the latest upstream alpha package release
- `.github/workflows/publish-upstream-release-manually.yml`
  - `workflow_dispatch` publishes the requested upstream tag as alpha or stable

Consumer note
-------------

When integrating this package into a Release configuration that enables merged binaries, set `MERGED_BINARY_TYPE=automatic`.
