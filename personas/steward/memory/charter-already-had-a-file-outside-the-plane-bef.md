# A machine-level charter file (not per plane) goes under $CHARTER_CONFI

_2026-09-25 · persistent_

A machine-level charter file (not per plane) goes under $CHARTER_CONFIG_HOME, then $XDG_CONFIG_HOME, then ~/.config, then charter/ (the ladder the Python charter used for publish consent since ADR 0003, and charter-app uses for extensions.json). Two reasons worth keeping: per-plane state is wrong for machine consent, because an operator with several planes would be asked repeatedly until the safeguard became a reflex; and CHARTER_CONFIG_HOME exists because gh keeps its auth under XDG_CONFIG_HOME, so redirecting XDG_CONFIG_HOME to isolate charter silently logs gh out. Take that ladder rung for rung rather than dirs::data_dir().
