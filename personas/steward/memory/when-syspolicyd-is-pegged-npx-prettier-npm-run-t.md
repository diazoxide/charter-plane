# When syspolicyd is pegged, 'npx prettier' / 'npm run typecheck' can hang

_2026-09-20 00:07 · persistent_

When syspolicyd is pegged, 'npx prettier' / 'npm run typecheck' can hang too: the stall is /usr/bin/env (npm's shebang shim) stuck at _dyld_start, not node. Call the tool through node directly and it runs: /usr/local/bin/node node_modules/prettier/bin/prettier.cjs --check e2e ; node node_modules/typescript/bin/tsc --noEmit -p e2e ; node node_modules/eslint/bin/eslint.js e2e. Symlink node_modules from the shared clone first, never copy it. (2026-09-20)
