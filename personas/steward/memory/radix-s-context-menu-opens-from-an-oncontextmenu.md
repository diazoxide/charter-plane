# Radix's context menu opens from an onContextMenu composed with composeEv

_2026-09-22 22:20 · persistent_

Radix's context menu opens from an onContextMenu composed with composeEventHandlers, which SKIPS its own handler when the event is already defaultPrevented. React 19 attaches delegated listeners to the root container, which is below window — so a global 'suppress the WebView's own context menu' listener must be on the BUBBLE phase. A capturing one on window runs first, prevents the default, and silently stops every Radix ContextMenu in the app from ever opening. Measured while building charter-app's context menus (PR #172, 2026-09-22).
