# charter-app's app/src/bindings.ts CAN be hand-edited correctly when Rust

_2026-09-20 19:38 · persistent_

charter-app's app/src/bindings.ts CAN be hand-edited correctly when Rust will not run locally (2026-09-20, PR 91, CI green): tauri-specta 2.0.0-rc.25 (~/.cargo/registry/.../tauri-specta-2.0.0-rc.25/src/lang/js_ts.rs) applies heck's to_lower_camel_case to BOTH the TypeScript argument name and the __TAURI_INVOKE object key, and specta-typescript-0.0.12 primitives.rs::js_doc renders a doc block as ' * ' + each raw /// line verbatim (a bare /// becomes ' * ' with a trailing space). The guard is 'cargo test --workspace' -> the_typescript_the_ui_imports_is_the_one_these_commands_generate in app/src-tauri/src/lib.rs. Also: adding an 8th argument to a #[tauri::command] trips clippy::too_many_arguments (threshold 7); #[allow] placed after #[specta::specta] and before fn survives both macros.
