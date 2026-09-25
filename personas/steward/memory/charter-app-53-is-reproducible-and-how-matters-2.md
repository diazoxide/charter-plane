# charter-app#53 IS reproducible, and how matters (2026-09-20, PR #105). p

_2026-09-20 21:47 · persistent_

charter-app#53 IS reproducible, and how matters (2026-09-20, PR #105). portable-pty 0.9.0's openpty window is only hit if the process spends a real share of wall-clock time inside it. A single-threaded loop of Session::spawn + 300 concurrent std::process::Command forks caught NOTHING on ubuntu-24.04 — Session::spawn is dominated by the program's own fork/exec, so one thread is inside the window ~1% of the time. Six opener threads, plus tying the forking loop to the opening loop so neither drifts, caught 5 held terminals out of 6 threads, each held the full 10 s. Rule of thumb for any narrow-window race test here: hits = (openings/second x window width) x (number of forks); raise the first factor with concurrency, not the second with more processes.
