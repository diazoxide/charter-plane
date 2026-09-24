# charter-app scenario harness (2026-09-23, PR#176, measured with a docume

_2026-09-23 01:50 · persistent_

charter-app scenario harness (2026-09-23, PR#176, measured with a document-level keydown trace in WebKitGTK): WebDriver CANNOT drive a <button> by keyboard in this WebView. Two separate facts, both from the trace 'Shift on <button> Cancel; Tab on <button> Cancel; Enter on <button> Cancel': (1) browser.keys(['Shift','Tab']) is NOT delivered as a chord — the Tab keydown arrives with event.shiftKey FALSE, so Radix's FocusScope edge handler (which needs shiftKey) never fires; (2) Enter on a genuinely focused button (the engine delivers the keydown TO that button, unprevented) does NOT activate it — no implicit activation from synthesised key events. Escape works because Radix listens on document. So a scenario can press keys that JS handles, and cannot press a button. Anything asserting 'activate this button by keyboard' belongs in a jsdom test.
