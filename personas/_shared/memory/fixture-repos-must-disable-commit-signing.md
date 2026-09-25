# Fixture git repos must set commit.gpgsign=false per repo (and pin user

_2026-08-22 17:23 · persistent_

Fixture git repos must set commit.gpgsign=false per repo (and pin user.name/user.email). On this machine commit.gpgsign=true with a 1Password signer makes the first fixture commit fail 'failed to write commit object', and a set -e script dies halfway so it looks like the tool doesn't work here. Never fix it by unsetting global config; the fixture must be self-contained. (In a worktree, pass -c commit.gpgsign=false per commit rather than git config.)
