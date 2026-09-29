# Repos and releases (operator rulings 2026-09-25/26, app ADR 0056): diazo

_2026-09-29 17:56 · persistent_

Repos and releases (operator rulings 2026-09-25/26, app ADR 0056): diazoxide/charter is the app, diazoxide/charter-plane is the plane. Never create a repo named charter-app — installed builds reach their updater through its redirect. Release signing secrets live only in the protected 'release' GitHub environment (branch main + tag v*); repo-level copies were deleted. The updater key must NEVER be regenerated: installed apps trust only its public key.
