# Shell-tab PATH shims (charter ADR 0062): a PATH handed to an interactive

_2026-09-26 20:43 · persistent_

Shell-tab PATH shims (charter ADR 0062): a PATH handed to an interactive shell is only where it starts — the operator's ~/.zshrc prepends ~/.local/bin and ~/.opencode/bin (measured 2026-09-26), so anything that must stay first on a shell tab's PATH has to be re-asserted after the user's rc: zsh via a charter ZDOTDIR whose files source the user's and hand ZDOTDIR back, bash via --rcfile. Same technique as VS Code shell integration.
