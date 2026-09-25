# A harness's environment is inherited by every shell its model's tools 

_2026-09-25 · persistent_

A harness's environment is inherited by every shell its model's tools start, so an environment variable set for a chat session (a session id, a pane or terminal id, a CHARTER_* variable) never proves that a process IS that session's harness. A charter command the model runs from its Bash tool passes any check that only reads those variables. To prove a process is the one charter launched, compare its PID (or parent chain) with the PID charter recorded when it spawned the harness, before acting. Treat such a check as a guard rail only: a process that fakes the whole setup still passes. First measured 2026-09-11 in the retired tmux frame, where the tool shell saw the harness pane's TMUX_PANE.
