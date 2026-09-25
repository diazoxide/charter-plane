# The forge-state refresh lock carries two facts: its content is the pid

_2026-08-21 23:18 · persistent_

The forge-state refresh lock carries two facts: its content is the pid of the in-flight refresh (empty when none), its mtime is when that last changed. glstate::maybe_spawn suppresses while that pid is alive, glrefresh's mark_done restarts the cooldown at completion rather than spawn, and STUCK_AFTER = 900s replaces a presumed-wedged refresh so a recycled pid cannot suppress forever. Do not simplify it back to touching the lock after spawning; that was diazoxide/charter-plane #324.
