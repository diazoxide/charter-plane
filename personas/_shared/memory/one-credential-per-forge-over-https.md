# Every git operation on a workspace repo uses that repo's own forge's t

_2026-09-25 · persistent_

Every git operation on a workspace repo uses that repo's own forge's token over HTTPS: gh for GitHub, glab for GitLab. No SSH keys, no commit signing in the repos charter manages. charter-core's git policy (crates/charter-core/src/gitpolicy.rs, docs/git-policy.md) writes a credential helper and an insteadOf into each clone to make this true mechanically, and doctor reports drift. Never print a secret: read credentials from the persona's vault through charter, never reveal them, and never put one in memory or a committed config file.
