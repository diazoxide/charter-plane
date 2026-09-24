# WHEN A MUTATION CANNOT BE MEASURED, MOVE THE CODE; DO NOT LOWER THE ST

_2026-09-25 · persistent_

WHEN A MUTATION CANNOT BE MEASURED, MOVE THE CODE; DO NOT LOWER THE STANDARD. On #923/#926 a mutation landed in a config module whose covering set was the whole suite, so every run timed out and gave no verdict. The agent neither merged on a hand measurement nor declared it unkillable: it moved the helper into the module that owns that state, whose covering set was small, and the mutation was then measured and killed. The move was also the better design on the repo's own precedent (each module spells its own state path). The deliberate cost: a named constant pins a literal for free and a function does not, so it added a test pinning the literal the operator sees. General rule: a line nothing can isolate is a line every test depends on, and it is usually in the wrong place.
