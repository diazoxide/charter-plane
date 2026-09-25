# When a wide local test run fails a test that passes alone, rule out lo

_2026-09-25 · persistent_

When a wide local test run fails a test that passes alone, rule out load before suspecting the change: rerun the failing test alone and then in its original order with its neighbours on the same head. Timing-deadline tests flake under long sequential runs and a loaded machine (seen 2026-09-14 in the retired tmux suite: 3 failures in a wide run, green alone and in order). Separately, a pair of WIP checkpoint commits can be re-split into coherent commits with git reset <base>, then per-hunk git apply --cached of git diff -U3 <base> -- <file> split on @@; offsets across commits apply cleanly.
