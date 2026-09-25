# A remote URL read back by charter has already had url.<base>.insteadOf a

_2026-09-20 18:22 · persistent_

A remote URL read back by charter has already had url.<base>.insteadOf applied. A differential or forge test that keys the rewrite on the URL actually in .git/config hands charter a file:// remote, charter answers 'no forge I know', nothing is pushed, and both implementations agree perfectly — green over a code path neither entered. Key the rewrite on the HTTPS base and leave the remote in SSH form. worktree::git's env_clear() does NOT protect against it: insteadOf arrives through config, and HOME is deliberately passed to every child, so ~/.gitconfig reaches every call.
