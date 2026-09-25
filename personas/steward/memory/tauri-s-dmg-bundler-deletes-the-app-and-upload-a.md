# Tauri's dmg bundler deletes the .app, and upload-artifact drops the exec

_2026-09-20 17:38 · persistent_

tauri build --bundles dmg DELETES the .app it built as an intermediate ('Cleaning .../bundle/macos/charter.app'). A second bundler call for an extra target must name both targets (--bundles app,dmg) or the first call's output is gone. Also: a .app must be uploaded as a ditto archive — actions/upload-artifact's zip drops the executable bit and the bundle will not launch. And Tauri names the bundle executable after the CARGO bin name (charter-app), not productName, which is what leaves room for a 'charter' sidecar beside it in Contents/MacOS.
