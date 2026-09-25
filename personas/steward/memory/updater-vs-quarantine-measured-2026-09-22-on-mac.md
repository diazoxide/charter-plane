# Updater vs quarantine, measured 2026-09-22 on macOS 26.2: tauri-plugin-u

_2026-09-22 16:04 · persistent_

Updater vs quarantine, measured 2026-09-22 on macOS 26.2: tauri-plugin-updater 2.12.0's macOS install (reqwest into memory, tar crate into a tempdir, fs::rename over the bundle) leaves NO com.apple.quarantine, even replacing a bundle that WAS quarantined. An ad-hoc app spctl rejects still launched through LaunchServices after it. curl never sets quarantine either; browsers do. Only com.apple.provenance appears, which Gatekeeper does not block on. Developer ID and a real browser download were NOT tested.
