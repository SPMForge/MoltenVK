module.exports = {
  branches: [
    {
      name: "main",
      prerelease: "alpha"
    }
  ],
  tagFormat: "MoltenVK-v${version}",
  plugins: [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/exec",
      {
        prepareCmd: "./Scripts/SwiftPackage/prepare_semantic_release.sh ${nextRelease.version}"
      }
    ],
    [
      "@semantic-release/git",
      {
        assets: [
          "Package.swift",
          "SwiftPackage/ReleaseRepository.txt",
          "SwiftPackage/PackageVersion.txt",
          "Artifacts/MoltenVK.xcframework.checksum",
          "Artifacts/MoltenVK-static.xcframework.checksum",
          "Artifacts/MoltenVKHeaders.checksum"
        ],
        message: "chore(release): MoltenVK-v${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
      }
    ],
    [
      "@semantic-release/github",
      {
        successComment: false,
        failComment: false,
        assets: [
          {
            path: "Artifacts/MoltenVK.xcframework.zip",
            label: "MoltenVK SwiftPM XCFramework"
          },
          {
            path: "Artifacts/MoltenVK.xcframework.checksum",
            label: "MoltenVK SwiftPM XCFramework checksum"
          },
          {
            path: "Artifacts/MoltenVK-static.xcframework.zip",
            label: "MoltenVK static XCFramework"
          },
          {
            path: "Artifacts/MoltenVK-static.xcframework.checksum",
            label: "MoltenVK static XCFramework checksum"
          },
          {
            path: "Artifacts/MoltenVKHeaders.zip",
            label: "MoltenVK headers bundle"
          },
          {
            path: "Artifacts/MoltenVKHeaders.checksum",
            label: "MoltenVK headers bundle checksum"
          }
        ]
      }
    ]
  ]
};
