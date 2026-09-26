# Codex 0.147.0 has no per-session skills root: it scans only $CODEX_HOME/

_2026-09-27 00:37 · persistent_

Codex 0.147.0 has no per-session skills root: it scans only $CODEX_HOME/skills, ~/.agents/skills, trusted .codex/skills, /etc/codex/skills, repo .agents/skills and plugins; -c adds none. charter's fallback lists its skills in the session-start briefing via CHARTER_SKILLS_DIR (PR #502, ADR 0063).
