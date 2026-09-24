# A loaded machine turns a mutation run into no answer, not a green one.

_2026-09-25 · persistent_

A loaded machine turns a mutation run into no answer, not a green one. An agent ran the retired tools/sweep.py while the full test suite ran on the same machine and got 22 timeouts; the same tree on an idle machine reported 7 real survivors. The same applies to cargo-mutants: a TIMEOUT mutant is neither caught nor missed, and reading a pile of them as 'nothing survived' is a false green created by overloading the machine. Never run a mutation run at the same time as the suite or another heavy build. Treat more than a couple of timeouts as an invalid run to repeat, not as a result.
