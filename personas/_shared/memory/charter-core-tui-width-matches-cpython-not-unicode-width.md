# charter_core::tui's width measures East-Asian width and combining mark

_2026-09-20 17:20 · persistent_

charter_core::tui's width measures East-Asian width and combining marks with tables generated from CPython's unicodedata (charter-app tools/gen-unicode-tables.py). The unicode-width crate deviates on purpose (emoji presentation, default-ignorables) and must not replace it where byte-exact width matters.
