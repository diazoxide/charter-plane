# In width-critical monospace cells use East-Asian Neutral glyphs: U+25A

_2026-08-09 22:54 · persistent_

In width-critical monospace cells use East-Asian Neutral glyphs: U+25AA, U+25B8, U+25AB are Neutral. Ambiguous-width glyphs (U+25C8, U+25C6, U+25CB, U+2302, U+00D7) are drawn two cells wide by some fonts and shipped misaligned twice. Alignment breaks on width that differs between rows, not on width itself; a glyph on only one row (a header) is the worst case because nothing else exercises it. If a new glyph is needed, reuse one already measured rather than picking a fresh one.
