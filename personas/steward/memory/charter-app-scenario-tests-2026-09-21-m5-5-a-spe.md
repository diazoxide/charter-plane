# charter-app scenario tests (2026-09-21, M5.5): a spec must NOT assume ho

_2026-09-21 05:34 · persistent_

charter-app scenario tests (2026-09-21, M5.5): a spec must NOT assume how many chat tabs the window has when it starts — specs share one app process and run in name order, so the count is whatever the spec before it left (projects.e2e.ts went red on both runners insisting on exactly one). And a PlaneId is the CANONICALISED root, so a fixture path from copyFixturePlane (under tmpdir(), which is /var/folders/... on macOS with /var a link into /private) never equals the id the app holds: realpathSync it before comparing. Also measured: 'cargo test --workspace' in the ci.yml rust job DOES build and test app/src-tauri, so the_typescript_the_ui_imports_is_the_one_these_commands_generate runs there — it is plain 'cargo test' (default-members) that skips the app crate.
