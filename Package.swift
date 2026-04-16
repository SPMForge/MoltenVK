// swift-tools-version: 6.0

import Foundation
import PackageDescription

let packageVersionFile = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .appendingPathComponent("SwiftPackage/PackageVersion.txt")
    .path
let releaseRepositoryFile = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .appendingPathComponent("SwiftPackage/ReleaseRepository.txt")
    .path
let localArtifactPath = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .appendingPathComponent("Artifacts/MoltenVK.xcframework")
    .path
let checksumFile = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()
    .appendingPathComponent("Artifacts/MoltenVK.xcframework.checksum")
    .path

guard let rawPackageVersion = try? String(contentsOfFile: packageVersionFile, encoding: .utf8) else {
    fatalError("Missing MoltenVK package version file: \(packageVersionFile)")
}
let packageVersion = rawPackageVersion.trimmingCharacters(in: .whitespacesAndNewlines)
guard !packageVersion.isEmpty else {
    fatalError("MoltenVK package version file is empty: \(packageVersionFile)")
}

guard let rawReleaseRepository = try? String(contentsOfFile: releaseRepositoryFile, encoding: .utf8) else {
    fatalError("Missing MoltenVK release repository file: \(releaseRepositoryFile)")
}
let releaseRepository = rawReleaseRepository.trimmingCharacters(in: .whitespacesAndNewlines)
guard !releaseRepository.isEmpty else {
    fatalError("MoltenVK release repository file is empty: \(releaseRepositoryFile)")
}

func readChecksum() -> String {
    guard let checksum = try? String(contentsOfFile: checksumFile, encoding: .utf8)
        .trimmingCharacters(in: .whitespacesAndNewlines),
          !checksum.isEmpty else {
        fatalError("Missing MoltenVK xcframework checksum file: \(checksumFile)")
    }
    return checksum
}

let remoteArtifactURL = "https://github.com/\(releaseRepository)/releases/download/MoltenVK-v\(packageVersion)/MoltenVK.xcframework.zip"

let moltenVKTarget: Target = {
    if FileManager.default.fileExists(atPath: localArtifactPath) {
        return .binaryTarget(
            name: "MoltenVK",
            path: "Artifacts/MoltenVK.xcframework"
        )
    }

    return .binaryTarget(
        name: "MoltenVK",
        url: remoteArtifactURL,
        checksum: readChecksum()
    )
}()

let package = Package(
    name: "MoltenVK",
    platforms: [
        .iOS(.v14),
        .macOS(.v11),
    ],
    products: [
        .library(
            name: "MoltenVK",
            targets: ["MoltenVK"]
        ),
    ],
    targets: [
        moltenVKTarget,
    ]
)
