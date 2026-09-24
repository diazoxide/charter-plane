# charter-app's 'scenario tests' CI job runs several wdio configs in seq

_2026-09-25 · persistent_

charter-app's 'scenario tests' CI job runs several wdio configs in sequence as separate steps (npm run e2e, e2e:state, e2e:finder, e2e:layout), so a failure in one means the later ones never ran. A red scenario job tells you nothing about the specs in the configs after the one that failed — and a spec that 'passed on the previous run' may simply never have been reached. Check which step failed before chasing a later spec.
