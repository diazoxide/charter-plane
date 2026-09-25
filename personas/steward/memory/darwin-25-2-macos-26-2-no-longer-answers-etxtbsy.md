# Darwin 25.2 (macOS 26.2) no longer answers ETXTBSY in either direction:

_2026-09-23 03:36 · persistent_

Darwin 25.2 (macOS 26.2) no longer answers ETXTBSY in either direction: a #! script whose inode another process holds open for writing execs and runs, and a running Mach-O can be truncated. The refusal moved, it did not go away — a Mach-O the kernel has already validated once is SIGKILLed when re-exec'd while somebody holds it open for writing (12/12), while one never exec'd runs (12/12). Also: every executable macOS ships is x86_64+arm64e, arm64e runs only as an Apple platform binary, so a copy of /bin/echo is SIGKILLed with nothing holding it open and an ad-hoc re-sign does not save it. Measured for charter-app#184.
