# charter-app theme layer (PR for 'theme is data', 2026-09-22): vitest ret

_2026-09-22 11:19 · persistent_

charter-app theme layer (PR for 'theme is data', 2026-09-22): vitest returns an EMPTY STRING for a CSS file imported with import.meta.glob(..., {query:'?raw'}) — test.css is off by default, so a guard that scans stylesheets that way passes while checking nothing. Use import.meta.glob for the FILE LIST and node:fs readFileSync for the contents, and assert each file read is non-empty. Also: an exported function named 'use' trips eslint react-hooks/rules-of-hooks in React 19 (it reads any use() call as a hook and refuses it inside try/catch).
