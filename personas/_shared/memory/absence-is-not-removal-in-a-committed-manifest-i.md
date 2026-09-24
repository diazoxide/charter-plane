# Absence is not removal in a committed manifest. For #884 I specified a

_2026-09-25 · persistent_

Absence is not removal in a committed manifest. For #884 I specified an auto-reconcile of a workspace's recorded repos: 'a repo cloned into the workspace, or removed'. The add half is safe. The removal half would have destroyed teammates' data, and the agent refused it with evidence. A repo missing from this machine's disk does not mean it was removed: a machine may deliberately leave recorded repos uncloned, or be unable to reach some of them (partial access is normal). A reconcile keyed on absence would erase a teammate's restore target on first launch, and the next save would push the erasure. Manifest maintenance must be additive. Removal is an explicit operator action. General rule: before writing anything that deletes rows from committed shared state based on what is on this machine right now, ask what a machine that has fetched less than everything looks like.
