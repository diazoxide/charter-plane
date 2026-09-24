# A refusal test that asserts only the EXIT CODE can stay green over a r

_2026-09-25 · persistent_

A refusal test that asserts only the EXIT CODE can stay green over a real guard deletion, because two guards in sequence mask each other. Measured 2026-08-26 on a release workflow's version check: deleting the empty-version refusal still exited 1, because the mismatch check below it caught the empty string and gave a worse message. Same rc, different reason. So a refusal test (and a mutation run scoring it) must assert WHICH refusal fired, by its message or error variant, not just that something refused. Matching a symptom instead of a property is the shape behind most guard bypasses.
