# A PreToolUse hook refuses by PRINTING, not by exiting: charter's guard

_2026-09-25 · persistent_

A PreToolUse hook refuses by PRINTING, not by exiting: charter's guard emits {hookSpecificOutput:{permissionDecision:'deny',...}} on stdout and exits 0; exit 2 is only the fallback for a denial that could not be written (charter#438), and any other non-zero status is a NON-blocking error the harness logs while the tool call proceeds. So a test that compares only exit status and stderr says nothing about a guard: the verdict is on stdout, and a case where the guard never fires is green while proving nothing. Assert the decision itself (deny/allow).
