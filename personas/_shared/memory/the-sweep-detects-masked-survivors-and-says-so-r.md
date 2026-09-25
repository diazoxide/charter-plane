# Two guards in sequence can MASK each other in mutation testing: each l

_2026-09-25 · persistent_

Two guards in sequence can MASK each other in mutation testing: each looks equivalent alone, so neither gets pinned. Worked examples from #822: a file-existence check returned before a return-code guard, so the only state that made git exit non-zero never reached git and dropping the guard changed nothing; and two conjuncts ('ends with ")"' and 'contains " ("') each mattered only for an input no fixture had. Rule: when two survivors sit in one function, do not pin them one at a time. Find the state that reaches the SECOND guard with the first satisfied, then drop each guard separately and check exactly which test goes red.
