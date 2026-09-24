# Generating a fixture plane must happen OUTSIDE any real plane, then be c

_2026-09-17 18:31 · persistent_

Generating a fixture plane must happen OUTSIDE any real plane, then be copied in. charter finds its plane by walking up from cwd, so 'charter init' run in a scratch dir inside workspaces/ide/... resolved the OPERATOR'S plane and wrote /Users/aharon/IdeaProjects/charter/.claude/settings.json (added a permissions.ask block) and created opencode.json there, 2026-09-17. Reverted with git checkout + rm. tests/fixtures/planes/generate.py in charter-app now builds in tempfile.TemporaryDirectory and refuses if any parent holds charter.toml (_refuse_enclosing_plane).
