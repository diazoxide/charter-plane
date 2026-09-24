# opencode 1.18.23 applies a plugin's shell.env output as {...process.en

_2026-09-10 15:13 · persistent_

opencode 1.18.23 applies a plugin's shell.env output as {...process.env, ...plugin.env}: a plugin's value overrides the inherited environment, it does not fill gaps. A charter-generated opencode plugin that sets a session id variable therefore replaces whatever the parent set in every shell. Verified from the installed binary, not docs (diazoxide/charter #946).
