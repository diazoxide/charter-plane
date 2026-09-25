# Spawn gh/glab with stdin closed (Stdio::null() in charter-core forge.r

_2026-08-21 23:18 · persistent_

Spawn gh/glab with stdin closed (Stdio::null() in charter-core forge.rs). gh reads stdin when a field value names it, and an inherited stdin hung a CI-status refresh once (diazoxide/charter-plane #323/#324). Never 'simplify' a forge call back to inherited stdin; charter's only interactive paths replace the process rather than capture it.
