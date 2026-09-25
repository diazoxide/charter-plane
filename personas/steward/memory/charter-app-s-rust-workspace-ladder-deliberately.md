# charter-app's Rust workspace ladder deliberately has eight rungs, not ni

_2026-09-20 10:17 · persistent_

charter-app's Rust workspace ladder deliberately has eight rungs, not nine: the tmux frame's launch record (.charter/frame/<fid>/workspace) is left out because docs/plane-format.md rules that .charter/frame/** is the frame's and the app neither reads nor writes there. The app's own replacement is to set CHARTER_SESSION_ID to its chat number in start::environment (charter-app#63) — then the per-session pointer rung is keyed on the chat, survives /clear, and the terminal rung below it (which under the app degrades to a recycled pty name from ttyname(0)) stops deciding anything.
