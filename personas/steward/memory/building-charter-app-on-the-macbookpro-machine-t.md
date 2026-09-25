# Building charter-app on the macbookpro machine: the Bash tool's PATH has

_2026-09-25 12:18 · persistent_

Building charter-app on the macbookpro machine: the Bash tool's PATH has no cargo/node. Prefix commands with: export PATH="$HOME/.cargo/bin:$HOME/.nvm/versions/node/v24.21.0/bin:$PATH". Rust stable was updated to 1.98.1 on 2026-09-25 (rustup self-update fails; use 'rustup update stable --no-self-update'). Node 24 installed via nvm alongside 22.
