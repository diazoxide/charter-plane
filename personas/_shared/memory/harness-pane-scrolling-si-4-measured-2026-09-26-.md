# Harness pane scrolling (SI-4, measured 2026-09-26): Claude Code under th

_2026-09-26 20:07 · persistent_

Harness pane scrolling (SI-4, measured 2026-09-26): Claude Code under the operator's ~/.claude/settings.json "tui": "fullscreen" (and opencode 1.18.23) run in the alternate screen with SGR mouse tracking (?1049h ?1000h ?1002h ?1003h ?1006h), so xterm.js 6 turns each wheel event into ONE mouse report and the harness scrolls itself — xterm's smoothScrollDuration/scrollSensitivity cannot make it smooth. With --settings '{"tui":"default"}' Claude stays in the normal buffer (xterm scrollback). codex 0.147 is inline, normal buffer.
