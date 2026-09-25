# Any test that launches a program with the caller's environment cannot se

_2026-09-21 23:36 · persistent_

Any test that launches a program with the caller's environment cannot see a PATH-shaped defect. charter-app#134 was invisible for a month because CI, every scenario run and every agent started the app from a shell. The two levers that make it testable: a Rust test that spawns the real binary with env_clear() plus a temp HOME (unsafe_code=forbid rules out set_var, so it must be a child process), and @wdio/tauri-service, whose env option is spread as {...process.env, ...options.env} - so a wdio config CAN hand the app under test a minimal PATH and a HOME of its own.
