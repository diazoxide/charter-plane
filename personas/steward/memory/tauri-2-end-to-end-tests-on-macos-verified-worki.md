# Tauri 2 end-to-end tests on macOS, verified working 2026-09-17 in charte

_2026-09-17 18:58 · persistent_

Tauri 2 end-to-end tests on macOS, verified working 2026-09-17 in charter-app: use @wdio/tauri-service with its DEFAULT driverProvider 'embedded' — an HTTP WebDriver server inside the app from the crate tauri-plugin-wdio-webdriver, plus tauri-plugin-wdio for browser.tauri.execute. Both are free and need no external driver (plain tauri-driver has NO macOS path; CrabNebula's fork needs a paid CN_API_KEY). Their ADR: github.com/webdriverio/desktop-mobile docs/adr/0002. Needs withGlobalTauri true and a capability granting 'wdio:default' and 'wdio-webdriver:default' — put both behind a cargo feature plus a tauri --config override so no shipped build carries them. Also: tauri-specta REFUSES to generate u64 (JS precision), so command ids must be u32.
