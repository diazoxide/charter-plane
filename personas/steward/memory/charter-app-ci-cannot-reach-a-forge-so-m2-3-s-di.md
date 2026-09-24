# charter-app CI cannot reach a forge, so tests that exercise forge code

_2026-09-25 · persistent_

charter-app CI cannot reach a forge, so tests that exercise forge code stand one in: bare repos behind a per-test HOME whose url.insteadOf rewrites the HTTPS base (charter still builds the real https URL and runs a real clone/push), plus a recorded gh stub script first on PATH. When comparing clones, ignore .git timestamps and inodes.
