# Shift+Enter newline for harnesses: ESC CR (\x1b\r) inserts a newline wit

_2026-09-26 20:07 · persistent_

Shift+Enter newline for harnesses: ESC CR (\x1b\r) inserts a newline without submitting in Claude Code 2.1.283, codex-cli 0.147.0 and opencode 1.18.23 (measured in a PTY with a pyte probe, 2026-09-26); xterm.js 6 sends bare CR for Shift+Enter. Modelled as charter_core::harness::Harness::newline (charter PR #490).
