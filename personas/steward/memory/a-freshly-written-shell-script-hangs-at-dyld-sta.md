# While syspolicyd is wedged on this machine, a freshly written shell sc

_2026-09-25 · persistent_

While syspolicyd is wedged on this machine, a freshly written shell script hangs at _dyld_start exactly as a freshly built binary does: it is Gatekeeper assessment, not Rust or the script. So a new stub script (for example a recorded gh stand-in on PATH in a test) cannot be exercised locally during a wedge; write it and let CI run it, or get the operator to restart syspolicyd.
