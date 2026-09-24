# xterm.js skips any render that falls while a synchronized update (?2026)

_2026-09-17 23:24 · persistent_

xterm.js skips any render that falls while a synchronized update (?2026) is open and forces one only on a 1-second safety timeout (RenderService._renderRows / SynchronizedOutputHandler). Consequences measured in charter-app M0.6 (2026-09-17, M4 Pro): output that ENDS inside an open update makes a pane draw once a second — 'fake-harness --synthetic N' did exactly that by truncating at N bytes, so every scenario test's pane was in that state until it was fixed to close the update. But a repaint merely ARRIVING split is harmless: every repaint does arrive split (a pseudo-terminal hands over about 1 KB per message, so a 3 KB repaint arrives in ~4), and those parse back to back before the next frame — 51.8 draws/s. What stalls it to 1.0 draws/s is the writer PAUSING (~16 ms) while the update is open.
