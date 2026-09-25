# charter-plane

Before 2026-09 this repository was `diazoxide/charter`; that name now belongs to the app.

This repository is a **charter control plane**: the committed state that
[charter](https://github.com/diazoxide/charter) reads when it opens this directory as a
project. It holds no software. charter itself is the desktop app in
[diazoxide/charter](https://github.com/diazoxide/charter); its bugs, features, design
record and docs live there.

## What is here

| Path | What it is |
| --- | --- |
| `charter.toml` | The plane's config: the forge, memory sharing, the default persona and harness. |
| `personas/steward/` | The one persona: its charter (`persona.md`) and its memory. |
| `personas/_shared/memory/` | Memory every persona reads. |
| `personas/_dispatch/`, `personas/_skills/` | Usage logs charter's hooks append. |
| `workspaces/` | Per-task workspaces. Only their committed parts are tracked; clones are ignored. |
| `.claude/` | Settings and the generated `steward` sub-agent charter hands the harness. |
| `docs/adr/` | Decision records 0001–0042, kept as history (see [`docs/adr/README.md`](docs/adr/README.md)). |

Every file and field charter reads or writes in a plane is specified in charter's
[plane format](https://github.com/diazoxide/charter/blob/main/docs/plane-format.md).
Per-machine state (`.charter/`, vaults, `charter.local.toml`) is never committed.

## Using it

Install charter from the
[latest release](https://github.com/diazoxide/charter/releases/latest), then open this
directory as a project. Commit plane changes with `charter save` or from the app.

## The Python charter

This repository used to be the Python CLI `charter` (PyPI `charter-cp`, tmux frame, Claude Code
plugin `charter@charter`). It is retired: the last commit that contained it is tagged
[`cli-final`](https://github.com/diazoxide/charter-plane/tree/cli-final), and `charter-cp` stays
frozen at 0.62.1 with no further releases. the app reads the planes the Python charter
made as they are.

## License

[MIT](LICENSE).
