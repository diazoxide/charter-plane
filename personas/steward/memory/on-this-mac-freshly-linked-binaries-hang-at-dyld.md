# On this Mac, freshly linked binaries hang at _dyld_start because /usr/li

_2026-09-19 23:49 · persistent_

On this Mac, freshly linked binaries hang at _dyld_start because /usr/libexec/syspolicyd is pegged at 100% CPU (first-launch assessment). That, not free memory, is why cargo 'cannot build': build-script-build processes and even a 1-line C program (cc, ad-hoc codesigned or not) sit in dyld indefinitely. Existing binaries (python3, rustfmt, /bin/sh, ps) run fine, so rustfmt works standalone but cargo test/build never will. Check with: ps -eo pid,%cpu,comm | grep syspolicyd; sample <pid> shows _dyld_start. Verify charter-app Rust changes in CI. (2026-09-19)
