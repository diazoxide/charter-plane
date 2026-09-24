# Mutation-testing gotcha, charter PR 1098 round 6: a guard can be invisib

_2026-09-16 04:35 · persistent_

Mutation-testing gotcha, charter PR 1098 round 6: a guard can be invisible to a whole test module because the FIXTURE never reaches the line. Round 5 nested its too-deep JSON under a top-level key, so hooks.PreToolUse was absent, pre was empty, and the loop re-encoding each group never ran - the uncaught RecursionError in _ensure_guard_hook survived a 19-mutation hand replay and 4 green CI jobs. Two lessons: mutate the lines the sweep will mutate (lines the branch ADDS), not only the guards you wrote; and when a replay mutation reports NOT APPLIED after a refactor, re-point the anchor and re-run - a mutation that does not apply is not evidence of anything.
