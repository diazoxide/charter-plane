# Guard-override ruling (#370, PR 379): charter deliberately has NO conf

_2026-09-25 · persistent_

Guard-override ruling (#370, PR 379): charter deliberately has NO config key or env var that lifts a guard's deny — an override charter can READ is an override the AGENT controls (it can write charter.toml or its env), the same defect shape as #333/#338/#339. The override is the operator's own terminal: PreToolUse guards govern the harness's tools, so the human's shell was never inside the boundary. Keep the deny-message note in one place so every new guard inherits it, and derive the guard list in docs from all matchers (Bash and Read/Grep), not one.
