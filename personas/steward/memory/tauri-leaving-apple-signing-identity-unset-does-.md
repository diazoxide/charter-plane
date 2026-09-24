# Tauri: leaving APPLE_SIGNING_IDENTITY unset does NOT ad-hoc sign a macOS

_2026-09-23 09:58 · persistent_

Tauri: leaving APPLE_SIGNING_IDENTITY unset does NOT ad-hoc sign a macOS bundle — tauri-bundler's keychain() returns None and signs nothing, so executables carry only the linker's ad-hoc signature and the BUNDLE has no _CodeSignature seal, which codesign --verify --deep --strict rejects. Set APPLE_SIGNING_IDENTITY=- to get a real ad-hoc bundle signature (codesign --force -s -, no --timestamp, no --keychain). Both states print Signature=adhoc, so --verify --deep --strict is the only thing that tells them apart.
