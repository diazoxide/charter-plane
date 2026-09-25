# A differential budget (count syscalls/IO for few rows vs many) can pas

_2026-09-25 · persistent_

A differential budget (count syscalls/IO for few rows vs many) can pass or fail by test ORDERING when the warm-up call runs outside the instrumentation: the first call made under the instrument pays a once-per-process cost, so one measured window carries it and the comparison becomes cold-vs-warm instead of small-vs-large. Warm up a second time INSIDE the instrumentation and discard that call's counts. Also: if adding instrumentation turns the red run green without changing the behaviour under test, you cannot name the extra call; report it as unnamed rather than guessing. (Found 2026-09-16 on a retired Python charter test.)
