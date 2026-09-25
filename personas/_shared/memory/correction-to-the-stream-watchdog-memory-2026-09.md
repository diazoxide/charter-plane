# CORRECTION to the stream-watchdog memory (2026-09-11): 'split loops in

_2026-09-25 · persistent_

CORRECTION to the stream-watchdog memory (2026-09-11): 'split loops into chunks of at most 10 iterations per call' is wrong for sleep polling. The watchdog kills a subagent when ONE tool call makes no progress for 600 s, and 10 iterations of sleep 60 in one call is exactly 600 s; an implementer stalled twice that way. The rule that holds: no single tool call may exceed about 4 minutes of wall-clock time. Long runs (a full cargo test or e2e run, a mutation run, CI) go to run_in_background writing to a file, and each poll is one call of at most one sleep 60 plus one tail or gh read (or use Monitor). Never wait on a background job inside a call, and never loop sleeps inside a call.
