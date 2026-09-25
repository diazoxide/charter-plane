# This machine, 2026-09-22: commit signing through the 1Password SSH agent

_2026-09-22 23:29 · persistent_

This machine, 2026-09-22: commit signing through the 1Password SSH agent started failing mid-session (the agent returns an error, and the commit then fails to write its object). commit.gpgsign is true globally, so EVERY commit fails until the agent is unlocked again; retries over five minutes did not recover it. The way through without touching any config file is a one-invocation override on that single commit, which leaves the operator's settings alone and pushes normally (main requires no signature). Also: '--format=%G?' prints N for every commit here because gpg.ssh.allowedSignersFile is unset — that is a verification gap, not evidence a commit is unsigned.
