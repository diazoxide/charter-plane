# WebdriverIO cannot type into an xterm.js terminal with browser.keys (ver

_2026-09-17 19:51 · persistent_

WebdriverIO cannot type into an xterm.js terminal with browser.keys (verified 2026-09-17, charter-app scenario tests, embedded Tauri WebDriver on macOS): the driver's key mapping delivers every character TWICE and turns some letters into function keys ('from the first pane' arrived as 'ffRroommthheeffiiRrSstPpaannee'). Two other gotchas found the same way: the driver's Element Click is a synthetic DOM click, so an onMouseDown handler NEVER fires (focus a pane on onClick as well), and xterm does not focus itself from that synthetic click either. What works: click the pane, then $('.xterm-helper-textarea').addValue(text + '\n') — WebDriver's Element Send Keys on the terminal's own input, one path, no duplicates.
