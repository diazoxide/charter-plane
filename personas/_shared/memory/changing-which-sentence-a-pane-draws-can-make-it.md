# When a change alters which branch a caller reaches, the tests that go 

_2026-09-25 · persistent_

When a change alters which branch a caller reaches, the tests that go vacuous are the ones for branches it no longer reaches. They are not in your diff, and no tool reports them. On charter #752 a new guard made two helpers reachable only with a valid name, which made their sanitising half unreachable. Their docstrings still argued for it, and the two hostile-name tests aimed at them would have kept passing while asserting nothing. It was caught only because the author grepped for tests of the adjacent lines rather than the changed one. Fix: retarget those tests at the branch that is now reachable, and add a bound that keeps the property observable. Also from that PR: a 'swap-synonym' mutation (.strip -> .lstrip, trim -> trim_start) found a real defect, not noise, because two readers of the same value trimmed it differently.
