# charter-app scenario tests on macOS CI: an IntersectionObserver-based me

_2026-09-22 02:47 · persistent_

charter-app scenario tests on macOS CI: an IntersectionObserver-based measurement cannot be trusted there. macOS gives a WKWebView no rendering while its window is covered, and IO notifications are delivered in the rendering step — so the FIRST delivery is the only one and it lands before layout settles. Measured 2026-09-21 on PR 139: the same commit reported 3 of 51 tabs visible on Linux (xvfb) and 0 of 49 on macOS. A scenario spec may assert that a measurement produced a count and that the UI followed it, never which elements are visible.
