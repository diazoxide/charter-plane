# An IntersectionObserver threshold of exactly 1 is a real hazard (a whole

_2026-09-22 03:22 · persistent_

An IntersectionObserver threshold of exactly 1 is a real hazard (a whole element can measure 0.9999 off fractional rects) but it was NOT what made a macOS charter-app scenario run report 0 of 49 tabs visible: lowering it to 0.99 changed nothing. The cause was that the observer is answered in the browser's rendering step and macOS gives a WKWebView none while its window is covered, so the first delivery is the only one and it lands before layout settles. Measured 2026-09-21. The lesson that generalises: when a guard you added does not move the number, say so in the comment rather than leaving the guard claiming the fix.
