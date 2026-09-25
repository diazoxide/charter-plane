# Measured 2026-09-15 (auto-wire, ruling 47): claude 2.1.272 'plugin marke

_2026-09-15 13:22 · persistent_

Measured 2026-09-15 (auto-wire, ruling 47): claude 2.1.272 'plugin marketplace add diazoxide/charter' into an EMPTY throwaway CLAUDE_CONFIG_DIR is a git clone from GitHub — 7 s and 18 s across two same-day runs, network-paced, no login (no .credentials.json, no oauthAccount, no API key in env); 'plugin install' 0.8-1.3 s; the probe after 150 ms. Two add+install sequences at once into one empty folder: both exit 0, one 'installed' one 'already installed', both manifests parse with one entry — clean but one sample, hence wiring._serialised's flock under .charter/locks/. opencode shim: 4 files, 35 ms, no subprocess; opencode's first 'debug config' in a fresh XDG home 8 s, then 0.45 s.
