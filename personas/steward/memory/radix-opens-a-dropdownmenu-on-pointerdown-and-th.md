# Radix opens a DropdownMenu on pointerdown, and the WebView WebdriverIO d

_2026-09-22 02:47 · persistent_

Radix opens a DropdownMenu on pointerdown, and the WebView WebdriverIO drives in charter-app answers a click with no pointer event at all — the scenario run reported '0 menus opened' on both macOS and Linux (2026-09-21, PR 139). The fix that works: hold the open state yourself, preventDefault the trigger's onPointerDown (composeEventHandlers skips Radix's own handler once the event is prevented) and toggle on onClick. Separately: Radix's MENU does follow the arrow keys under React 19 — the #137 radio-group defect is specific to primitives that learn a key is down from a listener on document.
