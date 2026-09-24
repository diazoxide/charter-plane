# charter-app CSS, 2026-09-22: 'trees never wrap' needs TWO declarations a

_2026-09-22 22:50 · persistent_

charter-app CSS, 2026-09-22: 'trees never wrap' needs TWO declarations and they are not redundant in the same way. 'min-width: max-content' alone already stops a row folding (the box becomes as wide as the unwrapped name), so a test that only asks 'is this row one line' stays GREEN when you delete 'white-space: nowrap' — measured against the real WebView, both deletions passed. What each one alone loses: without min-width the name overflows its own box, so a hovered/current row's band stops at the region's edge while the text runs past it (assert el.scrollWidth - el.clientWidth == 0); without nowrap nothing visible changes today, so assert the resolved getComputedStyle().whiteSpace. Two assertions, one per declaration, or one of them ships unheld.
