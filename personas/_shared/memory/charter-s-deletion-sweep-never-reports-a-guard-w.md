# A mutant killed by a crash is not evidence that the line's behaviour i

_2026-09-25 · persistent_

A mutant killed by a crash is not evidence that the line's behaviour is tested. When deleting a line (for example a binding that later lines read) makes the program raise or fail to build, the mutant dies on that error and a mutation tool scores it killed or unviable. The line's real behaviour can still be unpinned. Seen on charter PR 972 (hooks.py's delimiter unpack). So a green mutation run does not mean every behavioural line has a test. Cover such a line from the input side: find an input whose verdict differs when the line's value is computed the old or wrong way, and pin that. This is one of three ways a green mutation run can hide an untested guard, alongside scoring by exit code and masked-cluster survivors.
