# charter-app M5.5 (2026-09-21, PR 125): panels::root() resolved the plane

_2026-09-21 05:59 · persistent_

charter-app M5.5 (2026-09-21, PR 125): panels::root() resolved the plane from std::env::current_dir() — the singleton plane::resolve ADR 0034 removed — so workspace_panels/workspace_repos answered about whichever project the PROCESS started in, whatever the window showed. Already wrong once #121 let a window open a project the launch had not; visibly wrong with project tabs. Both take a PlaneId now, panels::root is gone, and current_dir() appears exactly ONCE in the app crate (setup, ADR 0034's first-launch hint). When auditing 'is every command told its plane', grep current_dir AND plane::resolve, not just the State<Planes> signatures.
