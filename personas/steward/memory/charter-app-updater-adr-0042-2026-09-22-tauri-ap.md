# charter-app updater (ADR 0042, 2026-09-22): @tauri-apps/cli 2.11.4 write

_2026-09-22 16:04 · persistent_

charter-app updater (ADR 0042, 2026-09-22): @tauri-apps/cli 2.11.4 writes NO version: field into an updater signature's trusted comment (only timestamp+file; no --app-version flag). 2.11.5 is the first that does, and tauri build sets it automatically. requireSignedVersion=true (the downgrade-attack guard, off by default upstream) rejects every update signed by an older CLI with MissingSignedVersion. Measured with tauri signer sign on both versions.
