# Recurring bug shape: a value computed once at startup (a global, a cac

_2026-09-25 · persistent_

Recurring bug shape: a value computed once at startup (a global, a cached config field) read where the current file on disk was meant, while another path reads the file. The two drift, and tests leak the real machine's value. Seen repeatedly in the retired Python charter (a worktree root resolved at import, one command reading a cached setting while another re-read charter.toml). Rule: if two paths answer the same question, they call the same function.
