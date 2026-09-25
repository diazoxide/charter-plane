# A refusal proves nothing without a benign twin. Smoke-testing 0.48.0, 

_2026-08-22 12:28 · persistent_

A refusal proves nothing without a benign twin. Smoke-testing 0.48.0, three of six 'passes' were vacuous: the command errored on a wrong fixture shape, exited on argument parsing, or refused for an unrelated parse reason. For every refusal check, assert the precondition was actually met, that the error is the refusal sentence and not a usage error, and that files are byte-identical before and after; then run the legitimate twin and watch it succeed. For a widened listing, replay the old version against the same fixture for an A/B count.
