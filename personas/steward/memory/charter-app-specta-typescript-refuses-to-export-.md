# charter-app: specta-typescript REFUSES to export u64/i64/usize/isize/u12

_2026-09-21 03:37 · persistent_

charter-app: specta-typescript REFUSES to export u64/i64/usize/isize/u128/i128 outright — a field of that type in a #[derive(specta::Type)] struct makes commands.export() return Err, and lib.rs's debug-build .expect("the TypeScript bindings are written") turns that into a panic at startup (exit 101). The scenario tests then fail in onPrepare with only 'the app likely crashed during startup'; the real message is in the panic log artifact (scenario-logs-<os>/panics.log, written by panics::record before the expect). Carry a timestamp as a number only if it fits JavaScript's own limit, or leave it out. Found 2026-09-21 on PR #121 with RecentPlane.opened: u64.
