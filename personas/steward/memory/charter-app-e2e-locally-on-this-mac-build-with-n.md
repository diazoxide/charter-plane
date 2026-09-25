# charter-app e2e locally on this Mac: build with 'npx tauri build --debug

_2026-09-25 15:08 · persistent_

charter-app e2e locally on this Mac: build with 'npx tauri build --debug --no-bundle --features e2e', run ONE spec with 'npx wdio run e2e/wdio.conf.ts --spec <spec>'. waitForDisplayed/isDisplayed never go true locally (window not painted), so probe with waitForExist and script clicks; browser.setWindowSize works (also on Linux CI). The macOS CI runner window is narrower than tauri.conf's 1280, so title-bar width bugs show only there.
