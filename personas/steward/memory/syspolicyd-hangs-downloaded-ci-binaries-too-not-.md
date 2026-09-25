# syspolicyd hangs downloaded CI binaries too, not just freshly linked one

_2026-09-20 17:37 · persistent_

When syspolicyd is pinned at ~100% CPU on this machine, it is not only freshly LINKED binaries that hang at _dyld_start — any binary the machine has not seen before does, including a CI-built .app downloaded from GitHub and even a plain cp of /bin/echo to a new path. So a release build from CI cannot be launched here either until syspolicyd is cleared (reboot). Diagnose with: sample <pid> 2 -mayDie (one frame, _dyld_start) and ps -Ao pcpu,pid,comm -r | head.
