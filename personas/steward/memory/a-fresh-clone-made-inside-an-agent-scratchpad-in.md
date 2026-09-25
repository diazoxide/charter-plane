# A fresh clone made inside an agent scratchpad inherits the operator glob

_2026-09-20 19:14 · persistent_

A fresh clone made inside an agent scratchpad inherits the operator global gpg.program (1Password op-ssh-sign), and every commit then dies with '1Password: failed to fill whole buffer / fatal: failed to write commit object' because the agent has no path to the 1Password agent socket. Fix per clone: set commit.gpgsign to false. charter-app main has required_signatures false, so an unsigned commit merges. Hit 2026-09-20 on charter-app PR 87.
