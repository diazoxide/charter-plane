# macOS gives a WKWebView NO paints when its window is covered, the displa

_2026-09-17 23:24 · persistent_

macOS gives a WKWebView NO paints when its window is covered, the display is asleep, or the screen is LOCKED: no requestAnimationFrame, no xterm.js render. A GUI benchmark or e2e test that waits for a paint then hangs or reports 0 fps is usually this, not the app. Measured in charter-app M0.6 (2026-09-17): three separate runs died this way. Fixes that worked: bring the window to the front by pid (osascript 'set frontmost of (first process whose unix id is N)'), hold the display awake for the run's lifetime ('caffeinate -d -i -u -w <pid>' — and 'caffeinate -u' DOES turn an off display back on (man caffeinate: "If the display is off, this option turns the display on"), verified 2026-09-18 when a bench run that had failed with zero frames ran at a full 60 fps after 'caffeinate -u -t 3'), and refuse to start when 'ioreg -n Root -d1 -r -a' contains CGSSessionScreenIsLocked.
