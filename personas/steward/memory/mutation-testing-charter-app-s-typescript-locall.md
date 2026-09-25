# Mutation-testing charter-app's TypeScript locally: COMMIT first. The res

_2026-09-21 10:44 · persistent_

Mutation-testing charter-app's TypeScript locally: COMMIT first. The restore step is a checkout of app/src, which silently throws away uncommitted test edits along with the mutation — lost a freshly written test that way on 2026-09-21. And a mutation must still typecheck: an unused parameter or setter trips TS6133 and proves nothing, so keep it used (void it, or make the branch trivially true).
