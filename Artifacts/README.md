This directory is reserved for Swift Package export artifacts.

`Scripts/SwiftPackage/build_swift_package.sh` populates:

- `MoltenVK.xcframework` as a mergeable dynamic XCFramework for Swift package consumers
- `MoltenVK-static.xcframework` for native static-link consumers such as `framework-ncnn`
- `MoltenVK.xcframework.zip` and `MoltenVK.xcframework.checksum` for remote SwiftPM distribution
- `MoltenVK-static.xcframework.zip` and `MoltenVK-static.xcframework.checksum` for native-package consumers that need the static library as a release asset
- `MoltenVKHeaders.zip` and `MoltenVKHeaders.checksum` for downstream native builds that need Vulkan/MoltenVK headers without a source checkout

The dynamic SwiftPM artifact is assembled from archived `macOS`, `iOS`, and `iOS Simulator` framework slices. Those framework slices carry the public headers and `Modules/module.modulemap` internally, and the final zipped XCFramework is validated for mergeable metadata plus import surface before publication.
