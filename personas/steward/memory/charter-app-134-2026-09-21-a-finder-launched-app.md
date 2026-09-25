# charter-app#134 (2026-09-21): a Finder-launched .app gets PATH=/usr/bin:

_2026-09-21 23:36 · persistent_

charter-app#134 (2026-09-21): a Finder-launched .app gets PATH=/usr/bin:/bin:/usr/sbin:/sbin - launchd starts a GUI process and reads no login shell - so a bare program word in a built-in harness profile could not spawn, the wiring probe answered Unknown, and every chat was refused. Fixed in crates/charter-core/src/programs.rs: the process PATH first (strictly additive), then a fixed audited list of $HOME/.local/bin, bin, .opencode/bin, .bun/bin, .volta/bin, .npm-global/bin plus /opt/homebrew/bin, /usr/local/bin, /usr/bin, /bin. Asking a login shell for its PATH was rejected: it executes the operator's dotfiles to answer a lookup, and on macOS zsh a login non-interactive shell does NOT read .zshrc, which is where most PATHs are actually set.
