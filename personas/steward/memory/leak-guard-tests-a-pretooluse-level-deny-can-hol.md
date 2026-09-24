# Guard tests: a hook-level deny can hold for the wrong reason because a

_2026-09-25 · persistent_

Guard tests: a hook-level deny can hold for the wrong reason because a different gate also refuses the same command (e.g. a substitution gate). When the claim is about one guard (the vault/leak guard), assert that guard's own decision function directly, and prove it with a hand mutant; the hook-level form was shown blind in #1070 / PR #1083. Also recorded: a parser fallback that erases newlines produced both false denies and a real bypass (#1082, fixed) — any unparseable-command fallback must preserve line structure.
