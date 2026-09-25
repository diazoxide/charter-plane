# charter-app (2026-09-23, PR#176): Radix's FocusScope (@radix-ui/react-fo

_2026-09-23 01:13 · persistent_

charter-app (2026-09-23, PR#176): Radix's FocusScope (@radix-ui/react-focus-scope handleKeyDown) intercepts Tab ONLY at the edges of the scope — on the FIRST tabbable it acts on Shift+Tab and calls focus(last) itself, on the LAST it acts on Tab and calls focus(first); in between it does nothing and the browser's tab sequence decides. A WKWebView on macOS does not put a <button> in the tab sequence unless Full Keyboard Access is on, so in a dialog whose answers are buttons, plain Tab from the focused Cancel reaches NOTHING on macOS and the scenario fails with 'expected not to be displayed'. The route that works on every platform is Shift+Tab (Radix's own focus() call). Also measured: browser.keys(['Shift','Tab']) IS a chord — WDIO puts every key in the array down, pauses, then releases them all.
