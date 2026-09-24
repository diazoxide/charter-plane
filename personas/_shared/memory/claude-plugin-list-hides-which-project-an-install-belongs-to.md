# claude plugin list shows each install's scope but never which project 

_2026-08-19 00:05 · persistent_

claude plugin list shows each install's scope but never which project a project-scope install belongs to; it repeats identical-looking entries. Read ~/.claude/plugins/installed_plugins.json and use each entry's projectPath (and installPath) before reporting where a stale install lives. Grepping .claude/settings.json for the plugin finds projects that enable it, not projects with an install record, and sends someone to the wrong repo.
