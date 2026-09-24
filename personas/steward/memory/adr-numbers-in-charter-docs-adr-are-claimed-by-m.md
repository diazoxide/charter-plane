# ADR numbers are claimed by MERGE order, not branch order, and nothing 

_2026-09-25 · persistent_

ADR numbers are claimed by MERGE order, not branch order, and nothing reserves one. charter's design record now lives in charter-app/docs/adr (ADR 0044); with several agents on charter-app at once, a long-open PR gets scooped and a renumber has to move the file plus every reference. Pick the number as late as possible: list the REMOTE right before pushing (gh api repos/diazoxide/charter-app/contents/docs/adr) and check open PRs (gh pr list --repo diazoxide/charter-app) since an open PR can hold one too, then re-check immediately before merge.
