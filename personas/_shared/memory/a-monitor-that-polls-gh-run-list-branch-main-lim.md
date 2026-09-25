# A monitor that polls "gh run list --branch main --limit 1" can report a

_2026-09-22 17:47 · persistent_

A monitor that polls "gh run list --branch main --limit 1" can report a STALE run as the answer: on 2026-09-22 one reported run 35537671563 completed success for a merge whose real run (35732990933) was still in progress. Right after a merge the new run may not be listed yet, so limit-1 returns the previous completed one and the until-loop exits on it. Key a CI watch on the SPECIFIC run id (gh run view <id>), or match the headSha, never on "the latest run".
