# Visually verifying charter-app UI on this Mac (2026-09-25): the terminal

_2026-09-25 12:23 · persistent_

Visually verifying charter-app UI on this Mac (2026-09-25): the terminal has no Screen Recording permission, so screencapture fails; use a throwaway WebdriverIO spec instead — build with 'npx tauri build --debug --no-bundle --features e2e --config src-tauri/tauri.e2e.conf.json', then 'npx wdio run e2e/wdio.conf.ts --spec <spec>' calling browser.saveScreenshot (fixture plane, no OS permission). Switch themes in the spec by setting cssVariables(BUILT_IN[name]) from src/theme/theme.ts on documentElement. 'npm run tauri dev' exits at once while the installed charter.app runs (single-instance, same identifier dev.charter.app); pass --config '{"identifier":"dev.charter.app.review"}'. Node is only at ~/.nvm/versions/node/v22.14.0/bin (not on PATH).
