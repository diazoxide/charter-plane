# claude --settings MERGES with the settings already in force, per key (

_2026-09-25 · persistent_

claude --settings MERGES with the settings already in force, per key (verified 2026-09-18 on claude 2.1.276 by planting a hook in a project .claude/settings.json and one in --settings, and watching both fire). What happens inside a key depends on its shape. `hooks` is a dict of arrays, so entries from both sides combine and both fire, which is why charter-app can arm its per-session state hooks without disarming hooks the operator or a project configured. `statusLine` is a single command, and there the flag simply wins: the file's statusLine is never invoked, silently (see [[claude-settings-shadows-statusline-it-does-not-m]]). So do not generalise 'merges' into 'nothing the operator configured is lost'. Before arming any new key through --settings, ask whether it is list-shaped or scalar-shaped, and measure that key.
