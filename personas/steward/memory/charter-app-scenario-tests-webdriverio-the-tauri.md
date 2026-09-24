# charter-app scenario tests (WebdriverIO + the Tauri service) share ONE a

_2026-09-21 10:44 · persistent_

charter-app scenario tests (WebdriverIO + the Tauri service) share ONE app process across spec files, run in name order, so a spec that fails leaving a MODAL on screen (the profile picker) makes every later spec fail with 'button=... still not clickable' — the cascade hides the one real failure. Read the FIRST failing spec in the run, not the loudest. Measured 2026-09-21 on PR 131: panes.e2e could not press New tab (the + had scrolled away with the tabs), left the picker up, and picker/sidebar/stress all went red behind it.
