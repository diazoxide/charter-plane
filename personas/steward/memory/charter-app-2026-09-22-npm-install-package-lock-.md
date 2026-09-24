# charter-app (2026-09-22): 'npm install --package-lock-only' to add one d

_2026-09-22 22:38 · persistent_

charter-app (2026-09-22): 'npm install --package-lock-only' to add one dependency also REWRITES the bundled-dependency metadata for @tailwindcss/oxide-wasm32-wasi, pinning @emnapi/* at older versions than npm resolves — and then 'npm ci' refuses the lockfile on every CI job with 'Missing: @emnapi/core@... from lock file'. The churn is additive (no removals), which is why it looks harmless in review and is not. Fix: rebuild package-lock.json from the base branch's copy and insert by hand only the two hunks for the new package (the root dependencies line and the node_modules/<pkg> entry).
