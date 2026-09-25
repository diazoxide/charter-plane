# 'remote get-url origin' APPLIES url.<base>.insteadOf. charter-app's diff

_2026-09-20 10:06 · persistent_

'remote get-url origin' APPLIES url.<base>.insteadOf. charter-app's differential clone scenarios point github.com at a local bare repo that way, so a gl-refresh scenario built on them reads origin as file:///… and charter resolves no forge at all. Build the remote directly instead; gl-refresh never crosses a network.
