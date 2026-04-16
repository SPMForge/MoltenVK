This directory is reserved for Swift Package export artifacts.

`build_swift_package.sh` populates:

- `MoltenVK.xcframework` for Swift package consumers
- `MoltenVK-static.xcframework` for native static-link consumers such as `framework-ncnn`
- `MoltenVK.xcframework.zip` and `MoltenVK.xcframework.checksum` for remote SwiftPM distribution
- `MoltenVK-static.xcframework.zip` and `MoltenVK-static.xcframework.checksum` for native-package consumers that need the static library as a release asset
- `MoltenVKHeaders.zip` and `MoltenVKHeaders.checksum` for downstream native builds that need Vulkan/MoltenVK headers without a source checkout
