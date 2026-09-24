# charter-app docs/ are NOT covered by prettier in CI — the 'web' job runs

_2026-09-22 13:34 · persistent_

charter-app docs/ are NOT covered by prettier in CI — the 'web' job runs 'prettier --check .' with working-directory: app, so only app/** is checked. Running prettier over docs/*.md reformats every *italic* to _italic_ across files other agents are editing and buries a real change in whitespace noise. Patch repo-root markdown by hand in the file's existing style; never run the repo's prettier over docs/. (Learned on PR #149, reverted before committing.)
