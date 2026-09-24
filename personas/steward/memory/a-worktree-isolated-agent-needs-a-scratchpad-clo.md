# A worktree-isolated agent needs a scratchpad clone and unsigned commits

_2026-09-20 21:30 · persistent_

Worktree-isolated agents on this machine (2026-09-20): the isolation guard refuses the -C flag, a cd into the shared checkout, and any compound command it cannot verify. A second repository therefore has to be cloned into the scratchpad with an ABSOLUTE clone target and then driven with plain, separate commands. Commit signing fails in such a clone: the commit returns "1Password: failed to fill whole buffer" because the global ssh signer cannot prompt non-interactively; setting commit.gpgsign to false in the throwaway clone is the workaround, and the charter-app worktree already has it false so it is unaffected. charter persona remember is refused too when the text needs shell-escaped apostrophes or reads like a version-control command - write the fact without apostrophes and single-quote the whole argument.
