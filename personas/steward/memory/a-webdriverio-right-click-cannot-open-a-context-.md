# A WebdriverIO right-click cannot open a context menu in a Tauri WebView,

_2026-09-22 23:46 · persistent_

A WebdriverIO right-click cannot open a context menu in a Tauri WebView, on EITHER engine. Measured in charter-app's own window with a listener on the element (webkit 605.1.15 macOS, 2026-09-22): element.click({button:'right'}) delivers 0 contextmenu events; a dispatched MouseEvent delivers 1 and Radix's ContextMenu opens. WebKitGTK 605.1.15 behaves the same (charter-app run 35771806598). The cause: click({button:'right'}) is a W3C pointer sequence, and contextmenu is a platform default action the engine raises from a NATIVE right-click, below where a synthesised sequence lands. So a scenario spec must dispatch the event. Prove it is the driver and not your wiring with a jsdom test that dispatches a real MouseEvent at the real App — and mutation-check it by making the global suppressor capture-phase, which must turn that test red.
