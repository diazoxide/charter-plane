# charter-app app-layer defects a review + the scenario tests found (2026-

_2026-09-17 19:35 · persistent_

charter-app app-layer defects a review + the scenario tests found (2026-09-17, M0.5) — worth knowing for any Tauri app of this shape: (1) Tauri's App::run ends the process with std::process::exit, so managed state is NEVER dropped: sessions' process groups leak unless you .build() then .run(|app,event| on RunEvent::Exit) and end them synchronously. (2) Clicking a pane does NOT focus the xterm inside it — typing went to the last-clicked button; the pane must call terminal.focus() (found only by the scenario test, since IPC send_input worked). (3) Never call a Tauri command from inside a React state updater: StrictMode re-runs updaters, so every close was asked twice — and tests must render in StrictMode or they do not test what ships. (4) A webview reload leaves every session in the core unreachable: sweep them on startup.
