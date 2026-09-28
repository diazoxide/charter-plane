# Codex 0.147.0 workspace-write sandbox: tool commands may write only unde

_2026-09-28 17:41 · persistent_

Codex 0.147.0 workspace-write sandbox: tool commands may write only under the chat's own directory (not the plane's .charter/ when the chat is in a workspace) and are refused Unix-socket connect(); hooks run OUTSIDE the sandbox. So anything a Codex tool command must tell charter goes via a marker the next hook relays (charter #520, #517).
