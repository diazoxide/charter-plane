# Tauri 2 startup order, measured 2026-09-18 (charter-app M1.7) with a CHA

_2026-09-18 12:06 · persistent_

Tauri 2 startup order, measured 2026-09-18 (charter-app M1.7) with a CHARTER_LAUNCH_LOG marker at each step: Builder::build() returns BEFORE the setup hook runs — markers showed 'built' at 110ms and 'setup' at 441ms. So .setup() runs inside run(), not build(). Consequence: anything that stops the event loop or window creation coming up (a desktop with no session D-Bus, a failing WebKitGTK spawn) means setup NEVER runs, so any work put in setup — restoring sessions, reading the plane — silently does not happen, with no error and no window to show for it. Don't put work an operator depends on behind a window that may not come up, and give the app an env-gated startup log from the start: a GUI app that hangs on the way up has literally nothing to show, and three CI round trips established only that setup wasn't reached.
