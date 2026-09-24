# Before adding a warning, answer 'who will ever see it?'. In the Python

_2026-09-25 · persistent_

Before adding a warning, answer 'who will ever see it?'. In the Python CLI the SessionStart preflight printed doctor's output only when doctor EXITED NON-ZERO, so a doctor WARN reached nobody in-session; issue #306 proposed 'make doctor warn' as the fix and would have closed the issue while leaving the symptom (fixed properly in PR 307 via a systemMessage channel). In charter-app, check which surface a warning actually lands on (a session's context, the app UI, the needs-you signal) before calling it delivered.
