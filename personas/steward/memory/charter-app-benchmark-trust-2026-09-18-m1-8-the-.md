# charter-app benchmark trust (2026-09-18, M1.8): the 13 MB burst arm in e

_2026-09-18 08:35 · persistent_

charter-app benchmark trust (2026-09-18, M1.8): the 13 MB burst arm in e2e/bench/burst.bench.ts has a run-to-run spread wider than most changes worth measuring — webgl read 22.3, 30.1 and 25.9 MB/s on three runs of the same build against ADR 0026's 28.4, at 41-48 fps each time (the low fps is the burst saturating the renderer, not the display idling). Do not read a single burst number as a regression or an improvement. What IS stable: the ?2026 draw-rate arms at 51-53 draws/s with framesPerSecond 60 beside them, and a core-only measurement (feed the corpus through a Session with a view attached and time it) at 93-105 MB/s, which must be INTERLEAVED with main because an evening of benchmarking warms the machine enough to move it 4% and swap sides on the next round.
