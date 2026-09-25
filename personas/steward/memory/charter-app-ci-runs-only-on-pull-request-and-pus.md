# charter-app CI runs only on pull_request and pushes to main, so a probe

_2026-09-20 18:15 · persistent_

charter-app CI runs only on pull_request and pushes to main, so a probe branch pushed on its own gets no run at all. To prove a mutation there, commit it on the PR branch marked PROOF ONLY, read the run, then push a revert.
