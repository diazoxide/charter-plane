# charter-app, 2026-09-19: two facts from the M1.6 agent. (1) On this mach

_2026-09-19 23:40 · persistent_

charter-app, 2026-09-19: two facts from the M1.6 agent. (1) On this machine 'npx <tool>' is what hangs, not the tool — npx vitest sat at 0.00% CPU for 15 minutes while 'node ./node_modules/vitest/vitest.mjs run' finished the same suite in 2.3s. Other sessions were stuck on npx at the same time. (2) eslint-plugin-react-hooks v7 traces ref reads TRANSITIVELY: any function that reaches a useRef cannot be passed into a function called during render (react-hooks/refs), which forces an action catalogue to carry data rather than closures. Also: F2 arrives as a plain keydown in both WebKit and WebKitGTK, but macOS ships 'press Tab to highlight each item' OFF, so Tab does not reach buttons in a webview — a keyboard-only e2e must not assume it.
