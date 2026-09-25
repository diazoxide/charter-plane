# Tauri 2 e2e (charter-app, verified 2026-09-18, M1.7): a scenario test th

_2026-09-18 11:35 · persistent_

Tauri 2 e2e (charter-app, verified 2026-09-18, M1.7): a scenario test that drives window.close()/show() from the page needs core:window:allow-close / allow-show / allow-is-visible — core:default grants NONE of them. Grant them in the e2e capability in tauri.e2e.conf.json only, never the default one. The trap: if the helper does 'void getCurrentWindow().close()' the rejection is swallowed, the window never hides, and the test that brings it back passes because it had never gone — 6 green tests testing nothing. Always await the promise and THROW on rejection in e2e helpers. Second trap: the app's CSP refuses eval, so a helper that takes the call as a STRING and evals it in the page fails with 'Refused to evaluate a string as JavaScript'; pass a real closure to browser.executeAsync and switch on a string argument instead.
