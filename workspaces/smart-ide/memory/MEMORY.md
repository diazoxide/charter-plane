# smart-ide — task memory

One file per memory — a small, programmatically-explorable DB, not a single log to
merge-conflict on. Files are timestamp-prefixed, so this index (and the directory) list chronologically. **Committed + shared** for LIVE workspaces. Write with `charter workspace remember "…"`, search with `charter workspace recall [--query …]`, drop one with `charter workspace forget <slug>`. Never put secrets here (vault only).
- [SI-7 (PR diazoxide/charter#485, branch si-7-no-select, commit efb8b09): ](20260926-190634-si-7-pr-diazoxide-charter-485-branch-si-7-no-sel.md)
