# A fresh chat id is not a fresh chat name when names are ordinals that 

_2026-09-25 · persistent_

A fresh chat id is not a fresh chat name when names are ordinals that get reused. If numbering counts up from 1 and closing a chat frees its number, a reopened or new chat often gets the same name back ('steward 1' closes, 'steward 1' opens). Any state keyed on that name and stored outside the chat's own lifetime then leaks into a different conversation. The retired Python CLI hit this with per-session workspace pointers and locks (#731, #794). Two rules. (1) When an id can be recycled, minting a new one is not isolation; the isolating act is reaping the state keyed on the old one when it is freed. (2) Before calling a hazard marginal because the ids differ, check whether the id space is dense and reused. Reuse is usually the common case, not the edge.
