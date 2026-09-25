# Display sigils differ by forge: GitLab merge requests render !123, Git

_2026-08-09 22:54 · persistent_

Display sigils differ by forge: GitLab merge requests render !123, GitHub pull requests #123. Old forge-cache entries (.charter/cache/glstate.json) carry no sigil and the render path defaults it; do not 'fix' that by writing one into old entries.
