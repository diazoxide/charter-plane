# charter-app: 'cargo test' does NOT compile or run the app crate — charte

_2026-09-18 17:19 · persistent_

charter-app: 'cargo test' does NOT compile or run the app crate — charter-app is a workspace member but not in default-members, so only 'cargo test --workspace' reaches app/src-tauri. Same for clippy: 'cargo clippy --all-targets' misses it and 'cargo clippy --workspace --all-targets' catches it. CI uses --workspace, so the local loop is the one that lies: tests you add under app/src-tauri appear to pass by not running, and dead code there is only reported by CI. Cost me two cycles in M1.3 (2026-09-18).

**2026-09-23 — say WHICH invocation, because the short version misleads.** This note has been
relayed into agent briefs as "cargo test does not compile the app crate", and an agent read that
as "the app crate cannot be tested locally" and reported the opposite as a contradiction. Both
of these reach `app/src-tauri` and work on this machine:

    cargo test --workspace          # what CI runs
    cargo test -p charter-app       # ~55 s cold, 172 lib tests pass

Only the **bare** `cargo test` misses it, and only because charter-app is a workspace member
that is not in `default-members`. The same holds for clippy. What is genuinely CI's alone is
the `tauri build` job on each platform, not the app crate's tests. Brief agents with the
invocation, never with the blanket sentence — `cargo test -p charter-app -- --ignored` is also
how `bindings.ts` is regenerated, so an agent who believes the app crate is untestable locally
will also believe it cannot regenerate the bindings, which is the more expensive mistake.
