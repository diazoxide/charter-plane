# charter statusline IS Claude Code's statusLine command — one line, one o

_2026-09-20 19:52 · persistent_

charter statusline IS Claude Code's statusLine command — one line, one occupant (verified 2026-09-20 against ADR 0019's own consequences: 'a framed Claude Code session has no context/cache gauge on ANY surface'). When charter prints an empty line there, Claude Code does NOT fall back to a footer of its own: the ctx%/cache% an operator loses are charter's own zone 3 (crates/charter-core/src/footer.rs draws the three zones). So 'charter blanks the harness's footer' is a mis-framing that will keep coming back — the real choice in a charter-app pane is charter's footer or nothing. ADR 0029 (charter#1153) records it.
