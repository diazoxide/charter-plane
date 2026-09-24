# GitHub branch protection: enforce_admins=false does NOT cover force-pu

_2026-08-30 11:02 · persistent_

GitHub branch protection: enforce_admins=false does NOT cover force-push. Creating protection sets allow_force_pushes=false by default, and an admin's 'git push --force' is then rejected GH006 'Cannot force-push to this branch' — unlike a normal push, which bypasses. Set allow_force_pushes=true explicitly to keep the owner's recovery path. allow_deletions=false is separate and worth keeping. Measured 2026-08-30.
