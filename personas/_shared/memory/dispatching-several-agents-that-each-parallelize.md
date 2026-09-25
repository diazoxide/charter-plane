# Dispatching several agents that each parallelize their own heavy runs 

_2026-09-25 · persistent_

Dispatching several agents that each parallelize their own heavy runs (full test suites, mutation runs, cargo builds) oversubscribes the machine: 2026-08-27 hit load 152 on 14 cores with 17 concurrent full-suite runs. It was CPU thrashing, not memory danger; the runs finished, just far slower than serial. Agents self-throttle if told the machine is loaded. When dispatching more than one agent whose brief includes a heavy test or mutation run, tell each one the others exist and not to raise concurrency to compensate. For cargo, also mind disk: each agent worktree grows its own target/.
