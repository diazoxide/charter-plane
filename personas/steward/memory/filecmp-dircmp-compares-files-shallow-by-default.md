# filecmp.dircmp compares files SHALLOW by default (stat signature: size+m

_2026-09-17 18:31 · persistent_

filecmp.dircmp compares files SHALLOW by default (stat signature: size+mtime), so a fixture-drift check built on it passes while contents differ — measured 2026-09-17: .charter/cache/repostate.json carried a different absolute temp path each run and dircmp called the trees equal. Use filecmp.cmp(a, b, shallow=False) per file; dircmp only gained a shallow= parameter in Python 3.13.
