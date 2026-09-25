# charter-app local tooling on this machine (2026-09-21): cargo is at /o

_2026-09-25 · persistent_

charter-app local tooling on this machine (2026-09-21): cargo is at /opt/homebrew/opt/rustup/bin, NOT ~/.cargo/bin and not on the default PATH. Two crates/stand-in tests fail on this macOS and on main alike — the kernel no longer answers ETXTBSY for a held descriptor, and a cp-copied binary is SIGKILLed — and two forklock timing tests flake under load and pass in isolation. Check main before believing either is your regression.
