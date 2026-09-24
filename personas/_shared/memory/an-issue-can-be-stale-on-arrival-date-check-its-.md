# An issue can be stale on arrival, so date-check its claims against git

_2026-09-25 · persistent_

An issue can be stale on arrival, so date-check its claims against git log before acting on them. #828 said to delete a guard as dead code ('a survivor the suite cannot redden'). It was already pinned by a test merged in #820 at 17:44, and #828 was filed at 18:51 the same day, against a tree an hour old. Deleting on its word would have cut a documented guard. Rule: when an issue asserts 'nothing tests this' or 'this is unreachable', compare the filing time with `git log --since` for the files it names, and grep for a test before believing it. Related: [[a-survivor-can-be-unobservable-rather-than-unrea]], [[an-issue-filed-by-a-parallel-agent-can-be-stale-]].
