# charter-app (Rust core, diazoxide/charter-app, 2026-09-17): portable-pty

_2026-09-17 17:24 · persistent_

charter-app (Rust core, diazoxide/charter-app, 2026-09-17): portable-pty 0.9 has traps a session wrapper must handle itself. (1) CommandBuilder silently falls back to $HOME when cwd is missing or not a dir (cmdbuilder.rs ~501). (2) Child::kill SIGHUPs only the direct pid and always sleeps 50 ms. Programs are setsid leaders, so kill the process group (rustix kill_process_group) and reap off the UI thread. On Linux a surviving grandchild keeps the PTY open and leaks the reader thread. (3) ExitStatus::exit_code() is 1 for signal deaths; check signal(). alacritty_terminal 0.26 panics on 0-column grids (floor at 2x1) and emits ColorRequest/TextAreaSizeRequest events that must be answered, not only PtyWrite. A blocking reply write on the reader thread deadlocks under a query flood; use a writer thread with a bounded queue.
