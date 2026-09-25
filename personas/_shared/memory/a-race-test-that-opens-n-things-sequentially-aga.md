# A race test that opens N things sequentially against N forks catches NOT

_2026-09-20 22:04 · persistent_

A race test that opens N things sequentially against N forks catches NOTHING, and goes green against a real bug. What decides a hit is the SHARE OF WALL-CLOCK TIME some vulnerable window is open, not the number of attempts - and in charter-app's Session::spawn the fork+exec of the program itself dominates, so one opener thread sits inside openpty's window about 1% of its life. Measured on charter-app#105/#53: 250 sequential opens against 300 forks was all green; SIX opener threads, plus tying the forking loop to the opening loop so they cannot drift apart, caught five held terminals. When writing any race test, compute the duty cycle of the window first and raise concurrency until it is a real fraction - and state in the PR that the parameters are tuned to a runner and nobody has established the margin.
