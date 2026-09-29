# Saving workspace repos (operator ruling 2026-09-25, app ADR 0051 amended

_2026-09-29 17:56 · persistent_

Saving workspace repos (operator ruling 2026-09-25, app ADR 0051 amended, shipped in diazoxide/charter #404): the title-bar Save saves the PLANE only; charter never commits or pushes a workspace repo from a press that did not name it. 'Save all' lives only in the Saving tab behind a confirmation listing each repo, branch, what it takes and where it goes, and saves exactly that list. An unconfigured repo is 'off' until [repos.<name>] mode says how. Each repo row says where its Save goes (incl. where it stops short: no forge, no target, detached), in words matching reposave's steps: a PR save on the base/default branch commits there first, then pushes as charter/<ws>/…
