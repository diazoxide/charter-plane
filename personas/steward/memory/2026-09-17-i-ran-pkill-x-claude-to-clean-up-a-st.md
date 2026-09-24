# 2026-09-17: I ran 'pkill -x claude' to clean up a stuck corpus recording

_2026-09-17 20:59 · persistent_

2026-09-17: I ran 'pkill -x claude' to clean up a stuck corpus recording and killed another chat's harness (ide.4, panes %462 %475 dead). Kill-by-name matches every Claude Code process on the plane. Always kill the PID you spawned; for a pty recording drive it with python pty.fork() and signal that child.
