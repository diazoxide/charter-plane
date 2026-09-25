# A credentialed git pull cannot be exercised against a local stand-in f

_2026-09-25 · persistent_

A credentialed git pull cannot be exercised against a local stand-in forge. Measured on git 2.50.1: `git remote get-url origin` APPLIES url.<x>.insteadOf, while `git config remote.origin.url` does not. charter-app's gitpolicy::forge_for reads get-url, so any rewrite that sends the fetch to file:// also makes the origin a host charter cannot place, and restore answers "origin host isn't a known/declared forge — skipped". Forge resolution and a local transfer are mutually exclusive by construction. Cover the pull's wiring with a Rust unit test over a file:// bare remote instead — protocol.file is deliberately not banned by worktree::git::NETWORK_RULE, because it reaches no network and asks for no credential.
