# syspolicyd un-wedged itself on 2026-09-21 without a reboot: old pid 461

_2026-09-21 08:43 · persistent_

syspolicyd un-wedged itself on 2026-09-21 without a reboot: old pid 461 (92 percent CPU for 13 days) is gone, replaced by a fresh pid at 0.1 percent, machine uptime unbroken at 14 days. Rust builds and RUNS locally again in charter-app - cargo fmt, clippy, test and a 200k-case differential all ran on this machine. Note the orchestrator's own Bash tool still SIGKILLs (exit 137) a copied binary while agents run Rust fine, so that kill is the tool sandbox and never was syspolicyd - do not read one as evidence about the other.
