# Using the environment as a FALLBACK for an id the payload should carry c

_2026-09-18 15:19 · persistent_

Using the environment as a FALLBACK for an id the payload should carry can invert a nesting guard rather than merely weaken it (charter-app M1.3, 2026-09-18). CLAUDE_CODE_SESSION_ID holds the OUTER chat's id for a harness nested in that chat's shell, so 'payload or env' substitutes the wrong id when the payload is slow, and the nested report is then accepted as the outer chat's. Python has always required payload == env (AND). But the first correction over-shot: refusing every unreadable id also dropped the honest harness's own reports when charter's read deadline fired. 'I could not tell' and 'someone is lying' are different evidence and need different answers.
