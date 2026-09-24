# A local clone can be several commits behind origin/main. Before verify

_2026-09-10 17:28 · persistent_

A local clone can be several commits behind origin/main. Before verifying a claim that something is 'still true on main', git fetch origin main and read with 'git show origin/main:<path>' rather than trusting the checked-out tree.
