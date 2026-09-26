# xterm.js 6.0.0 wheel (SI-4, PR diazoxide/charter#495): in mouse-tracking

_2026-09-26 20:57 · persistent_

xterm.js 6.0.0 wheel (SI-4, PR diazoxide/charter#495): in mouse-tracking mode consumeWheelEvent scales pixel deltas <50 by 0.3 and bindMouse sends ONE report per event (xtermjs/xterm.js#6181); the normal-buffer viewport (VS Code SmoothScrollableElement) ignores attachCustomWheelEventHandler entirely. charter's pane takes the wheel on the capture phase (app/src/wheel.ts) and hands xterm one DOM_DELTA_LINE event per row so xterm still encodes reports. JS-constructed WheelEvents in WKWebView have a legacy wheelDeltaY unlike native ones, so e2e 'before' numbers for xterm's own history path are not native-trackpad numbers.
