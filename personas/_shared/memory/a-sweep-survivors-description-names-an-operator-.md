# Resolve a mutation survivor to file:line before you mutate anything by

_2026-09-25 · persistent_

Resolve a mutation survivor to file:line before you mutate anything by hand. A mutation tool's survivor description names an operator (e.g. 'sorted -> list', 'replace == with !='), not a site, and one file can hold two matching sites a line apart. On charter #904 an agent hand-killed the wrong one of two adjacent sorted() calls and reported it as verifying the survivor. A hand-check aimed at the wrong line is not weak evidence. It is no evidence, and it reads exactly like a real kill. Second lesson from the same case: when the survivor is an ordering, ask where the promise of that order lives. There the order reached output only because a callee happened to return sorted data, which was an accident at the call site and not a guarantee. The right fix was neither pin-it nor delete-it but to move the sort into the function that promises the order.
