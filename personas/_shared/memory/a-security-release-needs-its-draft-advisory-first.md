# Before cutting a release whose notes promise 'the security advisory pu

_2026-09-13 18:57 · persistent_

Before cutting a release whose notes promise 'the security advisory published with this release', check that a draft advisory exists (gh api repos/OWNER/REPO/security-advisories?state=draft) and put publishing it on the operator's checklist. When fix PRs are still landing, tell the operator to tag the release PR's merge commit, not main's head, or the tag ships code whose changelog entry stays unreleased.
