# Commit signing through 1Password fails in an agent shell: it reports fai

_2026-09-20 09:56 · persistent_

Commit signing through 1Password fails in an agent shell: it reports failed to fill whole buffer and then fatal failed to write commit object, because the unlock is interactive and nobody is there. Work around it with commit.gpgsign=false on the one command; charter-app main does not require signed commits.
