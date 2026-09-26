# charter-app: 'npm install <pkg>' in app/ prunes the optional @emnapi / o

_2026-09-26 20:36 · persistent_

charter-app: 'npm install <pkg>' in app/ prunes the optional @emnapi / oxide-wasm32-wasi entries from package-lock.json, which can break npm ci on another platform. Add a dependency by running npm install into a scratch copy, then merging only the new node_modules/<pkg> entries into main's lock without reordering keys (SI-6, 2026-09-26).
