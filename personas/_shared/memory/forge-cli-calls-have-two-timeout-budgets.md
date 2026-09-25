# Forge CLI calls (gh/glab) are bounded by two constants in crates/chart

_2026-08-21 23:18 · persistent_

Forge CLI calls (gh/glab) are bounded by two constants in crates/charter-core/src/forge.rs: STATUS_TIMEOUT = 10s for best-effort calls (auth checks, CI status) and LIST_TIMEOUT = 60s for strict, paging calls. The split is by the cost of being wrong, not by caller: a status failure costs a blank column, a strict failure aborts a whole discover. Pick the budget by that cost when adding a call.
