# Running only the tests for the files you touched is not enough before 

_2026-09-25 · persistent_

Running only the tests for the files you touched is not enough before claiming green. Grep the changed SYMBOLS (functions, types, strings a test asserts on) across the test tree and run every test that mentions any moved surface, not just the modules next to the changed files. In the retired Python suite (2026-09-17) CI caught this twice: existing tests used a changed action as a stand-in for 'something that spawns', and another asserted a UI field's position that a new field displaced; none mentioned a changed symbol by file. Tree-wide guards (prose/claims checks, inventories) also fail on changes their own module never names, so run them after any doc-comment edit.
