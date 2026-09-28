# Claude Code 2.1.283: --resume <id> finds the conversation from ANY direc

_2026-09-28 16:33 · persistent_

Claude Code 2.1.283: --resume <id> finds the conversation from ANY directory (subdir, parent, unrelated) — cwd does not gate resume. An unknown id exits 1 in ~0.6 s ('No conversation found') with no model request and no SessionStart; Codex 0.147.0 'resume <id>' likewise exits 1 ('No saved session found'). Codex's default sandbox refuses connect() to charter's hook socket from tool commands (charter#517).
