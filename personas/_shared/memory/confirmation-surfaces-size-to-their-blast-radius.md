# Confirmation surfaces size themselves to their blast radius: closing o

_2026-09-07 20:08 · persistent_

Confirmation surfaces size themselves to their blast radius: closing one chat is a small inline confirm, quitting the app takes the whole surface, and destructive options sit last. Decide it in one place from the action itself, not per call site. Pin both directions in tests (small stays small, big stays big) or the unpinned one drifts silently.
