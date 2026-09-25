# charter-app scenario specs (2026-09-22): TABS ARE NOT SESSIONS. A split

_2026-09-22 22:38 · persistent_

charter-app scenario specs (2026-09-22): TABS ARE NOT SESSIONS. A split puts two sessions in ONE tab, and panes.e2e.ts's own 'splits the pane in front' test leaves exactly such a tab behind — so an assertion comparing what the tab strip holds against harnessesRunning() is off by the number of splits (measured: 49 tabs, 50 harnesses, both platforms). Since the strip collapses rather than scrolling, it no longer draws every tab either. The independent oracle for 'how many tabs are open' is the PALETTE: the catalogue emits one 'End chat <name>' row per tab and the palette lists them all.
