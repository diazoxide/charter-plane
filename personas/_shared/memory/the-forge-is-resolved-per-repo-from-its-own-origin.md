# The forge is resolved per repo from that repo's own origin (charter-co

_2026-08-09 22:54 · persistent_

The forge is resolved per repo from that repo's own origin (charter-core forge::resolve_host), not from the plane's first [[forge]] block. A workspace can hold repos from different forges side by side, and a self-hosted host declared in charter.toml is recognised too. Never assume the plane's first forge applies to a given repo.
