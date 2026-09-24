# charter-app layer::readable_text (#112, PR 145): the right shape for a p

_2026-09-22 12:09 · persistent_

charter-app layer::readable_text (#112, PR 145): the right shape for a plane-file read that must still follow a link landing INSIDE the plane is resolve-both-ends-then-open-the-RESOLVED-path with contain::open_no_link. Pointing open_no_link at the unresolved name — which is what issue #112 literally prescribes — refuses every legitimately linked .claude/agents entry and diverges from the frozen Python oracle (contain._refused follows a contained link). Resolving first keeps the follow AND gives the kernel the same inode the gate judged, which closes ADR 0028's resolve-then-reread window.
