# The wdio-tauri embedded driver dispatches a synthetic DOM keydown and pe

_2026-09-23 03:25 · persistent_

The wdio-tauri embedded driver dispatches a synthetic DOM keydown and performs NO default action: no activation from Enter, no focus movement from Tab (proved with two plain text inputs - focus did not move, keydown arrived unprevented), no shiftKey on a chord. One cause, three symptoms. So a scenario spec can only assert what the app handles in JavaScript; anything the ENGINE would do in response to a key belongs in jsdom.
