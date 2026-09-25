"""Argument parsing and dispatch for the ``charter`` CLI."""

from __future__ import annotations

import argparse
import functools
import os
import sys

from . import (
    commands_update,
    commands,
    commands_change,
    commands_frame,
    commands_handoff,
    commands_harness,
    commands_persona,
    commands_report,
    commands_secrets,
    commands_workspace,
    commands_worktree,
    contain,
    harness,
    hooks,
    statusline,
    toolgate,
    util,
    workspace,
)
from .browser import PINNED as _PLAYWRIGHT_PIN
from .forge.registry import KINDS as _FORGE_KINDS
from .frame import panel as frame_panel
from .secrets.registry import PROVIDERS


class _VersionAction(argparse.Action):
    """``--version``, resolved when it is asked for rather than when the parser is built.

    argparse's own ``action="version"`` takes a finished string at ``add_argument`` time,
    and this one is not free: `charter.channel.build_label` reads the dist-info to find
    out whether this is a dev build (PEP 610), and `build_parser` runs on **every** charter
    invocation — every hook, every status line render, several per turn. A lazy action
    moves that read onto the one path that wants it and off the several hundred that do
    not.

    Prints to stdout and exits 0, which is what the builtin does and what
    `commands_update._handoff` reads: it runs the newly installed `charter --version` and
    compares the last word to the version it asked for. A stable install still prints one
    word, so that comparison is untouched (see `channel.build_label`).
    """

    def __init__(self, option_strings, dest, **kw):
        kw.setdefault("nargs", 0)
        kw.setdefault("default", argparse.SUPPRESS)
        kw.setdefault("help", "Show this charter's version and, on a dev build, the "
                              "commit it was installed from.")
        super().__init__(option_strings, dest, **kw)

    def __call__(self, parser, namespace, values, option_string=None):
        from . import channel, update

        print(f"charter {channel.build_label()}", flush=True)
        # stderr, so the one word `charter --version` prints on stdout is unchanged for
        # anything that reads it.
        util.warn(update.END_OF_LIFE)
        parser.exit()


class _NoAbbrev(argparse.ArgumentParser):
    """An ArgumentParser that refuses prefix abbreviations, for the whole command tree.

    argparse expands any unambiguous prefix by default, so `charter secret get X Y --rev`
    ran as `--reveal` — and the PreToolUse leak guard, which looks for the flag the user
    would have to type, saw nothing to deny. A guard that a three-character abbreviation
    walks past is not a guard.

    Applied by making the ROOT parser this class: `add_subparsers` defaults its
    `parser_class` to `type(self)`, so every subcommand and sub-subcommand inherits it
    without each one having to remember. Setting `allow_abbrev=False` on the root alone
    would have covered only the top level, which is the level with nothing to protect.
    """

    def __init__(self, *a, **kw):
        kw.setdefault("allow_abbrev", False)
        super().__init__(*a, **kw)


def build_parser() -> argparse.ArgumentParser:
    p = _NoAbbrev(
        prog="charter",
        description="charter — discover, clone, and track org repos on demand.",
    )
    p.add_argument("--version", action=_VersionAction)
    sub = p.add_subparsers(dest="command", required=True)

    ini = sub.add_parser(
        "init",
        help="Scaffold a fresh control plane here: charter.toml, baseline dirs, "
             ".gitignore, and a status line. Additive + idempotent — never touches "
             "existing content. The first command a stranger runs.",
    )
    ini.add_argument("--forge", choices=sorted(_FORGE_KINDS), default="gitlab",
                     help="Forge this control plane tracks (default: gitlab).")
    ini.add_argument("--owner", help="Group/org/user that owns the repos "
                                     "(GitLab group or GitHub org/user).")
    ini.add_argument("--host", help="Self-hosted forge host (default: the forge's own public host).")
    # The acceptance half of init's one offer. charter has no interactive prompt (it runs
    # inside hooks, where blocking on stdin hangs the turn), so the offer is a printed
    # command and this flag is the command — nothing is ever cloned unasked.
    ini.add_argument("--clone-this-repo", action="store_true",
                     help="Also clone the git repo you are standing in into the first "
                          "workspace. This is how you accept the offer `charter init` "
                          "prints when it finds one; without it, init clones nothing.")
    # The front door is a FILE, not a feature: init writes one generic persona and
    # declares it in charter.toml. The name lives here, in a flag with a default — never
    # in the engine, which knows only that a plane may declare a default persona.
    ini.add_argument("--front-door", metavar="NAME", default="steward",
                     help="Name of the generic front-door persona to scaffold and declare "
                          "(default: steward). Skipped if this plane already has personas.")
    ini.add_argument("--no-front-door", dest="front_door", action="store_const", const=None,
                     help="Scaffold no persona at all; the plane declares no front door.")
    ini.set_defaults(func=commands.cmd_init)

    doc_check = sub.add_parser(
        "doctor",
        help="Preflight: check python/git/glab/auth/ssh/inventory before working.",
    )
    doc_check.add_argument("--json", action="store_true", help="Emit machine-readable results.")
    # What the SessionStart hook runs, and the reason it needs a flag at all: a hook runs
    # the same words a person types, so nothing in the process can tell the two apart — and
    # a tty test would misread `charter doctor --json` and `charter doctor | less` as the
    # hook. With it, no harness profile is probed (ruling 11) and no git call is made for
    # one: both are paid at every session start otherwise.
    doc_check.add_argument("--preflight", action="store_true",
                           help="Run as the SessionStart hook does: no harness-profile "
                                "probe and no git call for one. Every other check runs.")
    # The second of the two doors an install may come through (#881); `charter init` is the
    # first. A flag rather than a behaviour, because a preflight that installed software
    # every time it ran would be doing it as a side effect of a question — and `doctor` runs
    # from a SessionStart hook on every session.
    doc_check.add_argument("--fix", action="store_true",
                           help="Install what charter can install for this plane before "
                                "reporting — today, the Claude Code plugin. Never runs "
                                "without this flag.")
    doc_check.set_defaults(func=commands.cmd_doctor)

    ri = sub.add_parser(
        "reinit",
        help="Heal control-plane drift: create any missing baseline directory "
             "(personas/, inventory/, workspaces/) a newer charter expects. "
             "Idempotent + additive — existing content is never touched.",
    )
    ri.set_defaults(func=commands.cmd_reinit)

    d = sub.add_parser(
        "discover",
        help="Refresh inventory/repos.json from GitLab, then regenerate docs.",
    )
    d.add_argument("--no-probe", action="store_true", help="Skip per-repo stack detection (faster).")
    d.add_argument("--no-docs", action="store_true", help="Do not regenerate docs afterward.")
    d.set_defaults(func=commands.cmd_discover)

    c = sub.add_parser("clone", help="Clone repos on demand into the active workspace.")
    c.add_argument("repos", nargs="*", help="Repo name(s) or full path(s) from the inventory.")
    c.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    c.set_defaults(func=commands.cmd_clone)

    s = sub.add_parser("sync", help="Fetch + fast-forward cloned repos in a workspace (skips dirty).")
    s.add_argument("--workspace", "-w", help="Workspace to sync (default: the active one).")
    s.add_argument("--all", action="store_true", help="Sync every workspace.")
    s.set_defaults(func=commands.cmd_sync)

    st = sub.add_parser("status", help="Show workspaces and the cloned repos in the active one.")
    st.add_argument("--workspace", "-w", help="Workspace to detail (default: the active one).")
    st.add_argument("--all", action="store_true", help="Detail every workspace.")
    st.set_defaults(func=commands.cmd_status)

    br = sub.add_parser("browser",
                        help="The browser lane: charter ships the credential bridge, "
                             "Playwright ships the page-driving surface.")
    brsub = br.add_subparsers(dest="browser_cmd", required=True)
    bri = brsub.add_parser("install",
                           help="Generate Playwright's driving-surface skill into this "
                                "plane, from the tool that owns it (charter vendors none "
                                "of it — Apache-2.0, and it ships far more often than "
                                "charter does).")
    bri.add_argument("--version", help=f"@playwright/cli version (default: {_PLAYWRIGHT_PIN}).")
    bri.set_defaults(func=commands.cmd_browser_install)

    doc = sub.add_parser("docs",
                         help="Regenerate this plane's docs/topology.md — or read "
                              "charter's own documentation (`show`, `list`).")
    dsub = doc.add_subparsers(dest="docs_cmd")
    # Bare `charter docs` still generates. It did that long before it grew subcommands,
    # and Makefiles in the wild call it that way, so making the group require a
    # subcommand would break callers that never saw the change.
    doc.set_defaults(func=commands.cmd_docs)
    dgen = dsub.add_parser("generate", help="Regenerate docs/topology.md from the inventory.")
    dgen.set_defaults(func=commands.cmd_docs)
    dls = dsub.add_parser("list", help="List charter's own documentation topics.")
    dls.set_defaults(func=commands.cmd_docs_list)
    dsh = dsub.add_parser("show",
                          help="Print one of charter's own documentation pages — served "
                               "by the install that implements it, so it cannot be a "
                               "version behind the CLI reading it.")
    dsh.add_argument("topic", help="e.g. secrets, personas, git-policy (see `docs list`).")
    dsh.set_defaults(func=commands.cmd_docs_show)

    sv = sub.add_parser("save",
                        help="Commit + push the control plane's own changes via glab (HTTPS token — no SSH pain).")
    sv.add_argument("message", nargs="?", help="Commit message (default: 'charter save: N file(s)').")
    sv.add_argument("--sign", action="store_true", help="Sign the commit (default: unsigned, to avoid signer hangs).")
    sv.add_argument("--no-push", action="store_true", help="Commit only; don't push.")
    sv.set_defaults(func=commands.cmd_save)

    rcl = sub.add_parser("recall",
                         help="The one memory gate: search/list across ALL bases (active workspace + "
                              "active persona own + shared), each hit labeled by source.")
    rcl.add_argument("query", nargs="?", help="Keyword query; omit to list recent memories across bases.")
    rcl.add_argument("--scope", help="Comma list of scopes to search "
                                     "(workspace,persona,shared,refs,ephemeral); default "
                                     "workspace,persona,shared,refs. `refs` is the curated "
                                     "docs a persona collects — committed and shared, so it "
                                     "is searched by default; `ephemeral` is scratch and is "
                                     "not.")
    rcl.add_argument("--ephemeral", action="store_true", help="Also include the persona's session scratch.")
    rcl.add_argument("--full", action="store_true",
                     help="Also print a line of each memory's body (the path is always shown).")
    rcl.add_argument("--persona", help="Search this persona instead of the active one.")
    # One workspace or every workspace — never both. `-w beta --all-workspaces` has no
    # coherent reading, and argparse refusing it beats silently honouring one of them.
    _ws = rcl.add_mutually_exclusive_group()
    _ws.add_argument("--workspace", "-w", help="Search this workspace instead of the active one.")
    _ws.add_argument("--all-workspaces", action="store_true",
                     help="Search EVERY workspace's journal (persona + shared appear once). "
                          "For 'it was two weeks ago and I forget which task'.")
    rcl.add_argument("--since", metavar="WHEN",
                     help="Only memories recorded on/after this: an age (14d, 2w, 3m) or a "
                          "date (2026-07-01). Undated memories are excluded and counted.")
    rcl.add_argument("--limit", type=int, default=8, help="Max results (0 = no cap).")
    rcl.set_defaults(func=commands.cmd_recall)

    # Registered HERE, inside `build_parser` and therefore before `_add_frame_parsers`
    # snapshots `sub.choices`, so `handoff` is a core command a harness registering
    # `cli_name = "handoff"` would collide with loudly rather than silently take.
    #
    # The workspace is a positional and always named, the current one included: the
    # permission prompt that is this command's consent has to say where the chat goes, and
    # `.` says nothing (`docs/handoff.md`). There is no `--brief-file` — a prompt that
    # shows a path is an approval of a path, not of the brief — no `--harness` (a handoff
    # runs the calling chat's), and no `--repo` (the brief says what to clone, and the new
    # chat owns its own setup).
    hof = sub.add_parser(
        "handoff",
        help="Open a chat in a workspace you name, already working on a brief you pass as "
             "a quoted heredoc on stdin. Your harness asks before it runs.")
    hof.add_argument("workspace",
                     help="Where the chat opens — an existing workspace, or a new one with "
                          "--create. Always named, this workspace included.")
    hof.add_argument("--create", action="store_true",
                     help="Make the workspace first (LOCAL, never LIVE). Needs --vision.")
    hof.add_argument("--vision",
                     help="What the new workspace is for, one line. A workspace with no "
                          "vision is never proposed as a handoff target.")
    hof.add_argument("--persona",
                     help="Pin the new chat's persona. Without it the chat gets whatever a "
                          "new chat in that workspace gets.")
    hof.set_defaults(func=commands_handoff.cmd_handoff)

    gp = sub.add_parser("git-policy",
                        help="Golden rule: one credential — check/apply token-only git auth "
                             "(glab HTTPS, no SSH, no signing) on the control plane + every clone.")
    gp.add_argument("--apply", action="store_true", help="Write the policy (default: report drift).")
    gp.set_defaults(func=commands.cmd_git_policy)

    sl = sub.add_parser("statusline",
                        help="Render the plane's status line — from a JSON payload on "
                             "stdin, or ambiently with --watch on a harness that has no "
                             "status bar of its own.")
    sl.add_argument("--watch", action="store_true",
                    help="Repaint in place until Ctrl-C, in any spare terminal. Needs no "
                         "status-bar socket and no multiplexer, so it is the same render "
                         "on every harness.")
    sl.add_argument("--interval", type=float, default=statusline.WATCH_INTERVAL,
                    help="Seconds between repaints with --watch.")
    sl.set_defaults(func=lambda args: statusline.main(
        (["--watch", "--interval", str(args.interval)] if args.watch else [])))

    gl = sub.add_parser("gl-refresh",
                        help="Refresh the status line's forge state (open MRs/PRs + CI) "
                             "from each clone's own forge.")
    gl.add_argument("--workspace", "-w", help="Workspace to refresh (default: the active one).")
    gl.add_argument("--detach", action="store_true",
                    help="Return at once and refresh in a process that outlives this one. "
                         "What a hook's `async` used to buy, done by charter — one harness "
                         "skips async hooks outright.")
    gl.set_defaults(func=commands.cmd_gl_refresh)

    # Internal: the detached child `update.maybe_spawn` starts to refresh the update cache,
    # from the status line's render, the frame's gather and SessionStart (#938).
    # Hidden from help — nobody needs to run it, and it is not part of the UX.
    vc = sub.add_parser("_version-check")
    vc.set_defaults(func=commands.cmd_version_check)

    up = sub.add_parser("update",
                        help="Says that charter-cp is no longer maintained, and installs "
                             "nothing: 0.62.2 is the last release.")
    up.add_argument("--to", help="Accepted and ignored: nothing is installed.")
    up.add_argument("--bump", action="store_true",
                    help="Accepted and ignored: no pin is moved.")
    up.set_defaults(func=commands_update.cmd_update)

    nw = sub.add_parser("news",
                        help="What a version brought, and what this plane has not adopted.")
    nw.add_argument("--pending", action="store_true",
                    help="Every entry, any version, whose probe says you have not adopted "
                         "it yet.")
    nw.add_argument("--since", help="Report entries newer than this version.")
    nw.add_argument("--until", help="Stop at this version (default: the running one).")
    nw.add_argument("--for", dest="for_version", metavar="VERSION",
                    help="One version's entries, as the body of its release notes.")
    nwsub = nw.add_subparsers(dest="news_cmd")
    nw.set_defaults(func=commands.cmd_news)         # bare `charter news` = the range view
    nst = nwsub.add_parser("stamp",
                           help="Move every staged `unreleased-*` entry onto the version "
                                "about to ship — the bump PR's step, beside the four "
                                "files that carry a version number.")
    nst.add_argument("version", help="The version about to be published, e.g. 0.45.0 — "
                                     "the number alone, not the tag name.")
    nst.set_defaults(func=commands.cmd_news_stamp)

    ver = sub.add_parser("version",
                         help="The control plane's charter version lock: show drift, "
                              "conform this machine to it, or move the pin.")
    vsub = ver.add_subparsers(dest="version_cmd")
    ver.set_defaults(func=commands.cmd_version)     # bare `charter version` = show

    # The harness names are DERIVED, never written down. `charter guard` writes every
    # registered harness — there is no `detect()` gate on purpose, because `detect()`
    # answers "am I running inside this harness right now" rather than "does this team use
    # it", and gating on it would make a rule's reach depend on which harness happened to
    # type the command (ADR 0014: no sync step, nothing that can drift). The help said one
    # file while the command wrote three, so the claim moved to match (#369) — and reading
    # the registry rather than listing it here keeps this from being one more place to
    # remember the day a harness is added, which `harness/registry.py` warns about.
    from .harness import registry as _harness_registry

    gd = sub.add_parser("guard",
                        help="Force-prompt and stop-prompting rules for this plane. "
                             "Written in each harness's own syntax, into the file each "
                             "one reads — every harness charter knows ("
                             + ", ".join(_harness_registry.KINDS)
                             + "), not only the one you are running. charter keeps no "
                               "list of its own (ADR 0014).")
    gsub = gd.add_subparsers(dest="guard_cmd")
    gd.set_defaults(func=commands.cmd_guard_list)
    ga = gsub.add_parser("ask", help="Always prompt before this command runs.")
    ga.add_argument("pattern", help="e.g. 'terraform apply *' — wrapped as Bash(...) "
                                    "unless it already names a tool.")
    ga.add_argument("--local", action="store_true", help="Write this machine's own file (`.claude/settings.local.json`, gitignored) instead of the plane's committed settings — the rule is yours alone.")
    ga.set_defaults(func=commands.cmd_guard_ask)
    # `guard ask 'charter handoff *'` with the pattern fixed, because a news entry's `adopt:`
    # line cannot carry the quotes that pattern needs (`news._tokens`).
    gh = gsub.add_parser("handoff",
                         help="Always prompt before `charter handoff` runs — the rule "
                              "`charter init` writes on a new plane.")
    gh.set_defaults(func=commands.cmd_guard_handoff)
    gl = gsub.add_parser("list", help="Show this plane's force-prompt rules.")
    gl.set_defaults(func=commands.cmd_guard_list)

    # The mirror of `guard ask`. charter could only ever make a command prompt MORE; this
    # is the other direction, written into the same host file by the same registry (#291).
    gw = gsub.add_parser("allow",
                         help="Stop the harness prompting for a command pattern "
                              "(writes the host's own allow rule).")
    gw.add_argument("pattern", nargs="?", default="",
                    help="e.g. 'git status *'. Bare patterns are wrapped as Bash rules.")
    gw.add_argument("--local", action="store_true", help="Write this machine's own file (`.claude/settings.local.json`, gitignored) instead of the plane's committed settings — the rule is yours alone.")
    gw.set_defaults(func=commands.cmd_guard_allow)

    vsy = vsub.add_parser("sync",
                          help="Move THIS plane to the version it pins. A plugin is "
                               "installed per project, so no other plane moves.")
    vsy.add_argument("--cli", action="store_true",
                     help="Conform the machine-global `charter` binary instead. Shared by "
                          "every plane on this machine, so it can put others into drift.")
    vsy.set_defaults(func=commands.cmd_version_sync)

    vbp = vsub.add_parser("bump",
                          help="Move the pin: install + verify the target, then write "
                               "charter.toml. Affects every teammate, so in that order.")
    vbp.add_argument("--to", help="Version to pin (default: the latest published, as PyPI "
                                  "answers this command; refuses if it does not answer, or "
                                  "answers a version older than the one running).")
    vbp.add_argument("--push", action="store_true",
                     help="Also commit + push the lock, so teammates conform on their "
                          "next session.")
    vbp.set_defaults(func=commands.cmd_version_bump)

    hk = sub.add_parser("hook",
                        help="Dispatch a Claude Code hook by name — what the plugin's "
                             "hooks/hooks.json actually invokes (the plugin ships no Python).")
    hk.add_argument("name", choices=sorted(hooks._HANDLERS), help="Which handler to run.")
    hk.add_argument("--plugin-version", dest="plugin_version",
                    help="The installed plugin's version (hooks/hooks.json bakes this in); "
                         "compared against this CLI's own version to catch skew.")
    hk.set_defaults(func=lambda args: hooks.dispatch(args.name, args.plugin_version))

    tr = sub.add_parser("trace",
                        help="Session observability: guard denials, tool approvals, secret warnings, memory writes.")
    tr.add_argument("--session", help="A specific session id (default: the current one).")
    tr.add_argument("--summary", action="store_true", help="Aggregate counts instead of raw events.")
    tr.add_argument("-n", type=int, default=0, help="Show only the last N raw events.")
    tr.set_defaults(func=commands_persona.cmd_trace)

    # §4e/§4i's third verb, and the only one of the three an operator types rather than
    # presses: quit and close are palette rows in a running frame, and by the time a reopen
    # is wanted there is no frame to press a key in. Registered HERE, above
    # `_add_frame_parsers`, so it is one of the commands the harness collision guard checks
    # a `cli_name` against rather than one added after that snapshot is taken.
    ro = sub.add_parser(
        "reopen",
        help="Put back the plane your last `F2 → charter: quit` recorded: every "
             "workspace, chat, persona and directory, and — for Claude Code — the "
             "conversation.")
    ro.set_defaults(func=commands_frame.cmd_reopen)

    _add_harness_parser(sub)
    _add_workspace_parser(sub)
    _add_worktree_parser(sub)
    _add_change_parser(sub)
    _add_vault_parser(sub)
    _add_secret_parser(sub)
    _add_persona_parser(sub)
    _add_report_parser(sub)
    # Last: the collision guard below refuses a harness `cli_name` that shadows an
    # already-registered command, so it needs the FULL set of `charter`'s own commands
    # already in `sub.choices` — not just the ones defined above this line — to check
    # against. Placed after every other `_add_*_parser` call for that reason.
    _add_frame_parsers(sub)

    return p


def _add_report_parser(sub) -> None:
    r = sub.add_parser("report",
                       help="Report a charter bug or missing capability upstream (drafts "
                            "locally; nothing is published without a second command).")
    rsub = r.add_subparsers(dest="report_cmd", required=True)

    bug = rsub.add_parser("bug", help="Charter did something wrong.")
    # Optional, and joined by --from-file/--stdin: a body worth filing carries backticks,
    # `$` and fenced code, none of which survives being a shell argument. Same two flags,
    # same spelling, as `secret set` — there to keep a value off argv, here to keep one
    # intact.
    bug.add_argument("text", nargs="?", help="What went wrong, in your own words. Use `-` to read it from stdin.")
    bug.add_argument("--from-file", help="Read the body verbatim from a file.")
    bug.add_argument("--stdin", action="store_true", help="Read the body from stdin.")
    bug.set_defaults(func=commands_report.cmd_report_bug)

    gap = rsub.add_parser("gap", help="Charter cannot do something it should.")
    # Optional, and joined by --from-file/--stdin: a body worth filing carries backticks,
    # `$` and fenced code, none of which survives being a shell argument. Same two flags,
    # same spelling, as `secret set` — there to keep a value off argv, here to keep one
    # intact.
    gap.add_argument("text", nargs="?", help="What is missing, in your own words. Use `-` to read it from stdin.")
    gap.add_argument("--from-file", help="Read the body verbatim from a file.")
    gap.add_argument("--stdin", action="store_true", help="Read the body from stdin.")
    gap.set_defaults(func=commands_report.cmd_report_gap)

    ls = rsub.add_parser("list", help="Reports drafted on this machine, and what was sent.")
    ls.set_defaults(func=commands_report.cmd_report_list)

    sh = rsub.add_parser("show", help="Print one report exactly as it would be published.")
    sh.add_argument("id")
    sh.set_defaults(func=commands_report.cmd_report_show)

    # The undo for drafting. Drafting is cheap and local on purpose, which only works if
    # discarding is too — otherwise a redrafted report leaves its superseded twin in `list`
    # forever and the "not sent" column stops meaning anything.
    dl = rsub.add_parser("delete", aliases=["discard"],
                         help="Discard a drafted report (a sent one needs --force).")
    dl.add_argument("id")
    dl.add_argument("--force", action="store_true",
                    help="Discard even one already sent — that also drops the pointer a "
                         "later identical crash would have reused.")
    dl.set_defaults(func=commands_report.cmd_report_delete)

    # Its own command, not a flag on `send`: a flag an agent can pass is a flag it will
    # pass every time, where a one-off command has a single auditable purpose (ADR 0003).
    cs = rsub.add_parser("consent",
                         help="Agree, once, that reports may be published under your own "
                              "GitHub identity. Nothing sends until you do.")
    cs.set_defaults(func=commands_report.cmd_report_consent)

    sd = rsub.add_parser("send",
                         help="Publish a drafted report. THIS is the approval step — the "
                              "only reporting command that touches the network.")
    sd.add_argument("id")
    sd.add_argument("--new", action="store_true",
                    help="File even though charter found a possible duplicate.")
    sd.add_argument("--dry-run", action="store_true",
                    help="Show exactly what would be published, and send nothing.")
    sd.set_defaults(func=commands_report.cmd_report_send)

    cm = rsub.add_parser("comment",
                         help="Add your details to an existing upstream issue — the right "
                              "answer to a duplicate, since it keeps your reproduction.")
    cm.add_argument("id")
    cm.add_argument("--on", required=True, help="Upstream issue number to comment on.")
    cm.set_defaults(func=commands_report.cmd_report_comment)


def _add_workspace_parser(sub) -> None:
    w = sub.add_parser("workspace", aliases=["ws"],
                       help="Manage isolated per-task workspaces (workspaces/<workspace>/<repo>).")
    wsub = w.add_subparsers(dest="workspace_cmd", required=True)

    lst = wsub.add_parser("list", help="List workspaces and their clones; mark the active one.")
    lst.set_defaults(func=commands_workspace.cmd_workspace_list)

    cur = wsub.add_parser("current", help="Print the active workspace and how it was resolved.")
    cur.set_defaults(func=commands_workspace.cmd_workspace_current)

    rec = wsub.add_parser("_reconcile")  # internal: SessionStart hook
    rec.set_defaults(func=commands_workspace.cmd_workspace_reconcile)

    cr = wsub.add_parser("create", help="Create a workspace (optionally select it and clone repos).")
    cr.add_argument("name")
    cr.add_argument("--use", action="store_true", help="Make it the active workspace (locks the session to it).")
    cr.add_argument("--force", action="store_true",
                    help="With --use: switch even if the session is already locked to another workspace.")
    cr.add_argument("--live", action="store_true",
                    help="Make it LIVE (shareable — manifest + memory committed/synced/auto-saved). "
                         "Default is LOCAL (private, nothing committed).")
    cr.add_argument("--vision", "--about", dest="vision",
                    help="The goal/idea for this workspace — seeds its living charter "
                         "(workspaces/<name>/workspace.md). Ask the developer if you don't know it.")
    cr.add_argument("repos", nargs="*", help="Repos to clone into it immediately.")
    cr.set_defaults(func=commands_workspace.cmd_workspace_create)

    lv = wsub.add_parser("live",
                         help="Make a workspace LIVE (shareable) — or LOCAL with --off (private).")
    lv.add_argument("name")
    lv.add_argument("--off", action="store_true", help="Make it LOCAL (private) instead — stop committing it.")
    lv.set_defaults(func=commands_workspace.cmd_workspace_live)

    use = wsub.add_parser("use",
                          help="Set + lock the active workspace for this session (no mid-session switch).")
    use.add_argument("name")
    use.add_argument("--force", action="store_true",
                     help="Override the session lock and switch to another workspace mid-session.")
    use.add_argument("--create", action="store_true",
                     help="Create the workspace if it does not exist. Without this an "
                          "unknown name is an error with a did-you-mean — a typo used to "
                          "be created AND session-locked, so the correction was refused.")
    use.set_defaults(func=commands_workspace.cmd_workspace_use)

    unl = wsub.add_parser("unlock",
                          help="Release this session's workspace lock so another can be selected.")
    unl.set_defaults(func=commands_workspace.cmd_workspace_unlock)

    rm = wsub.add_parser("remove", help="Delete a workspace and its clones (guards unpushed work).")
    rm.add_argument("name")
    rm.add_argument("--force", action="store_true", help="Remove even with uncommitted/unpushed work.")
    rm.set_defaults(func=commands_workspace.cmd_workspace_remove)

    rn = wsub.add_parser("rename", aliases=["mv"],
                         help="Rename a workspace (moves its clones + memory; commits the move if LIVE).")
    rn.add_argument("old", help="Current workspace name.")
    rn.add_argument("new", help="New workspace name.")
    rn.add_argument("-m", "--message", help="Commit message for a LIVE workspace's rename.")
    rn.set_defaults(func=commands_workspace.cmd_workspace_rename)

    fk = wsub.add_parser("fork", aliases=["duplicate"],
                         help="Fork a workspace: copy its charter + manifest + memo so you can "
                              "branch off with full context (repos via --restore or on demand).")
    fk.add_argument("src", help="Source workspace to fork from.")
    fk.add_argument("new", help="Name for the fork.")
    fk.add_argument("--restore", action="store_true", help="Also clone the inherited repos now.")
    fk.add_argument("--live", action="store_true", help="Make the fork LIVE (default LOCAL).")
    fk.set_defaults(func=commands_workspace.cmd_workspace_fork)

    ri = wsub.add_parser("reinit",
                         help="Upgrade a workspace's structure to the current layout "
                              "(create missing workspace.md/memory/refs; stamp the version).")
    ri.add_argument("name", nargs="?", help="Workspace to reinit (default: the active one).")
    ri.add_argument("--all", action="store_true", help="Reinit every workspace (after a charter upgrade).")
    ri.set_defaults(func=commands_workspace.cmd_workspace_reinit)

    dflt = wsub.add_parser("default",
                           help="Nominate the workspace a session lands on when nothing "
                                "else decided (committed; mirrors `persona default`).")
    dflt.add_argument("name", nargs="?", help="Workspace to nominate; omit to show it.")
    dflt.add_argument("--clear", action="store_true", help="Remove the declared default.")
    dflt.set_defaults(func=commands_workspace.cmd_workspace_default)

    opt = wsub.add_parser("optimize",
                          help="Curate a workspace's memory: collapse exact duplicates and "
                               "repair the index with --apply; propose the rest.")
    opt.add_argument("name", nargs="?", help="Workspace to optimize (default: every one).")
    opt.add_argument("--all", action="store_true", help="Every workspace (the default).")
    opt.add_argument("--apply", action="store_true",
                     help="Apply the safe, reversible ops. Proposals always stay manual.")
    opt.add_argument("--stale-days", type=int, default=90, dest="stale_days",
                     help="Age at which a memory is proposed for review (default: 90).")
    opt.set_defaults(func=commands_workspace.cmd_workspace_optimize)

    rem = wsub.add_parser("remember",
                          help="Record one workspace memory (its own file, indexed) — the task journal.")
    rem.add_argument("text", nargs="?", help="Memory text; omit to list the workspace's memories.")
    rem.add_argument("--title", help="Optional title (else derived from the first line).")
    rem.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    rem.add_argument("--no-sync", action="store_true", dest="no_sync",
                     help="Don't reactively commit+push it now (LIVE workspaces; sync later).")
    rem.set_defaults(func=commands_workspace.cmd_workspace_remember)

    rc = wsub.add_parser("recall", help="Search the workspace's memories (--query) or list them all.")
    rc.add_argument("--query", "-q", help="Keyword query; omit to list every memory chronologically.")
    rc.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    rc.set_defaults(func=commands_workspace.cmd_workspace_recall)

    fg = wsub.add_parser("forget", help="Delete one workspace memory by slug or filename.")
    fg.add_argument("slug", help="Memory slug or filename (see `charter workspace recall`).")
    fg.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    fg.set_defaults(func=commands_workspace.cmd_workspace_forget)

    td = wsub.add_parser("todo",
                         help="Record what this task still means to do — or list them. "
                              "Intent, kept apart from memory (what it learned) and the "
                              "journal (what happened).")
    # Text optional, exactly like `remember`: the bare verb lists. A `list` SUBCOMMAND
    # would be indistinguishable from recording a todo whose text is "list".
    #
    # `done`/`forget` are read as verbs rather than as todo text, which the same argument
    # would seem to forbid — except that each takes a SLUG after it, and recording never
    # has a second positional. So the two are told apart by the shape of the call, not by
    # the word: `todo "forget the labels"` is one argument and records; `todo forget
    # 20260101-120000-labels` is two and closes. Real subparsers can't do this — argparse
    # matches the leading positional against `text` before any subcommand gets a look.
    td.add_argument("text", nargs="?",
                    help="The todo — or `done`/`forget` with a slug after it; omit to list.")
    td.add_argument("slug", nargs="?",
                    help="With `done` (finished — journalled) or `forget` (abandoned — "
                         "silent): which todo to close. Closing deletes it; the journal is "
                         "already the record of what happened.")
    td.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    td.add_argument("--query", "-q", help="Search the todos instead of listing them all.")
    td.set_defaults(func=commands_workspace.cmd_workspace_todo)

    nt = wsub.add_parser("note", help="Alias for `remember` — record a workspace memory (or list them).")
    nt.add_argument("message", nargs="?", help="Memory text; omit to list the workspace's memories.")
    nt.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    nt.add_argument("--no-sync", action="store_true", dest="no_sync",
                    help="Don't reactively commit+push it now (LIVE workspaces; sync later).")
    nt.set_defaults(func=commands_workspace.cmd_workspace_note)

    vs = wsub.add_parser("vision",
                         help="Show or set the workspace's Vision (the north star in workspace.md).")
    vs.add_argument("text", nargs="?", help="Vision text to set; omit to show it.")
    vs.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    vs.set_defaults(func=commands_workspace.cmd_workspace_vision)

    snp = wsub.add_parser("snapshot",
                          help="Capture repos+branches into the committed manifest (workspace.json).")
    snp.add_argument("name", nargs="?", help="Workspace (default: the active one).")
    snp.add_argument("--description", help="Set/update the workspace description.")
    snp.add_argument("--force", action="store_true",
                     help="Snapshot even if a repo has uncommitted/unpushed work.")
    snp.set_defaults(func=commands_workspace.cmd_workspace_snapshot)

    rst = wsub.add_parser("restore",
                          help="Rebuild a workspace from its manifest — clone repos + checkout branches.")
    rst.add_argument("name")
    rst.add_argument("--on-demand", dest="on_demand", action="store_true",
                     help="Don't clone now; clone each repo when you enter it.")
    rst.set_defaults(func=commands_workspace.cmd_workspace_restore)

    syn = wsub.add_parser("sync",
                          help="Pull the control plane for fresh workspace manifests + memory (before working).")
    syn.set_defaults(func=commands_workspace.cmd_workspace_sync)

    sav = wsub.add_parser("save",
                          help="Commit + push this workspace's manifest + memory (secret-scanned, via glab).")
    sav.add_argument("name", nargs="?", help="Workspace (default: the active one).")
    sav.add_argument("--message", "-m", help="Commit message.")
    sav.set_defaults(func=commands_workspace.cmd_workspace_save)

    aus = wsub.add_parser("_autosave")  # internal: Stop hook — debounced auto-save
    aus.set_defaults(func=commands_workspace.cmd_workspace_autosave)
    pbg = wsub.add_parser("_pushbg")    # internal: background push half of autosave
    pbg.set_defaults(func=commands_workspace.cmd_workspace_pushbg)


@functools.cache
def command_words() -> frozenset[str]:
    """Every word `charter <word>` already means, minus the registered kinds' own launchers.

    A harness profile named like one of these could never launch — `charter doctor` is
    `doctor` whatever `charter.local.toml` says — so `profiles.current` refuses it by name.
    Asked of the parser `main` dispatches through rather than of a list kept beside it, so a
    command added tomorrow is a word no profile can take on the day it is added. The kinds
    are left out because a declared profile named after its kind is how plain `claude` gets
    pinned.

    Built once per process: the parser does not change for the life of one.
    """
    subparsers = next(action for action in build_parser()._actions
                      if isinstance(action, argparse._SubParsersAction))
    # No `if h.cli_name` filter: a harness with no launcher contributes "", which names no
    # subcommand, so subtracting it changes nothing — the deletion sweep measured the filter
    # as a line the suite could lose, and a line nothing can observe is a line to delete.
    return frozenset(subparsers.choices) - {h.cli_name for h in harness.all()}


def _add_frame_parsers(sub) -> None:
    """One launcher per registered harness, plus the escape hatch (`charter frame --`).

    Generated from `harness.all()` rather than listed, which is the reason `registry.py`
    exists: a harness added to `KINDS` gets a launcher the day it is registered, with no
    second place to remember to update. That same automatism is exactly what makes a
    name collision dangerous — a harness registered with `cli_name = "status"` would
    otherwise silently take `charter status` away from the operator, with nothing
    printing so much as a warning, because nothing forced the two registries (core
    commands here, harnesses in `harness.KINDS`) to stay disjoint.

    **Two collisions, two different hazards, two different responses.** A `cli_name` that
    shadows a CORE command (anything registered before this function runs — see
    `build_parser`'s own comment about calling this last — plus the names this function
    reserves for itself: `frame`, `panel`, `frame-palette`, `frame-probe`)
    raises, loudly, at parser-construction time: `build_parser()` is called by every
    single `charter` invocation, so a registry mistake here breaks `charter --help`,
    `charter doctor`, everything — the failure has to happen in CI, not in an operator's
    terminal. A `cli_name` shared between two HARNESSES is a narrower problem: it costs
    one harness a launcher, not the whole CLI, and `harness.registry.all()` instantiating
    by dict VALUE rather than by key (`tests/test_guard_claims_its_reach.py`'s own
    `KINDS["zzz-fictional"] = KINDS[CLAUDE_CODE]` reproduces this directly) makes it
    reachable by a registry mistake that has nothing to do with `_add_frame_parsers` at
    all. Raising there would take down every command over a defect in a DIFFERENT
    module's registry — so the first registration wins the word and every later one is
    skipped, reported (not silently), and `build_parser()` keeps going.

    "First" is `harness.all()`'s own order, which is `KINDS`'s dict-insertion order —
    stable, and `registry.all`'s own docstring already calls it "registration order" — not
    an alphabetical or otherwise inferred one. Worth stating here rather than leaving a
    reader to work it out from `KINDS` being a dict at all.

    `sub.choices` is `argparse`'s own record of every subcommand name already claimed, so
    the CORE-collision check asks the same authority the CLI itself will dispatch
    through, rather than keeping a second list of "known" command names that could itself
    drift — but it is read as a SNAPSHOT taken before the harness loop starts, not live
    inside it: the loop's own `sub.add_parser(h.cli_name, ...)` calls grow `sub.choices`
    as they run, and reading it live would conflate "this collides with a core command"
    with "this collides with an earlier harness in this very loop" — exactly the two
    cases this docstring just said get different responses.
    """
    def _wire(parser, name):
        # **How to drive the thing this command opens, on the command that opens it**
        # (#747). `charter claude --help` and `charter frame --help` described four flags
        # and never mentioned that the window they are about to hand the operator has a
        # palette, an escape hatch, and somebody else's scrollback. The only place any of
        # it was written outside the frame is `charter docs show frame`, and nothing
        # pointed there; the only place inside it is the attention strip's two-word `F2
        # palette` field, which `density = minimal` drops.
        #
        # Set here rather than at each `add_parser` for the reason this whole function is
        # generated from `harness.all()`: one launcher per registered harness plus the
        # escape hatch, and a per-parser epilog is one more thing to remember for a
        # harness registered next year. It is also what makes `charter claude --help` and
        # `charter frame --help` identical BY CONSTRUCTION, which is the property #747
        # observed and wanted kept — they should say the same thing, and what was wrong
        # was that the thing they both said was silent on the frame.
        #
        # Three facts and no more. They are the three an operator hits in the first
        # minute: the palette is how you reach everything, the hatch is how you get the
        # keyboard back from a pane that stopped answering, and scrollback is tmux's
        # copy-mode now — which `docs/frame.md` itself calls "the difference people notice
        # first", and the one an operator has no reason to connect to charter at all.
        # `RawDescriptionHelpFormatter` because argparse reflows an epilog otherwise and
        # a wrapped key name reads as prose. Called rather than read off a module constant:
        # the sentence names this plane's own palette key, and a value frozen at import is
        # a second answer to a question `config.FRAME` already answers — the masked-default
        # shape the sweep is written to catch.
        parser.formatter_class = argparse.RawDescriptionHelpFormatter
        _keys = "\n".join(f"  {k}" for k in commands_frame.driving_keys())
        parser.epilog = (f"Inside the frame:\n{_keys}\n"
                         f"  charter docs show frame  —  all of it, and what `[frame]` "
                         f"configures.")
        parser.add_argument("rest", nargs=argparse.REMAINDER,
                            help="Passed to the harness verbatim.")
        parser.add_argument("--no-frame", action="store_true",
                            help="Run the harness bare, with no charter frame.")
        # Read-only, and shares `--no-frame`'s own `_OWN_FLAGS` treatment below so
        # `charter claude --probe` reaches `cmd_launch` as a flag rather than being
        # grafted onto the harness's own verbatim argv. `cmd_launch` checks this FIRST,
        # before resolving a harness or touching the workspace — see its own docstring.
        # A `charter frame-probe` sibling also exists (registered further down) for the
        # one caller this flag cannot serve: a news `check:`, which `news._PROBEABLE`
        # refuses for any command whose parser carries a pass-through positional — every
        # parser `_wire` builds has one (`rest`, above) — so `frame --probe` itself can
        # never be listed there. See `commands_frame.cmd_probe`'s own docstring.
        parser.add_argument("--probe", action="store_true",
                            help="Read-only: can a frame run here? Prints one line, "
                                 "starts nothing, never launches the harness.")
        # #518. `--workspace` is the top rung of `workspace.resolve`'s own precedence,
        # said on the command line — so it both aims the launch and skips the picker, in
        # one flag, without a second rule for the second job. `--pick` is the other
        # direction: ask even though something already answered.
        #
        # Both share `--no-frame`'s `_OWN_FLAGS`/`_OWN_VALUE_FLAGS` treatment below, so
        # they reach `cmd_launch` as flags instead of being grafted onto the harness's own
        # verbatim argv — and only in the leading position, which is the one unambiguous
        # rule available once a harness's own flags are indistinguishable from ours by
        # shape (see `_split_frame_argv`).
        parser.add_argument("--workspace", dest="workspace", default=None,
                            help="Run in this workspace (skips the picker).")
        parser.add_argument("--pick", action="store_true",
                            help="Choose the workspace before the harness starts, even "
                                 "if one is already selected.")
        # #845. Shares `--no-frame`'s `_OWN_FLAGS` treatment below for the same reason:
        # this is charter's own word and must not be grafted onto the harness's verbatim
        # argv, where `claude --fresh` would be an unknown flag to Claude Code.
        #
        # **It says "this run does not participate", in both directions.** Once bare
        # `charter` puts the recorded plane back, a plane an operator wanted to abandon
        # comes back on every launch and the only escape is deleting a file they have to
        # know about first. Skipping the restore alone would not be that escape: the same
        # run would go on RECORDING, and two seconds later the record it declined to act on
        # is the one it just overwrote — a loss nothing makes visible until the operator
        # asks for the plane back. So the flag turns both halves off, and `[frame] record`
        # is what a plane sets when it wants a fresh plane recorded from the start.
        parser.add_argument("--fresh", action="store_true",
                            help="Do not restore the recorded plane, and do not record "
                                 "over it: start one chat and leave the record alone.")
        # Which PROFILE of this kind to run — `charter claude --profile claude-work`, and
        # what `_profile_launch` rewrites `charter claude-work` into. Suppressed from the
        # help because an operator names a profile by typing it: the flag is the shape the
        # rewrite produces, so every splitter and branch below runs on one set of tokens.
        parser.add_argument("--profile", dest="profile", default=None,
                            help=argparse.SUPPRESS)
        parser.set_defaults(harness=name, func=commands_frame.cmd_launch)

    # Snapshot, not a live read of `sub.choices` inside the loop — see this function's
    # own docstring for why the two must be kept apart. `_add_frame_parsers` runs LAST
    # (`build_parser`'s own comment), so `sub.choices` here already holds every CORE
    # command: init, doctor, workspace, worktree, vault, secret, persona, report,
    # harness, hook, trace, all of it. `"frame"`, `"panel"`, `"frame-palette"` and
    # `"frame-probe"` join it even though none of their OWN
    # `add_parser` calls below has run yet: the loop finishes and registers every
    # harness BEFORE any of them are added, so a harness with `cli_name` equal to one of
    # these would pass a check against `sub.choices` alone (nothing there is named any of
    # them yet) and only collide once THAT `add_parser` call runs a few lines down —
    # where, on argparse versions that raise for a conflicting name, the error names the
    # reserved command instead of the harness that actually caused it, and on versions
    # that do not raise (this repo's own 3.11 floor — see `_split_frame_argv`'s docstring
    # for the same version gap elsewhere), the later `add_parser` call silently shadows
    # the harness instead — `frame`'s own escape hatch disappearing, every panel pane
    # failing to start because `charter panel` now means something else
    # (`layout.panel_argvs` emits exactly that argv; see `frame/panel.py`), the hotkey
    # palette silently opening a harness launch instead of a palette because `charter
    # frame-palette` now means something else too, or a news `check:`
    # naming `frame-probe` silently launching a harness instead of reading tmux's own
    # version (see `commands_frame.cmd_probe`'s own docstring).
    _core_commands = set(sub.choices) | {"frame", "panel", "frame-palette",
                                         "frame-probe", "frame-respawn", "frame-density",
                                         "frame-resize", "frame-gather", "frame-switch",
                                         "frame-toggle", "frame-chrome", "frame-chat",
                                         "frame-new-chat", "frame-quit", "frame-close",
                                         "frame-transcript", "frame-bar-rows",
                                         "frame-launch"}

    # Which harness (by `.name`, never `.cli_name` — that's the dict key below) has
    # already claimed each word, so a SECOND harness wanting it is told who got there
    # first rather than merely "already taken". Scoped to this one loop, never `sub
    # .choices`: after the first `sub.add_parser(h.cli_name, ...)` call below, that name
    # IS in `sub.choices` too, and reading it there would make a harness-vs-harness
    # collision indistinguishable from a harness-vs-core one — the exact conflation this
    # function's own docstring says the two checks below exist to avoid.
    _claimed_by: dict[str, str] = {}
    for h in harness.all():
        if not h.cli_name:
            continue
        if h.cli_name in _core_commands:
            raise ValueError(
                f"harness {h.name!r} wants `charter {h.cli_name}`, which is already a "
                f"charter command — rename the harness's cli_name or the command before "
                f"this can ship")
        if h.cli_name in _claimed_by:
            # Two REGISTERED harnesses, not a harness against a core command — a
            # narrower hazard (one harness loses a launcher, not the whole CLI; see the
            # docstring), so this is reported rather than raised. "First" is
            # `harness.all()`'s own order — `KINDS`'s dict-insertion order, per
            # `registry.all`'s own docstring ("registration order") — so the harness
            # registered EARLIER in `registry.KINDS` keeps `charter <cli_name>` and this
            # one simply gets no launcher of its own.
            util.warn(f"harness {h.name!r} also wants `charter {h.cli_name}`, already "
                      f"claimed by {_claimed_by[h.cli_name]!r} — {h.name!r} has no "
                      f"`charter <harness>` launcher of its own until the collision is "
                      f"fixed in the registry.")
            continue
        _claimed_by[h.cli_name] = h.name
        p = sub.add_parser(h.cli_name,
                           help=f"Run {h.cli_name} inside charter's frame.")
        _wire(p, h.cli_name)

    fr = sub.add_parser("frame",
                        help="Run any command inside charter's frame — `charter frame -- <cmd>`.")
    _wire(fr, "")
    # **Open a chat at the profile selector** — what bare `charter` rewrites to, and the
    # only launch that starts no harness of its own. Suppressed from the help for
    # `--profile`'s reason: an operator types `charter`, and this is the shape that rewrite
    # produces, so every splitter and branch below runs on one set of tokens.
    #
    # On `frame` alone, and never on a harness's parser: `charter claude --select` would be
    # asking charter to open a picker for a profile the operator has just named. It is
    # listed in :data:`_OWN_FLAGS` so `_split_frame_argv` hands it to argparse instead of
    # grafting it onto the command's verbatim argv, and argparse then refuses it by name on
    # any parser but this one.
    #
    # **No `--start` here**, and that asymmetry with `frame-launch` is deliberate. The row
    # the cursor opens on is a fact about the press — the profile of the chat `+` was
    # pressed in — and `cmd_new_chat` and `_open_workspace` call `cmd_launch` in-process
    # with it on the namespace, so it never has to survive a command line. A bare `charter`
    # has no press behind it and takes the plane's `[harness] default` instead. Adding a
    # flag nothing types would mean teaching `_OWN_VALUE_FLAGS` about a second value flag
    # for a spelling with no caller.
    fr.add_argument("--select", action="store_true", help=argparse.SUPPRESS)

    # Internal: one pane of a running frame, spawned by `layout.panel_argvs` — never
    # typed by an operator. The argv shape here (`panel <component> --session <fid>`)
    # must match what that function emits EXACTLY: it is the only thing standing between
    # a tmux pane and a process that fails at startup, leaving a hole in the frame.
    #
    # The word is a component NAME, not a key of `frame.slots.SLOTS`: one of the four
    # committed slot names, the id of the built-in behind one, or the id of a component
    # an installed provider supplies. `frame.panel.run` is what resolves it, and it is
    # the only validation — argparse takes any word, because the value arrives from
    # charter's own `layout.panel_command` and a second, weaker copy of that resolution
    # here is the two-answers shape #547 measured.
    pn = sub.add_parser("panel")
    pn.add_argument("slot", metavar="<component>")
    pn.add_argument("--session", dest="session", required=True)
    pn.set_defaults(func=lambda args: frame_panel.run(args.slot, args.session))

    # Internal, same reason `panel` above is a TOP-LEVEL sibling of `frame` rather than
    # nested under it: `_split_frame_argv` (below) treats `argv[0] == "frame"` as the
    # launcher's own escape hatch and grafts EVERYTHING past it onto the harness's own
    # verbatim argv before `argparse` ever gets a chance to route a subcommand — a
    # `frsub = fr.add_subparsers(...)` nested under `fr` would never be reached, because
    # `_split_frame_argv` runs first and unconditionally. `frame-palette` is a different
    # literal token, so `_split_frame_argv` leaves it alone and ordinary top-level
    # dispatch applies. It is fired by tmux via `run-shell` — the hotkey bind in
    # `conf_text` — and, with `--pane`, by tmux's own `split-window`; never typed by an
    # operator.
    #
    # Its `client` positional is ACCEPTED AND IGNORED, and is kept for one reason only:
    # a bind installed by a charter from before #729 is still sitting in a running
    # server's key table across the upgrade, and it fires this command with a
    # `#{client_name}` in it. Dropping the positional would make F2 on every such frame
    # fail to parse. Nothing reads it: an outcome is now written to the frame's own state
    # and drawn by its attention panel (`commands_frame._say_on_screen`), which every
    # client attached to that frame sees, so there is no longer a per-client screen to
    # choose between. `nargs="?"` is what lets the new bind, which carries no client at
    # all, parse through the same parser.
    #
    # `--pane` says "you ARE the palette" rather than "open one". One subcommand and not
    # two, because they are two halves of one keypress and two spellings would be two
    # things to keep in step — see `cmd_palette`.
    pal = sub.add_parser("frame-palette")
    pal.add_argument("client", nargs="?", default="")
    pal.add_argument("--pane", action="store_true")
    # Which CHAT the key was pressed in, expanded by tmux out of the presser's own
    # window's `@charter_chat` (`commands_frame.conf_text`). A value rather than a
    # positional, and OPTIONAL rather than required, for `frame-respawn --frame`'s reason
    # exactly: a bind installed by a charter that predates the option is still sitting in
    # a running server's key table across the upgrade, and it fires this command with no
    # `--chat` at all. Empty falls back to `$CHARTER_SESSION_ID`, which is what that frame
    # always resolved through — see `commands_frame._pressers_chat`.
    pal.add_argument("--chat", dest="chat", default="")
    # Which TAB the menu is about, and it is a different question from `--chat` above:
    # that one says which chat the keypress happened in — which frame's harness the pane
    # is carved off — and this says which chat the two rows in it act on. A right-click on
    # another chat's tab opens a menu over the frame the operator is looking at (#846).
    #
    # Not a positional, for `frame-switch`'s reason: the `client` positional above is a
    # compatibility surface for binds installed by older charters, and a second one would
    # be ambiguous with it. Optional, for `--chat`'s reason exactly — every invocation
    # that is not a tab menu carries none, and `frame/tabmenu.wanted` reads an absent or
    # unspellable value as "this is the ordinary palette" rather than as an error.
    pal.add_argument("--tab", dest="tab", default="")
    pal.set_defaults(func=commands_frame.cmd_palette)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # ones above. Started DETACHED by a palette row (#517,
    # `frame/builtin_actions._run_switch`), whose argv is exactly
    # `util.self_relaunch_argv("frame-switch", "--workspace"|"--persona", <name>)`. Also
    # typeable by hand from inside a frame, which is why the name is a value and not a
    # positional: `charter frame-switch --workspace foo` reads as what it does.
    #
    # The two are separate flags rather than one `--to` plus a noun, because a switch is
    # not one operation with a parameter — `frame/switch.py` has different refusals, a
    # different lock story and a different repaint cost for each, and a single flag would
    # have to be dispatched on a second one anyway.
    #
    # **`--workspace` is kept, and it refuses** (§4j: a chat belongs to its workspace for
    # life). It is what a `workspaces` tab click and a workspace name off the palette both
    # spawn, and it is typeable by hand — so removing the flag would turn a sentence the
    # operator can read into an argparse error, which is #764's defect one layer up. The
    # `help=` line names the persona alone because that is what the command can still do,
    # and a help text advertising a refusal is a worse first answer than the refusal.
    sw = sub.add_parser("frame-switch",
                        help="Adopt another persona in this frame.")
    sw.add_argument("--workspace", dest="workspace", default=None)
    sw.add_argument("--persona", dest="persona", default=None)
    sw.set_defaults(func=commands_frame.cmd_switch)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # two above. Fired by a PANEL pane's own `pane-died` hook (#382,
    # `commands_frame._panel_died_hook_argv`) — never typed by an operator, and never by
    # the harness pane's hooks, which carry the exit code instead. The frame it belongs
    # to travels on the argv (`--frame`), unlike `frame-palette`'s: this hook is armed on
    # the operator's own tmux too (#408), where `$CHARTER_SESSION_ID` is a session option
    # charter is not allowed to write. Optional, not required, so a hook installed by a
    # charter that predates #408 — already sitting in a running frame's pane options,
    # outliving the upgrade — still resolves its frame from the environment.
    rs = sub.add_parser("frame-respawn")
    rs.add_argument("slot")
    rs.add_argument("--pane", dest="pane", required=True)
    rs.add_argument("--frame", dest="frame", default=None)
    rs.set_defaults(func=commands_frame.cmd_respawn)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # ones above. Fired by the frame window's own `window-resized` hook (#488,
    # `commands_frame._resize_hook_argv`) — never typed by an operator. The hook used to
    # carry the sizes as literal text; `repos` is content-sized now, so the sizes have
    # to be RECOMPUTED against the window that just changed, and only charter can do
    # that. `--frame` travels on the argv for `frame-respawn`'s reason: on the operator's
    # own server there is no `$CHARTER_SESSION_ID` for a `run-shell` child to read.
    # Optional, not required, so a hook installed by an older charter and still sitting
    # in a running frame's window options resolves its frame from the environment.
    rz = sub.add_parser("frame-resize")
    rz.add_argument("--frame", dest="frame", default=None)
    rz.set_defaults(func=commands_frame.cmd_resize)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # ones above. Fired DETACHED by `commands_frame._spawn_gather` at launch (#512) —
    # never typed by an operator, and never by tmux: this one has no `run-shell` behind
    # it at all, it is `util.detach_self` out of the launcher's own process.
    #
    # BOTH arguments are required, and neither has a default that could be inferred. The
    # child is deliberately as far from the operator's terminal as a panel is (a new
    # session, no controlling tty), so `workspace.resolve`'s pointer rungs would answer
    # for the CHILD rather than for the frame — which is exactly the defect #512 is. The
    # launcher already knows both; stating them is what keeps the gather keyed to the
    # frame it is for.
    gt = sub.add_parser("frame-gather")
    gt.add_argument("--session", dest="session", required=True)
    gt.add_argument("--workspace", dest="workspace", required=True)
    gt.set_defaults(func=commands_frame.cmd_gather)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # three above. Started DETACHED by a palette row (`frame/builtin_actions`), whose
    # argv is exactly `util.self_relaunch_argv("frame-density", <level>)`. It
    # changes the RUNNING frame only — never charter.toml, which is hand-maintained (see
    # `cmd_density`'s own docstring) — and, like every other `frame-*` command here,
    # resolves which frame from `$CHARTER_SESSION_ID` at the moment it fires rather than
    # from anything baked into a shared bind. Deliberately NOT `choices=` on the
    # level: `instance.density_level` is the one gate on that closed set, and a second
    # copy of it in argparse would mean a level added to the table and not to the parser
    # exits 2 from inside a `run-shell` where nothing prints the reason.
    dn = sub.add_parser("frame-density")
    dn.add_argument("level")
    dn.set_defaults(func=commands_frame.cmd_density)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # ones above. Started DETACHED by a palette row, whose argv is exactly
    # `util.self_relaunch_argv("frame-chrome", <level>)`. It repaints the RUNNING frame's
    # panel panes — never charter.toml, for `frame-density`'s reason — and resolves which
    # frame from `$CHARTER_SESSION_ID` when it fires rather than from a shared bind.
    #
    # Deliberately NOT `choices=` on the level, for `frame-density`'s argument and one
    # more that is specific to this command: `instance.chrome_level` is the one gate on
    # the closed set, and it is also the boundary that keeps an operator's string away
    # from a tmux style value. A second copy of the set in argparse would be a second
    # answer to that question, and the weaker one — argparse exits 2 from inside a
    # detached child where nothing prints the reason, while `cmd_chrome` is a quiet no-op
    # that leaves the frame exactly as it was.
    cr = sub.add_parser("frame-chrome")
    cr.add_argument("level")
    cr.set_defaults(func=commands_frame.cmd_chrome)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # ones above. Fired by ONE COMPONENT's own `bind -n` — the `key` its
    # `[[frame.component]]` table declares, written into the frame's config by
    # `commands_frame.conf_text` — and typeable by hand from inside a frame. It shows or
    # hides that one component on the RUNNING frame; charter.toml is not touched, for
    # `frame-density`'s reason.
    #
    # Deliberately NOT `choices=` on the component, and for a stronger version of
    # `frame-density`'s argument: which names are togglable is a property of THIS PLANE's
    # arrangement, resolved from a committed file at the moment the key fires, so there is
    # no set for argparse to hold at parser-build time at all. `cmd_toggle` refuses a name
    # its own frame's arrangement does not contain — one gate, where the arrangement is.
    tg = sub.add_parser("frame-toggle")
    tg.add_argument("component")
    # Which chat the key was pressed in — `frame-palette --chat`'s twin, same source
    # (`#{@charter_chat}` in this component's own `bind -n`), same reason it is optional.
    tg.add_argument("--chat", dest="chat", default="")
    tg.set_defaults(func=commands_frame.cmd_toggle)

    # Internal, and a top-level sibling for `frame-toggle`'s reason. Fired by
    # `layout.BAR_ROWS_KEY`'s own `bind -n` and typeable by hand from inside a frame; it
    # cycles the RUNNING frame's tab strips 1 -> 2 -> 3 rows and back, and charter.toml is
    # not touched, for `frame-density`'s reason.
    #
    # **No argument at all, which is the whole shape of it.** A height is not a name an
    # operator picks off a set — it is the next one, and `layout.next_bar_rows` is where
    # that arithmetic lives. A `--rows N` would be a second way to say a thing one key
    # already says, and a number off an argv that would then need a gate.
    br = sub.add_parser("frame-bar-rows")
    # Which chat the key was pressed in — `frame-toggle`'s twin, same source
    # (`#{@charter_chat}` in the bind), same reason it is optional.
    br.add_argument("--chat", dest="chat", default="")
    br.set_defaults(func=commands_frame.cmd_bar_rows)

    # Internal, and a top-level sibling for the same `_split_frame_argv` reason as the
    # ones above. Started DETACHED by a palette row whose argv is exactly
    # `util.self_relaunch_argv("frame-chat", <chat id>)`
    # (`commands_frame._start_chat_switch`), and typeable by hand from inside a frame. It
    # moves the tmux CLIENT to another chat of this workspace and re-lays-out the panels
    # into the window tmux resized on the way (Phase 5 §3.7); charter.toml is not touched
    # and neither is any frame's recorded identity, for `frame-density`'s reason.
    #
    # **Two chat ids, and they are two different questions.** The POSITIONAL is where to
    # go — a name off a picker, or one typed. `--chat` is where the keypress came FROM,
    # `frame-toggle`'s twin and from the same source (`#{@charter_chat}` expanded in the
    # presser's own window), because one bind text is shared by every frame on the socket
    # and `$CHARTER_SESSION_ID` cannot tell two chats of one workspace apart.
    #
    # Deliberately NOT `choices=`, and for a stronger version of `frame-toggle`'s
    # argument: which chats exist is a property of the plane's frame directory at the
    # moment the key fires, so there is no set for argparse to hold at parser-build time.
    # `frame/chats.check` is the one gate, asked by this command and by the palette row
    # that starts it.
    ch = sub.add_parser("frame-chat")
    ch.add_argument("chat_id")
    ch.add_argument("--chat", dest="chat", default="")
    ch.set_defaults(func=commands_frame.cmd_chat)

    # The chat bar's `+`, and the one thing no other spelling of `charter <harness>` can
    # ask for: a launch that must NOT become the operator's terminal. `cmd_launch` has
    # taken `attach=False` since `_open_workspace` needed it (§4k), and until now it was
    # reachable only in-process — so a panel that wanted to add a chat had `charter claude`
    # and nothing else, which on a detached child with `/dev/null` for stdout takes
    # `bypass` and `os.execvp`s a bare harness into the void.
    #
    # **A sibling of `frame-chat` rather than a flag on it.** They are two different
    # operations that happen to share a noun: one moves this client to a window that
    # exists, the other makes one. `frame-chat`'s positional would have to become optional
    # to carry a `--new`, which makes `charter frame-chat` alone — a plausible typo —
    # parse into something that CREATES.
    #
    # **No name and no positional at all**, which is #518's line held: the chat's id is
    # allocated (`state.workspace_prefix`) and its workspace is the one this chat is in for
    # life (§4j), so there is nothing here for an operator to type and nothing to validate.
    # `--chat` is where the press happened, exactly as it is for `frame-toggle` and
    # `frame-quit`, and it falls back to `$CHARTER_SESSION_ID`.
    nc = sub.add_parser("frame-new-chat")
    nc.add_argument("--chat", dest="chat", default="")
    nc.set_defaults(func=commands_frame.cmd_new_chat)

    # Internal: what tmux starts in every chat pane, where the harness's own argv used to go
    # (`layout.session_argv`, `layout.chat_window_argv`, and `layout.respawn_argv` after the
    # placeholder in an operator's own tmux). It runs the profile's guards in the pane and
    # `exec`s the profile's command — `frame/launcher.py` is the whole of it. Never typed by
    # an operator: `charter <profile>` is the spelling, and this is what it becomes.
    #
    # **`--attended` rather than `--unattended`**, because unattended is what a pane gets
    # unless somebody is in front of it (review 3). A reopen, a handoff and a background
    # open must never stop on a question nobody can see, and a flag they would have to
    # remember to pass is a flag that gets forgotten — the failure would be a pane waiting
    # forever on a keypress that is never coming.
    #
    # **`--select` is the same pane with no profile named yet.** It draws the profile
    # selector there and starts the harness in it once a row is picked, so a chat window
    # can exist before anybody has said what it runs. `--start` is the row the cursor opens
    # on and the row that is marked — a NAME, like `--profile`, because no profile's
    # command or environment crosses tmux by any route.
    #
    # `--profile` is no longer `required`: the two flags are alternatives, and argparse has
    # no way to say "one of these" that produces a sentence worth reading. The command says
    # it itself (`launcher.NOTHING_NAMED`), which is also the only spelling that can explain
    # that this is not a command to type.
    fl = sub.add_parser("frame-launch")
    fl.add_argument("--profile", dest="profile", default="")
    fl.add_argument("--select", action="store_true")
    fl.add_argument("--start", dest="start", default="")
    fl.add_argument("--attended", action="store_true")
    fl.add_argument("rest", nargs=argparse.REMAINDER)
    fl.set_defaults(func=_frame_launch)

    # §4i's quit. Started DETACHED by the palette's confirmation row
    # (`commands_frame._start_leaving`) and typeable by hand, which is why it warns on its
    # own stderr as well as on the surface that confirmed it: §4i is explicit that quit
    # *warns and proceeds*, so the record of what was lost has to survive the keypress.
    #
    # **It takes no target, and that is the design rather than an omission.** Quit is
    # plane-scoped — the operator's own words were "all harness sessions will be closed" —
    # and §3.3 bounds it from the other side: a tmux server can hold more than one plane (the
    # legacy shared socket, an operator's own tmux) and session names carry no plane, so the set of things it stops can only come
    # from this plane's own chat directories. `--chat` is where the keypress came FROM, for
    # `frame-toggle`'s reason, and is used only to decide which workspace a later
    # `charter reopen` puts the operator back on.
    qt = sub.add_parser("frame-quit")
    qt.add_argument("--chat", dest="chat", default="")
    qt.set_defaults(func=commands_frame.cmd_quit)

    # §4d's `chat: close`, which is stage 4's new reaper arriving on its own. Quit's
    # teardown with one target and one file more (`state.record_closed`), because a missing
    # `exit` file means "was open" and closing writes no exit either — see `cmd_close`.
    #
    # **Two chat ids, and they are two different questions**, exactly as `frame-chat` has:
    # the POSITIONAL is which chat to close, optional so the bare command closes the one
    # you are in; `--chat` is where the keypress came from. Deliberately NOT `choices=`,
    # for `frame-chat`'s reason — which chats exist is a property of the frame root at the
    # moment the key fires, so there is no set for argparse to hold.
    cl = sub.add_parser("frame-close")
    cl.add_argument("chat_id", nargs="?", default="")
    cl.add_argument("--chat", dest="chat", default="")
    cl.set_defaults(func=commands_frame.cmd_close)

    # §4f's other half: the captured scrollback, offered rather than replayed. Opens a
    # pager in a window of its own; nothing is ever written into the harness's pane. See
    # the ADR 0018 amendment this change carries.
    tr = sub.add_parser("frame-transcript")
    tr.add_argument("--chat", dest="chat", default="")
    tr.set_defaults(func=commands_frame.cmd_transcript)

    # A TOP-LEVEL sibling of `frame` for a DIFFERENT reason than `frame-palette` above:
    # that one exists because `_split_frame_argv` eats everything
    # after `argv[0] == "frame"`. This one exists because `news._PROBEABLE` (charter's
    # `check:` allowlist, #317) refuses any command whose parser carries a pass-through
    # positional, and every parser `_wire` builds carries one (`rest`, the harness's own
    # verbatim argv) — so `("frame",)` can never be added there, `--probe` on it or not.
    # `frame-probe` takes no arguments at all, so it is not that shape and CAN be listed
    # (see `news._PROBEABLE` and `commands_frame.cmd_probe`'s own docstring). Unlike
    # `panel`/`frame-palette`, an operator can also type this one directly —
    # it is the same read-only check `--probe` runs, just reachable without a launcher.
    pb = sub.add_parser("frame-probe",
                        help="Read-only: can a frame run here? (same check as "
                             "`--probe` on any launcher above.)")
    pb.set_defaults(func=commands_frame.cmd_probe)


def _add_harness_parser(sub) -> None:
    h = sub.add_parser("harness",
                       help="Agent runtimes charter can run inside (Claude Code, opencode, "
                            "Codex) — list them, or arm the one `init` will not.")
    hsub = h.add_subparsers(dest="harness_cmd", required=True)

    lst = hsub.add_parser("list", help="Every registered harness, its ceilings, and which "
                                       "one this session is in.")
    lst.set_defaults(func=commands_harness.cmd_harness_list)

    ins = hsub.add_parser("install", help="Arm a harness whose wiring lives outside the "
                                          "plane (Codex). Running it IS the consent.")
    ins.add_argument("name", help="Harness name, e.g. codex.")
    ins.set_defaults(func=commands_harness.cmd_harness_install)


def _add_worktree_parser(sub) -> None:
    w = sub.add_parser("worktree", aliases=["wt"],
                       help="Worktrees of a workspace's clone — parallel pieces of one task "
                            "(workspaces/<ws>/.worktrees/<repo>/<piece>).")
    wsub = w.add_subparsers(dest="worktree_cmd", required=True)

    add = wsub.add_parser("add", help="Create a worktree on a new branch off the clone's HEAD.")
    add.add_argument("repo")
    add.add_argument("piece", help="Name of the piece; also the new branch name.")
    add.add_argument("--branch", help="Check out this EXISTING branch instead of creating one.")
    add.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    add.set_defaults(func=commands_worktree.cmd_worktree_add)

    lst = wsub.add_parser("list", help="List the worktrees of one clone, or of every clone.")
    lst.add_argument("repo", nargs="?", help="Only this repo (default: all clones).")
    lst.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    lst.set_defaults(func=commands_worktree.cmd_worktree_list)

    # `done` and `abandon` take no piece argument on purpose: the piece is where you are
    # standing, and an argument is an opportunity to declare someone else's finished.
    done = wsub.add_parser("done", help="Declare the piece you are standing in finished.")
    done.set_defaults(func=commands_worktree.cmd_worktree_done)

    ab = wsub.add_parser("abandon", help="Declare the piece you are standing in given up.")
    ab.add_argument("reason", help="Why you stopped — what whoever picks this up reads first.")
    ab.set_defaults(func=commands_worktree.cmd_worktree_abandon)

    # Its own command, not `list --history`: `list` answers what is running here (from git),
    # this answers what happened here (from the record), and ADR 0010 is about not letting
    # one name cover both.
    hist = wsub.add_parser("history", help="What happened to this workspace's pieces, "
                                           "including ones whose worktree is gone.")
    hist.add_argument("repo", nargs="?", help="Only this repo (default: all).")
    hist.add_argument("piece", nargs="?", help="Only this piece (default: all).")
    hist.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    hist.set_defaults(func=commands_worktree.cmd_worktree_history)

    rm = wsub.add_parser("remove", help="Remove a worktree (refuses to lose uncommitted "
                                        "or unpushed work).")
    rm.add_argument("repo")
    rm.add_argument("piece")
    rm.add_argument("--force", action="store_true",
                    help="Remove even with uncommitted or unpushed work (DISCARDS it).")
    rm.add_argument("--delete-branch", action="store_true", dest="delete_branch",
                    help="Also delete the piece's branch.")
    rm.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    rm.set_defaults(func=commands_worktree.cmd_worktree_remove)


def _add_change_parser(sub) -> None:
    """`charter change` — one intent, N repositories, as a per-workspace record.

    Records only: nothing under this command reaches a network, and there is deliberately
    **no expansion** anywhere in it — no glob, no pattern, no `--all-repos`, no "every repo
    in the workspace". Membership is enumerated by hand, one literal repo name per
    invocation, because in a LIVE workspace the record is committed and a record that could
    grow itself is a committed file that names repositories nobody typed.
    """
    c = sub.add_parser("change",
                       help="A change spanning several repos in one workspace: what it is "
                            "for, which repos are in it, which must land first "
                            "(workspaces/<ws>/changes/<slug>.json).")
    csub = c.add_subparsers(dest="change_cmd", required=True)

    cr = csub.add_parser("create", help="Create a change: a name and the reason for it.")
    cr.add_argument("change", help="The change's slug — also its default branch name, and "
                                   "the `Charter-Change:` trailer on every landing commit.")
    # Required, and the handler refuses an empty one too. A change with no stated reason is
    # unreadable six months later, which is the one job the record has that git cannot do.
    cr.add_argument("--why", required=True,
                    help="One line: what this work is for. Required.")
    cr.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    cr.set_defaults(func=commands_change.cmd_change_create)

    ad = csub.add_parser("add", help="Add one repo to the change, by literal name.")
    ad.add_argument("change")
    ad.add_argument("repo", help="A repo already cloned in this workspace. One name; there "
                                 "is no pattern and no expansion.")
    ad.add_argument("--branch", help="This member's branch (default: change/<slug>). Stored "
                                     "in the record: git knows a branch exists, it cannot "
                                     "know the branch is this change's.")
    ad.add_argument("--needs", action="append", metavar="REPO",
                    help="A member that must LAND before this one. Repeatable. Declared, "
                         "because no amount of reading either repository reveals it.")
    ad.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    ad.set_defaults(func=commands_change.cmd_change_add)

    dr = csub.add_parser("drop", help="Take a repo out of the change (or record one that "
                                      "was never in it), with the reason.")
    dr.add_argument("change")
    dr.add_argument("repo")
    dr.add_argument("--why", required=True,
                    help="One line: why this repo is out. Required — if members already "
                         "landed, this is the only thing that makes the resulting partial "
                         "world explicable.")
    dr.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    dr.set_defaults(func=commands_change.cmd_change_drop)

    ls = csub.add_parser("list", help="The workspace's changes, one row each.")
    ls.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    ls.set_defaults(func=commands_change.cmd_change_list)

    sh = csub.add_parser("show", help="One change whole: why, members, branches, blockers, "
                                      "exclusions.")
    sh.add_argument("change")
    sh.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    sh.set_defaults(func=commands_change.cmd_change_show)

    fg = csub.add_parser("forget", help="Delete the change record. Branches, requests and "
                                        "the landing log are untouched.")
    fg.add_argument("change")
    fg.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    fg.set_defaults(func=commands_change.cmd_change_forget)

    ph = csub.add_parser("push", help="Push every member's branch, open its request, and "
                                      "write the cross-link block into each body.")
    ph.add_argument("change")
    ph.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    ph.set_defaults(func=commands_change.cmd_change_push)

    # ONE member per invocation, and **there is no `--all`** — not a flag that defaults off,
    # a flag that does not parse (ADR 0020). It would have to answer "what now?" when member
    # 3 of 5 is rejected mid-loop, and the three available answers are each wrong in a case
    # the others handle. The shell loop somebody writes instead is five GATED landings,
    # because the gates live in this command; `--all` would be one ungated one.
    ld = csub.add_parser("land", help="Land ONE member: blocker gate, check gate at the "
                                      "head sha, merge, read back, record.")
    ld.add_argument("change")
    ld.add_argument("--repo", required=True,
                    help="The single member to land. Required, and there is no --all.")
    # `--rebase` DOES parse, and is refused with the reason — the asymmetry with `--all` is
    # deliberate. `--all` has no legitimate reading, so argparse rejecting it is the whole
    # answer; `--rebase` is a thing a reasonable person will try, and argparse's "unknown
    # option" would teach them nothing about why charter cannot put a trailer on it.
    ld.add_argument("--squash", action="store_true",
                    help="Land as a squash instead of a merge commit.")
    ld.add_argument("--rebase", action="store_true",
                    help="Refused, with the reason: a rebase landing leaves charter no "
                         "commit to carry the trailer and no single sha to revert.")
    ld.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    ld.set_defaults(func=commands_change.cmd_change_land)

    # A revert is a NEW change, with the ordinary gates — not an undo button. There is
    # deliberately no `--force`, no `--all` and nothing that deletes a branch: a
    # force-push over three default branches leaves a world where the change happened,
    # was undone, and no repository's history mentions either.
    rv = csub.add_parser("revert",
                         help="Derive a new change reverting what charter landed for this "
                              "one — a branch per landed member, then the ordinary gates.")
    rv.add_argument("change")
    rv.add_argument("--workspace", "-w", help="Target workspace (default: the active one).")
    rv.set_defaults(func=commands_change.cmd_change_revert)


def _add_vault_parser(sub) -> None:
    v = sub.add_parser("vault", help="Manage secret vaults (provider + config + persona).")
    vsub = v.add_subparsers(dest="vault_cmd", required=True)

    add = vsub.add_parser("add", help="Register a vault.")
    add.add_argument("name")
    add.add_argument("--provider", default="plain-file", choices=sorted(PROVIDERS),
                     help="Vault backend (default: plain-file).")
    add.add_argument("--file", help="File path for plain-file/reference vaults "
                                    "(default: .charter/vaults/<name>.json).")
    add.add_argument("--op-vault", metavar="NAME",
                     help="1Password vault charter keeps its item in (provider: 1password).")
    add.add_argument("--op-item",
                     help="1Password item whose fields are this vault's secrets "
                          "(provider: 1password). Default: charter-<vault>. Point it at "
                          "an item you already curate to adopt it as-is.")
    add.add_argument("--account", help="1Password account to pin to (provider: 1password); "
                                       "needed when signed into more than one.")
    add.add_argument("--persona", help="Tag this vault for a persona (e.g. devops, qa). It "
                                       "must be one this plane defines.")
    add.add_argument("--env", action="append", metavar="TARGET=SOURCE", default=[],
                     help="Bind the identity this vault is read through: TARGET is the "
                          "variable the CLI reads, SOURCE the one this machine carries it "
                          "in (e.g. OP_SERVICE_ACCOUNT_TOKEN=OP_ACME_DEVOPS_TOKEN). Only "
                          "NAMES are stored, never values. Repeatable.")
    add.add_argument("--token-env", metavar="SOURCE",
                     help="Shorthand for --env OP_SERVICE_ACCOUNT_TOKEN=SOURCE, the "
                          "1Password service-account case.")
    add.add_argument("--share", action="store_true",
                     help="Record it in the COMMITTED registry (vaults.json at the plane "
                          "root) so teammates inherit the wiring. Default is local-only: a "
                          "registry names which personas hold credentials and where their "
                          "files are, so it is never published by accident. The 1Password "
                          "--account pin always stays local.")
    add.add_argument("--force", action="store_true",
                     help="Replace an existing registration of this name. Does NOT migrate "
                          "its secrets — the old vault's file is left where it is, with "
                          "nothing pointing at it.")
    add.set_defaults(func=commands_secrets.cmd_vault_add)

    lst = vsub.add_parser("list", help="List configured vaults (names/status only, never values).")
    lst.set_defaults(func=commands_secrets.cmd_vault_list)

    vfy = vsub.add_parser("verify",
                          help="Resolve every reference for real and report what does NOT "
                               "resolve. `list` and `doctor` only check the vault is "
                               "reachable — a reference can be registered and still be dead.")
    vfy.add_argument("name", nargs="?", help="One vault (default: all of them).")
    vfy.set_defaults(func=commands_secrets.cmd_vault_verify)

    rm = vsub.add_parser("remove", help="Unregister a vault (leaves its file on disk).")
    rm.add_argument("name")
    rm.set_defaults(func=commands_secrets.cmd_vault_remove)


# Secret-operation arguments (shared by `charter secret` and `charter persona secret`).
def _sa_set(p):
    p.add_argument("key")
    p.add_argument("--stdin", action="store_true", help="Read the value from stdin.")
    p.add_argument("--from-file", help="Read the value verbatim from a file.")
    p.add_argument("--value", help="Inline value (discouraged: visible in shell history).")
    p.add_argument("--allow-empty", action="store_true", dest="allow_empty",
                   help="Permit storing an empty value. Refused by default: an empty "
                        "secret reads as present and healthy everywhere charter looks, so "
                        "the mistake only surfaces later as a 401.")


def _sa_get(p):
    p.add_argument("key")
    p.add_argument("--reveal", action="store_true", help="Print plaintext (interactive terminals only).")
    p.add_argument("--force", action="store_true", help="Allow --reveal to a non-interactive stdout.")


def _sa_key(p):
    p.add_argument("key")


def _sa_cp(p):
    p.add_argument("key")
    p.add_argument("dest",
                   help="Path of a REAL FILE to create. A device, FIFO, directory or "
                        "symlink is refused — /dev/stdout is this conversation.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite an existing file (destroying its contents and "
                        "setting it to 0600). Refused without this.")


def _sa_exec(p):
    p.add_argument("--env", action="append", metavar="NAME=key",
                   help="Inject secret <key> as env var NAME (repeatable).")
    p.add_argument("--file", action="append", metavar="ENVVAR=key",
                   help="Write secret <key> to a temp 0600 file; set ENVVAR to its path (repeatable).")
    p.add_argument("--dotenv", action="append", metavar="ENVVAR=NAME:key",
                   help="Add secret <key> as NAME to a temp 0600 dotenv file; set "
                        "ENVVAR to its path (repeatable — repeats sharing an "
                        "ENVVAR merge into one file). For tools that read a "
                        "dotenv secrets file, e.g. PLAYWRIGHT_MCP_SECRETS_FILE.")
    p.add_argument("--stream", dest="stream_mode", action="store_true",
                   help="Run the command as a CHILD with stdio inherited, wait for it, then "
                        "delete any --file/--dotenv temp files. For a long-running child "
                        "whose credential must be a FILE (Google ADC's "
                        "GOOGLE_APPLICATION_CREDENTIALS takes a path, not a value) — the "
                        "case --exec cannot serve, because exec leaves nothing alive to "
                        "clean up. Output is NOT redacted (nothing is captured). Cleanup "
                        "survives every terminating signal charter may catch — SIGINT, "
                        "SIGTERM, SIGHUP, SIGQUIT and the rest. It does not survive "
                        "SIGKILL, which cannot be caught, or a fault (SIGSEGV, SIGABRT), "
                        "which charter does not intercept; then the 0600 file survives.")
    p.add_argument("--exec", dest="exec_mode", action="store_true",
                   help="Replace this process with the command (os.exec) instead of capturing "
                        "it, so stdio streams through — required for a long-running child such "
                        "as an MCP stdio server. Output is NOT redacted (nothing is captured); "
                        "incompatible with --file and --dotenv — use --stream for those.")
    p.add_argument("command", nargs="*",
                   help="Command to run; put it after `--`, e.g. -- kubectl get pods.")


def _add_secret_parser(sub) -> None:
    s = sub.add_parser("secret", help="Read/write secrets in a vault; values stay out of the model.")
    ssub = s.add_subparsers(dest="secret_cmd", required=True)

    st = ssub.add_parser("set", help="Store a secret (value via --stdin/--from-file, not argv).")
    st.add_argument("vault"); _sa_set(st); st.set_defaults(func=commands_secrets.cmd_secret_set)

    ls = ssub.add_parser("list", help="List secret keys in a vault (never the values).")
    ls.add_argument("vault"); ls.set_defaults(func=commands_secrets.cmd_secret_list)

    au = ssub.add_parser("audit", help="Flag secrets older than --days for rotation.")
    au.add_argument("vault")
    au.add_argument("--days", type=int, default=90, help="Staleness threshold in days (default 90).")
    au.set_defaults(func=commands_secrets.cmd_secret_audit)

    g = ssub.add_parser("get", help="Show a secret (masked by default; --reveal for humans).")
    g.add_argument("vault"); _sa_get(g); g.set_defaults(func=commands_secrets.cmd_secret_get)

    rm = ssub.add_parser("rm", help="Delete a secret.")
    rm.add_argument("vault"); _sa_key(rm); rm.set_defaults(func=commands_secrets.cmd_secret_rm)

    cp = ssub.add_parser("cp", help="Materialize a secret to a 0600 file (e.g. a kubeconfig).")
    cp.add_argument("vault"); _sa_cp(cp); cp.set_defaults(func=commands_secrets.cmd_secret_cp)

    ex = ssub.add_parser("exec", help="Run a command with secrets injected as env/files, redacted.")
    ex.add_argument("vault"); _sa_exec(ex); ex.set_defaults(func=commands_secrets.cmd_secret_exec)


def _add_persona_parser(sub) -> None:
    pp = sub.add_parser("persona", help="Manage shared personas (committed) and use their vaults.")
    psub = pp.add_subparsers(dest="persona_cmd", required=True)

    cr = psub.add_parser("create", help="Create a persona → committed personas/<name>.md.")
    cr.add_argument("name")
    cr.add_argument("--role", help='Human role, e.g. "DevOps Engineer".')
    cr.add_argument("--delegate-when", metavar="WHEN",
                    help='REQUIRED (unless --extends): when the steward should route work '
                         'here, e.g. "CI/CD pipelines, k8s deploys". Becomes the persona\'s '
                         'routing line in its dispatchable description.')
    cr.add_argument("--vault", help="Vault this persona uses (default: the persona name).")
    cr.add_argument("--extends", metavar="PARENT",
                    help="Inherit another persona's charter + tools; this one adds its own on top.")
    cr.add_argument("--with-vault", action="store_true", help="Also register a local plain-file vault now.")
    cr.add_argument("--use", action="store_true", help="Make it the active persona.")
    cr.add_argument("--force", action="store_true", help="Overwrite an existing definition.")
    cr.set_defaults(func=commands_persona.cmd_persona_create)

    lst = psub.add_parser("list", help="List personas; mark active; show role + vault status.")
    lst.set_defaults(func=commands_persona.cmd_persona_list)

    show = psub.add_parser("show", help="Print a persona's metadata and charter.")
    show.add_argument("name"); show.set_defaults(func=commands_persona.cmd_persona_show)

    use = psub.add_parser("use", help="Set the active persona (writes .charter/active-persona).")
    use.add_argument("name"); use.set_defaults(func=commands_persona.cmd_persona_use)

    cur = psub.add_parser("current", help="Print the active persona and how it resolved.")
    cur.set_defaults(func=commands_persona.cmd_persona_current)

    clr = psub.add_parser("clear", help="Clear the active persona.")
    clr.set_defaults(func=commands_persona.cmd_persona_clear)

    df = psub.add_parser("default",
                         help="Show/set/clear the committed team-wide default persona (personas/.default).")
    df.add_argument("name", nargs="?", help="Persona to make the default (omit to show).")
    df.add_argument("--clear", action="store_true", help="Remove the committed default.")
    df.set_defaults(func=commands_persona.cmd_persona_default)

    rmv = psub.add_parser("remove", help="Delete a persona definition (commit the deletion).")
    rmv.add_argument("name")
    rmv.add_argument("--force", action="store_true",
                     help="Remove even if another persona extends/uses it (leaves a dangling ref).")
    rmv.set_defaults(func=commands_persona.cmd_persona_remove)

    sa = psub.add_parser("sync-agents",
                         help="Generate a Claude Code sub-agent (.claude/agents/<name>.md) per persona.")
    sa.add_argument("--persona", help="Only sync this persona (default: all).")
    sa.add_argument("--approve-mcp", action="store_true",
                    help="Ask, per server, whether the MCP command the personas' mcp.json "
                         "files name may receive the persona's vault value. What is "
                         "recorded is a digest of the line printed above the question, so "
                         "ANY change that changes that line — including the persona's "
                         "vault, an env value, or a key charter does not read — lapses "
                         "the approval and asks again.")
    sa.add_argument("--yes", action="store_true",
                    help="With --approve-mcp: approve every credentialed server without "
                         "asking. Required off a terminal, where nobody can be asked.")
    sa.add_argument("--dry-run", action="store_true",
                    help="With --approve-mcp: print the servers it would ask about and "
                         "record nothing.")
    sa.set_defaults(func=commands_persona.cmd_persona_sync_agents)

    mig = psub.add_parser("migrate",
                          help="Convert legacy personas/<name>.md → <name>/persona.md + memory/refs.")
    mig.add_argument("name", nargs="?", help="Only this persona (default: all).")
    mig.set_defaults(func=commands_persona.cmd_persona_migrate)

    # memory: the persona decides persistent (committed) vs ephemeral (session scratch).
    rem = psub.add_parser("remember", help="Write a memory (persistent by default; --ephemeral for scratch).")
    rem.add_argument("name", nargs="?", help="Persona (default: the active one).")
    rem.add_argument("text", help="The fact/note to remember.")
    rem.add_argument("--title", help="Short title (default: first line of the text).")
    rem.add_argument("--shared", action="store_true", help="Write to the cross-persona _shared namespace.")
    rem.add_argument("--ephemeral", action="store_true", help="Session scratch, deleted after the session.")
    rem.add_argument("--no-sync", action="store_true", dest="no_sync",
                     help="Don't reactively commit+push it now (record locally; sync later).")
    rem.set_defaults(func=commands_persona.cmd_persona_remember)

    rec = psub.add_parser("recall", help="Show a persona's memory, or --query to search it.")
    rec.add_argument("name", nargs="?", help="Persona (default: the active one).")
    rec.add_argument("--query", "-q", help="Keyword-search memories (ranked) instead of listing all.")
    rec.add_argument("--log", type=int, default=8, help="Log lines to show / max search hits (default: 8).")
    rec.set_defaults(func=commands_persona.cmd_persona_recall)

    dd = psub.add_parser("dedupe", help="Report near-duplicate memories (Jaccard overlap) to prune.")
    dd.add_argument("name", nargs="?", help="Persona (default: the active one).")
    dd.add_argument("--threshold", type=float, default=0.5, help="Overlap to flag (0-1, default 0.5).")
    dd.set_defaults(func=commands_persona.cmd_persona_dedupe)

    lt = psub.add_parser("lint", help="Config eval: dangling uses:, missing role/vault/delegate-when, stale agents.")
    lt.add_argument("--only", metavar="KEY",
                    help="Report only findings mentioning KEY, and exit non-zero solely "
                         "on those — what a news entry's probe needs to ask about one "
                         "feature.")
    lt.add_argument("name", nargs="?", help="Only this persona (default: all).")
    lt.set_defaults(func=commands_persona.cmd_persona_lint)

    stt = psub.add_parser("stats",
                          help="Roster health from committed memory: usage (count/recency) + "
                               "quality proxy (verification / dedup ratios); flags prune candidates.")
    stt.add_argument("name", nargs="?", help="Only this persona (default: all + _shared).")
    stt.add_argument("--recent-days", type=int, default=14, dest="recent_days",
                     help="Window for the RECENT column (default 14).")
    stt.set_defaults(func=commands_persona.cmd_persona_stats)

    bf = psub.add_parser("dispatch-backfill",
                         help="Seed the committed dispatch tally from past sessions' transcripts "
                              "(counts + dates only), so the routing baseline exists today.")
    bf.set_defaults(func=commands_persona.cmd_persona_dispatch_backfill)

    opt = psub.add_parser("optimize",
                          help="Curate persona memory: auto-apply safe ops (--apply: collapse exact "
                               "dups + repair index) and print tier-2 proposals for the steward to quiz.")
    opt.add_argument("name", nargs="?", help="Only this persona (default: all + _shared).")
    opt.add_argument("--all", action="store_true", help="Every persona (same as omitting name).")
    opt.add_argument("--apply", action="store_true",
                     help="Auto-apply the safe/reversible ops (else read-only report).")
    opt.add_argument("--stale-days", type=int, default=90, dest="stale_days",
                     help="Age (days) past which a memory is proposed for archival (default 90).")
    opt.set_defaults(func=commands_persona.cmd_persona_optimize)

    ms = psub.add_parser("memory-sync",
                         help="Commit + push all pending persona memory/refs in one step (secret-guarded).")
    ms.add_argument("--no-push", action="store_true", help="Commit only; don't push.")
    ms.set_defaults(func=commands_persona.cmd_persona_memory_sync)

    fgt = psub.add_parser("forget", help="Delete one memory by slug/filename.")
    fgt.add_argument("name"); fgt.add_argument("slug")
    fgt.add_argument("--shared", action="store_true")
    fgt.add_argument("--ephemeral", action="store_true")
    fgt.set_defaults(func=commands_persona.cmd_persona_forget)

    lg = psub.add_parser("log", help="Append to (with a message) or show the persona's activity log.")
    lg.add_argument("name", nargs="?", help="Persona (default: the active one).")
    lg.add_argument("message", nargs="?", help="Message to append; omit to show recent entries.")
    lg.add_argument("-n", type=int, default=20, help="How many entries to show (default: 20).")
    lg.set_defaults(func=commands_persona.cmd_persona_log)

    gc = psub.add_parser("_gc", help=argparse.SUPPRESS)  # SessionStart: prune ended-session scratch
    gc.add_argument("--detach", action="store_true", help=argparse.SUPPRESS)
    gc.set_defaults(func=commands_persona.cmd_persona_gc)

    tg = psub.add_parser("tool-gate",
                         help="PreToolUse gate: auto-approve the active persona's declared tools (reads stdin).")
    tg.set_defaults(func=lambda args: toolgate.main())

    sec = psub.add_parser("secret", help="Read/write the ACTIVE persona's vault (values stay out of the model).")
    xsub = sec.add_subparsers(dest="psecret_cmd", required=True)

    def _p(name, help_):
        q = xsub.add_parser(name, help=help_)
        q.add_argument("--persona", help="Override the active persona.")
        return q

    st = _p("set", "Store a secret in the persona's vault."); _sa_set(st)
    st.set_defaults(func=commands_persona.cmd_persona_secret_set)
    ls = _p("list", "List secret keys in the persona's vault.")
    ls.set_defaults(func=commands_persona.cmd_persona_secret_list)
    au = _p("audit", "Flag the persona's secrets older than --days for rotation.")
    au.add_argument("--days", type=int, default=90, help="Staleness threshold in days (default 90).")
    au.set_defaults(func=commands_persona.cmd_persona_secret_audit)
    g = _p("get", "Show a secret (masked; --reveal for humans)."); _sa_get(g)
    g.set_defaults(func=commands_persona.cmd_persona_secret_get)
    rm = _p("rm", "Delete a secret from the persona's vault."); _sa_key(rm)
    rm.set_defaults(func=commands_persona.cmd_persona_secret_rm)
    cp = _p("cp", "Materialize a secret to a 0600 file."); _sa_cp(cp)
    cp.set_defaults(func=commands_persona.cmd_persona_secret_cp)
    ex = _p("exec", "Run a command with the persona's secrets injected + redacted."); _sa_exec(ex)
    ex.set_defaults(func=commands_persona.cmd_persona_secret_exec)


# The persona *memory* subcommands mix an optional positional (persona name) with
# free-text and flags. argparse can't split positionals across an interspersed flag
# (`remember dev --shared "note"` fails), so we hoist their known flags to the end
# first — making `--shared`/`--ephemeral`/`--title` (etc.) work in any position while
# leaving positional text untouched. Scoped to these commands so no other command's
# flags are affected. (bool-flags, value-flags) per subcommand:
_MEM_FLAG_SPEC = {
    "remember": ({"--shared", "--ephemeral"}, {"--title"}),
    "recall": (set(), {"--log", "--query", "-q"}),
    "log": (set(), {"-n"}),
    "forget": ({"--shared", "--ephemeral"}, set()),
    "dedupe": (set(), {"--threshold"}),
}


def _hoist(tokens: list[str], bool_flags: set[str], value_flags: set[str]) -> list[str]:
    """Move recognized flags (and each value-flag's argument) after the positionals.
    Only the listed flags are moved; anything else — including free text that starts
    with '-' — stays a positional, so argparse handles it as before."""
    pos: list[str] = []
    flags: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in bool_flags:
            flags.append(t)
        elif t in value_flags:
            flags.append(t)
            if i + 1 < len(tokens):
                flags.append(tokens[i + 1])
                i += 1
        else:
            pos.append(t)
        i += 1
    return pos + flags


def _hoist_persona_memory(argv: list[str]) -> list[str]:
    if len(argv) >= 2 and argv[0] == "persona" and argv[1] in _MEM_FLAG_SPEC:
        bool_f, value_f = _MEM_FLAG_SPEC[argv[1]]
        return argv[:2] + _hoist(argv[2:], bool_f, value_f)
    return argv


#: argv prefixes whose trailing `-- <command…>` must survive argparse untouched.
_EXEC_PREFIXES = (("secret", "exec"), ("persona", "secret", "exec"))


def _split_exec_command(argv: list[str]) -> tuple[list[str], list[str] | None]:
    """Peel a trailing ``-- <command…>`` off an ``exec`` invocation before parsing.

    On **Python 3.11** argparse cannot hold a ``nargs="*"`` positional that follows
    repeated optionals, so the documented shape

        charter secret exec <vault> --env NAME=key -- kubectl get pods

    dies with "unrecognized arguments: -- kubectl get pods". 3.12 parses it fine —
    which is why this went unnoticed: the suite calls ``cmd_secret_exec`` directly
    and never crosses argparse, so CI was green on every version while the CLI was
    broken on the one charter declares as its floor.

    Splitting here makes the behaviour identical across versions. Only the `exec`
    subcommands are touched, and only at the FIRST ``--`` — anything after it is
    the child's, flags included.
    """
    for prefix in _EXEC_PREFIXES:
        if tuple(argv[:len(prefix)]) == prefix and "--" in argv[len(prefix):]:
            cut = argv.index("--", len(prefix))
            return argv[:cut], argv[cut + 1:]
    return argv, None


def _frame_command_names() -> set[str]:
    """Every subcommand `_add_frame_parsers` registers: each harness's `cli_name`, plus
    the `frame` escape hatch. Read at call time (`harness.all()`, never cached) for the
    same reason `_add_frame_parsers` itself iterates live rather than listing — a harness
    added to `KINDS` is covered the moment it is registered."""
    return {h.cli_name for h in harness.all() if h.cli_name} | {"frame"}


#: The ONLY tokens `_split_frame_argv` ever keeps for `argparse` itself, and only in the
#: fixed leading run described there. `-h`/`--help` are included deliberately: leaving
#: them out was tried first and broke `charter claude --help` outright — REMAINDER
#: absorbs `--help` just like any other harness token once it is past `argparse`'s own
#: matching, so `cmd_launch` received `rest=["--help"]`, found no harness named `""`
#: (bare `frame`) or treated it as a literal argv element otherwise, and the bypass path
#: (non-tty in that reproduction) called `os.execvp("--help", ...)` — a real crash
#: (`FileNotFoundError`, uncaught), not merely a UX regression. Keeping `-h`/`--help`
#: recognized here restores the working behaviour: `charter claude --help` shows
#: charter's OWN thin help for that subcommand (`usage: charter claude [-h]
#: [--no-frame] ...`) exactly as before this fix, and a harness's own `--help` is still
#: reachable — just as `-p`/`--continue` are — by putting it anywhere OTHER than this
#: fixed leading run (`charter claude --continue --help`, or explicitly `charter claude
#: -- --help`).
#:
#: `--probe` joined for the identical reason `--no-frame` is here at all: without it,
#: `charter frame --probe` has `argparse` never see `--probe` as `frame`'s own flag —
#: `_split_frame_argv` grafts it onto `args.rest` instead, and `cmd_launch` (finding no
#: harness named `""`, bare `frame`) hands `["--probe"]` to `bypass`, which
#: `os.execvp("--probe", ...)` turns into a `FileNotFoundError` — confirmed by running
#: `charter frame --probe` with this entry left out before adding it.
#: `--select` joined for the same reason, and it is what bare `charter` becomes: without it
#: `charter frame --select` never reaches argparse as a flag at all — `_split_frame_argv`
#: grafts it onto `args.rest`, `cmd_launch` finds no harness named `""` and hands
#: `["--select"]` to `bypass`, which is an `os.execvp("--select", …)`.
_OWN_FLAGS = ("--no-frame", "--probe", "--pick", "--fresh", "--select", "-h", "--help")

#: The launcher flags bare ``charter`` may carry — the ones that are about the LAUNCH
#: rather than about a harness that has not been named yet (#845). `_bare_launch` rewrites
#: ``charter --fresh`` into ``charter <default> --fresh``, so the flag is parsed by exactly
#: the parser that declares it and nothing here needs to know what it means.
#:
#: Deliberately not `_OWN_FLAGS`: `--probe`, `-h` and `--help` all have answers of their own
#: on a bare `charter` (argparse's usage message), and rewriting them into a harness launch
#: would take those answers away. `--workspace` is absent for a different reason — it takes
#: a value, so it is two tokens, and `charter -w foo` is a launch that names something,
#: which is exactly the shape `_restores_the_plane` excludes anyway.
_BARE_FLAGS = ("--fresh",)

#: The launcher's own flags that take a VALUE — `--workspace <name>` (#518). Kept apart
#: from `_OWN_FLAGS` because the two are consumed differently and getting that wrong is
#: silent in both directions: listed here but consumed as one token, and the name after it
#: becomes `argv[0]` of the harness's own command; listed in `_OWN_FLAGS` and consumed as
#: two, and a harness argument disappears.
#:
#: `--workspace=<name>` needs no entry — it is a single token, so the leading-run scan
#: below matches it by prefix and `argparse` splits it.
_OWN_VALUE_FLAGS = ("--workspace", "--profile")


def _split_frame_argv(argv: list[str]) -> tuple[list[str], list[str] | None]:
    """Peel a harness's own arguments off before `argparse` ever sees them.

    `nargs=argparse.REMAINDER` cannot hold a positional whose very FIRST token looks
    like an option `argparse` does not itself recognize: `charter claude -p hi` has
    `argparse` try to match `-p` against `claude`'s own options (`-h`, `--no-frame`),
    fail, and refuse the whole command with "unrecognized arguments: -p" — before
    REMAINDER ever gets a chance to absorb anything. Confirmed identical on 3.9, 3.12 and
    3.14, so unlike `_split_exec_command` above this is not something a Python-version
    split could route around: it is `argparse`'s documented behaviour on every version
    this repo supports, not drift on the 3.11 floor.

    Splitting here — the same shape `_split_exec_command` uses for `secret exec` —
    sidesteps the mechanism entirely: only `charter <name>` and a leading run of
    `_OWN_FLAGS` immediately after it are ever handed to `argparse`; everything past
    that point is captured here and grafted onto `args.rest` untouched by `argparse`'s
    own option matching, dashes and all. `_OWN_FLAGS` is recognized only in that one
    fixed leading position — anywhere else, a token that happens to spell `--no-frame`
    or `--help` is just more of the harness's own verbatim argv, which is the one
    unambiguous rule available once the harness's own flags (`-p`, `--continue`,
    anything) are indistinguishable from ours by shape alone.

    **A value-taking flag consumes two tokens, and that is why `_OWN_VALUE_FLAGS` is a
    separate tuple.** `--workspace foo` in the leading run is charter's; scanning it as one
    token would leave `foo` as the harness's `argv[0]`, which for `charter frame
    --workspace foo -- true` would try to execute the workspace name. A trailing
    `--workspace` with nothing after it stops the scan there and is handed to `argparse`,
    which refuses it with its own "expected one argument" — the right message, from the
    part that owns the flag.
    """
    if not argv or argv[0] not in _frame_command_names():
        return argv, None
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok in _OWN_FLAGS or any(tok.startswith(f + "=") for f in _OWN_VALUE_FLAGS):
            i += 1
        elif tok in _OWN_VALUE_FLAGS:
            # Two tokens, or one when the flag is last — that trailing case is handed to
            # `argparse` on its own so its "expected one argument" is what the operator
            # gets, rather than the flag disappearing into the harness's verbatim argv
            # where nothing would ever mention it.
            i += 2 if i + 1 < len(argv) else 1
        else:
            break
    return argv[:i], argv[i:]


def _subcommand_names(parser: argparse.ArgumentParser) -> set[str]:
    """Every top-level subcommand the parser accepts.

    Reads the subparsers action directly. ``_SubParsersAction`` is nominally private but
    has been stable for the life of argparse, and the alternative — keeping a hand-written
    list of command names in sync with :func:`build_parser` — is the kind of duplication
    that goes wrong silently.
    """
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def _hint_gap_if_unknown_command(parser: argparse.ArgumentParser, argv: list[str]) -> None:
    """Offer gap reporting when someone reached for a command charter does not have.

    This is the *only* mechanical signal charter gets that a capability is missing. The
    reporting feature is advertised on failure and nowhere else — which costs no prompt
    budget and is perfectly targeted — but a gap prints nothing on its own, so without this
    it would have no delivery mechanism at all.

    Narrow on purpose. A bad flag or a missing argument is a typo, not a missing
    capability, and offering to open an upstream issue every time someone mistypes would
    turn the prompt into noise — which is how a feature like this gets switched off.
    """
    if not argv or argv[0].startswith("-") or argv[0] in _subcommand_names(parser):
        return
    util.err(f"↳ charter has no `{argv[0]}` command. If that is something charter should "
             f'do, say so: charter report gap "<what you were trying to do>"')


def _record_crash(exc: BaseException, subcommand: str) -> None:
    """Draft a report for a crash, locally. Never raises.

    Wrapped defensively because a bug in the bug reporter is the worst possible thing to
    surface in place of the real error: whatever happens here, the caller re-raises the
    original exception and the developer still sees what actually broke.

    Nothing is published. This only writes to the Reporter's own disk, which is what lets
    detection default to on without charter reading as telemetry (docs/adr/0003).
    """
    try:
        from . import report
        rid = report.record_bug(exc, subcommand)
        if not rid:
            return
        rec = report.load(rid) or {}
        if rec.get("issue_url"):
            # Already filed from this machine. Pointing at the existing issue is the whole
            # reason a sent report is kept rather than deleted — local dedupe, no API call.
            util.err(f"↳ this is a charter bug you already reported → {rec['issue_url']}")
        else:
            util.err(f"↳ this is a charter bug, drafted locally as {rid} — nothing sent. "
                     f"Review it: charter report show {rid}")
    except Exception:  # noqa: BLE001 - see the docstring; this must never win over `exc`
        pass


def _bare_launch(argv: list[str]) -> tuple[list[str], int | None]:
    """Bare ``charter``: the profile selector, or today's usage error off a terminal.

    Returns the argv to parse and, when charter is finished here, a return code. Expressed
    as a REWRITE of argv rather than as a dispatch of its own — bare ``charter`` on a
    terminal becomes exactly `["frame", "--select"]`, and every splitter, flag and branch
    below it then runs on the same tokens a typed `charter frame --select` produces. A
    second path into `cmd_launch` would be a second set of answers about the workspace
    picker, `$CHARTER_HARNESS`, `--probe` and the frame, all of which are already settled
    for the typed form.

    **It carries :data:`_BARE_FLAGS`, and nothing else** (#845). ``charter --fresh`` is a
    launch that opts out of #845's record, and there is no harness name in front of it for
    the flag to belong to — so the rewrite puts one there and the flag rides along behind
    it, in the one position `_split_frame_argv` reads charter's own flags in. That is the
    whole widening: an argv holding anything else, `--fresh` alongside a subcommand
    included, is a command the operator typed and is returned untouched.

    **Three things stop it, and each is reachable on its own.**

    *A subcommand was typed.* Nothing here runs, `--version` included. It is a flag on the
    root parser (`_VersionAction`), so ``charter --version`` is a non-empty argv and never
    reaches this function at all — the version action still exits 0 from inside
    `parse_args`, which is what `commands_update._handoff` reads back.

    *Charter refused this plane's format version.* A plane charter cannot place declares
    nothing charter can read, so falling through would hand the operator argparse's usage
    message for a plane charter had in fact refused. The gate in `main` cannot cover it:
    that reads the typed subcommand and a bare argv has none.

    **What is no longer here: the default, and its refusal.** Until the selector, this
    function read `[harness] default` and launched it, and refused loudly when the plane
    named a profile this machine lacks. A bare `charter` now opens the selector, which
    lists what this machine has, marks the default where there is one and says on the row
    why anything cannot start — so there is no value left here to refuse and nothing left
    to guess. A plane that declared no default is no longer a usage error either.

    *Stdout is not a terminal.* Also today's behaviour, and this is the one that has to be
    a test rather than a comment. `commands_frame.cmd_launch` returns `bypass(argv)` when
    stdout is not a tty — it `os.execvp`s the harness in place of charter. Bare `charter`
    off a terminal is argparse's usage error, exit 2 with no side effect, so ``charter 2>&1
    | head`` is a probe that costs nothing. Rewrite argv unconditionally and that pipeline
    execs a harness — correct against every config anyone tested, wrong the first time a
    script asks whether charter is installed (#687, #690). It matters MORE with a selector
    than it did with a default: a pane with no terminal cannot draw one and cannot be asked
    anything, so there is nothing for the rewrite to lead to. Stdout, and stdout alone,
    because that is the exact stream `cmd_launch` branches on: a second, looser condition
    here is how the two come to disagree about what "interactive" means.
    """
    # `all` over an empty iterable is True, so bare `charter` falls through this without
    # an `argv and` in front of it — and the deletion sweep found that conjunct as a
    # survivor for exactly that reason. A guard that only restates what the next one
    # already says is the shape this repository deletes.
    if not all(tok in _BARE_FLAGS for tok in argv):
        return argv, None

    # *The plane's format version is one charter cannot place.* A plane charter has refused
    # declares nothing charter can read, so falling through would open a selector over a
    # plane charter had already refused — every row read out of a config it will not use.
    # Bare `charter` would look like a plane with no profiles rather than one charter
    # refused. The gate in `main` cannot cover this: it reads the typed subcommand, and a
    # bare argv has none. Both call the same :func:`_plane_refusal`, so there is one
    # message and one exemption rule between them.
    refusal = _plane_refusal(None)
    if refusal:
        util.err(refusal)
        return argv, 1

    # **It no longer reads a default, and that is the whole of what the selector changes
    # here.** Bare `charter` used to resolve `[harness] default` and launch it — a harness
    # session started before anybody said which one they wanted — and to refuse loudly when
    # the plane named one this machine does not have. Both go: the launch opens the profile
    # SELECTOR, which lists what this machine actually has, marks the default where there is
    # one, and says why any row cannot start. A default naming nothing simply marks no row
    # (ruling 18), and `charter doctor` is where that is reported.
    #
    # So a plane that declared no default is no longer a usage error either: every machine
    # has at least the built-in profile of whichever harness is installed, and the selector
    # is how charter asks rather than guesses.
    #
    # The flags the operator typed ride along, after the name rather than before it:
    # `_split_frame_argv` recognises `_OWN_FLAGS` only in the run immediately following
    # `charter <name>`, which is the same position a typed `charter frame --fresh` puts them
    # in.
    if not sys.stdout.isatty():
        return argv, None
    return ["frame", "--select", *argv], None


def _profile_launch(argv: list[str],
                    parser: argparse.ArgumentParser) -> tuple[list[str], int | None]:
    """`charter <profile>` → `charter <kind> --profile <profile>`, or *argv* untouched.

    :func:`_bare_launch`'s own shape and for its own reason: a REWRITE rather than a route
    of its own, so every splitter, flag and branch below it runs on the tokens a typed
    `charter claude --profile <name>` produces. A second path into `cmd_launch` would be a
    second set of answers about the workspace picker, `$CHARTER_HARNESS`, `--probe` and the
    frame, all of which are settled for the typed form.

    **A word charter already means is never a profile, and the parser is what says so.**
    `charter doctor` is `doctor` whatever `charter.local.toml` declares, which is why
    `profiles.current` refuses a clashing name outright — so a command reaches this and
    leaves it without the profiles ever being read. Asked of the parser `main` has already
    built, never of `command_words()`, which builds a SECOND one: ~10 ms measured on this
    machine, in every `charter hook …` process, on hooks that fire on Bash, Read, Grep,
    Write, Edit, Task, Skill and SendMessage.

    **A built-in's name is left exactly as typed.** `charter claude` already parses and
    `_launch` resolves `args.profile or args.harness`, so a declared profile that replaces a
    built-in is reached without a rewrite.

    A name the file declares and charter REFUSED says the rule instead of falling through to
    argparse, which would call it an invalid choice and offer the gap reporter for a profile
    the operator can see in their own file.
    """
    if not argv or argv[0].startswith("-") or argv[0] in _subcommand_names(parser):
        return argv, None
    from .frame import launcher

    p, why = launcher.resolve(argv[0])
    if p is not None:
        # The resolved names and never the typed word — `instance.harness_of`'s rule for
        # the same reason: what goes back onto a command line is charter's own string.
        return [p.kind, "--profile", p.name, *argv[1:]], None
    if why:
        util.err(f"charter: {why}")
        return argv, 2
    return argv, None


def _frame_launch(args) -> int:
    """`charter frame-launch` — the launcher every chat pane's first process is.

    A thunk rather than `func=launcher.cmd_frame_launch`, so `charter/frame/launcher.py` and
    `charter/profiles.py` stay off the import path that every `charter hook …` process pays
    for (ruling 43): this module is imported to build the parser, and the parser is built
    per tool call.
    """
    from .frame import launcher

    return launcher.cmd_frame_launch(args)


#: The commands that still run on a plane charter has refused (`config.PLANE_REFUSAL`).
#:
#: Three of them, and each earns its place by being about CHARTER rather than about the
#: plane's contents: `doctor` is where the refusal is reported, `version`/`_version-check`
#: answer "which charter is this" — the first question anyone asks on reading the refusal —
#: and `update` is the only remedy, since nothing but a newer charter can understand a
#: newer plane. Refusing the remedy would leave a plane with no way out but a hand edit.
#:
#: `--version`, `-h` and `--help` need no entry: argparse's own actions exit from inside
#: `parse_args`, above the gate, so help still works on a plane charter will not operate on.
#:
#: **`init` and `reinit` are NOT here.** Both write into the plane, and writing into a
#: layout you have been told you do not understand is the guess in its most damaging form.
#:
#: **Neither is `hook`, and that is the deliberate half.** charter's hooks are the session
#: briefing and the PreToolUse guard, and on a refused plane the guard is *already* covering
#: nothing: `forge.registry.known_forges_report` opens `charter.toml` through
#: `instance.load`, gets the refusal, and returns an empty forge set — a guard that looks
#: present and denies nothing. Refusing out loud turns a silent fail-open into a visible
#: one. It costs the session its briefing and not its turn, which is the standing rule for
#: a charter hook: the exit code below is 1, never `hooks.DENY_EXIT`, so Claude Code shows
#: the line and carries on.
_DESPITE_REFUSAL = frozenset({"doctor", "update", "version", "_version-check"})


def _plane_refusal(typed: str | None) -> str | None:
    """What to print instead of running *typed*, or ``None`` to carry on.

    One function for the two callers — `_bare_launch` (which has no subcommand to pass) and
    the gate in :func:`main` (which passes the typed token) — so the message and the
    exemption rule cannot come to differ between the bare form and the typed one.

    ``None`` is never exempt, and that is deliberate rather than incidental: it is what a
    bare ``charter`` passes, and opening a frame over a plane charter cannot place is the
    most expensive guess available to it.
    """
    from . import config
    refusal = config.PLANE_REFUSAL
    if not refusal or typed in _DESPITE_REFUSAL:
        return None
    from .update import END_OF_LIFE
    return (f"{refusal} Nothing was run. `charter doctor` reports it. {END_OF_LIFE}")


#: Commands that never print the end-of-life notice. Each one either runs inside something
#: else's display — a hook's output is Claude Code's, the status line is one row, a frame
#: command draws a tmux pane or popup — or is an internal child nobody typed. `update` and
#: `version` print the notice themselves.
_NO_NOTICE = frozenset({"hook", "statusline", "gl-refresh", "tool-gate", "update", "version"})


def _end_of_life_notice(typed: str) -> None:
    """Print :data:`charter.update.END_OF_LIFE` once, to a person at a terminal.

    Once per invocation, because :func:`main` calls this once. On stderr and only when
    stderr is a terminal, so no stdout a script or a harness parses changes, and a chat
    running `charter …` through its shell tool is not handed the line on every call.
    `charter --version` and `charter update` print it whatever stderr is.
    """
    if typed in _NO_NOTICE or typed.startswith(("_", "frame")):
        return
    try:
        if not sys.stderr.isatty():
            return
    except (AttributeError, ValueError):
        return
    from .update import END_OF_LIFE
    util.warn(END_OF_LIFE)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # First, so what it returns is then hoisted, split and parsed exactly as the same
    # tokens typed by hand would be. See `_bare_launch`.
    argv, rc = _bare_launch(argv)
    if rc is not None:
        return rc
    # Built HERE rather than after the splitters, and handed to the rewrite below. The
    # rewrite has to know which words are commands, and asking `command_words()` builds a
    # second parser — ~10 ms, in every process, including the `charter hook …` ones that run
    # per tool call. One parser answers both questions and then parses the result.
    parser = build_parser()
    # Directly after `_bare_launch`, so a profile named by a bare `charter`'s own default is
    # rewritten by the same line a typed one is. See :func:`_profile_launch`.
    argv, rc = _profile_launch(argv, parser)
    if rc is not None:
        return rc
    argv = _hoist_persona_memory(argv)
    argv, exec_command = _split_exec_command(argv)
    argv, frame_rest = _split_frame_argv(argv)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        # `parse_args` exits from inside itself, above the crash handler below — so the
        # gap signal needs catching here rather than a third `except` down there.
        _hint_gap_if_unknown_command(parser, argv)
        raise
    # The refusal, and both halves of where it sits are load-bearing.
    #
    # *After `parse_args`*, so charter has understood the command before declining it and,
    # more to the point, so `--version` and `--help` are already gone: both are argparse
    # actions that exit from inside `parse_args`, which is what keeps them working on a
    # plane charter will not otherwise touch. A gate above this line would have to
    # re-implement that, and would refuse the two questions an operator asks first.
    #
    # *Reading `argv[0]` and not `args.command`.* They agree for almost every command and
    # then do not: `charter secret exec` gives its own positional the dest `command`
    # (`_sa_exec`), so argparse overwrites the subparser name with the child command line
    # and `args.command` is a LIST there — unhashable, and a `not in` against a frozenset
    # raises rather than refuses. `argv[0]` is the token the operator typed, `_bare_launch`
    # has already rewritten a bare `charter` into it, and the root parser carries no flag
    # that survives to this line, so it is the subcommand every time.
    #
    # Subscripted with no emptiness guard because `parse_args` has already made one: the
    # subparsers are `required=True`, so an empty argv exits from inside it and never
    # arrives here. A guard would be an unreachable branch, which is the shape this
    # repository deletes.
    refusal = _plane_refusal(argv[0])
    if refusal:
        util.err(refusal)
        return 1
    _end_of_life_notice(argv[0])
    if exec_command is not None:
        args.command = exec_command
    if frame_rest is not None:
        args.rest = frame_rest
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # `charter … | head` is ordinary shell usage: the reader stopped, so the next write
        # fails. A condition, not a bug — charter did nothing wrong, so this joins the two
        # clauses below rather than falling through to the crash reporter, which used to
        # file a report every time somebody piped output into `head`.
        #
        # Redirecting at the fd level is what stops the interpreter trying to flush the
        # dead pipe again on the way out; without it the process exits 120 (a failed
        # shutdown flush) whatever is returned here.
        #
        # BOTH streams, and stderr is the one that actually matters: charter's progress
        # output goes there via util.ok/info, so under the usual `charter … 2>&1 | head`
        # it is stderr that hits the closed pipe. Redirecting only stdout left the exit
        # code at 120 with the report correctly suppressed — half a fix that looked whole.
        #
        # Guarded because a captured stream has no fileno: under test the redirect is
        # skipped, and there is no real pipe there to suppress anyway.
        for stream in (sys.stdout, sys.stderr):
            try:
                os.dup2(os.open(os.devnull, os.O_WRONLY), stream.fileno())
            except Exception:  # noqa: BLE001 - a best-effort tidy-up, never the story
                pass
        return 141  # 128 + SIGPIPE, matching the 128 + SIGINT returned below
    except contain.Refused as e:
        # A committed file that redirects a write is a defect in the PLANE's data, not in
        # charter — the same distinction `ProcTimeout` draws below, one noun over. Falling
        # through to the crash reporter would file a report against charter for it and
        # send whoever reads it looking in the wrong repository (#349).
        util.err(str(e))
        return 1
    except workspace.CannotCheck as e:
        # A directory charter could not look at, reaching a command with no partial answer to
        # give (#1084) — `persona dedupe`, `ws todo`, `persona stats`. A condition of the plane's
        # modes, like `Refused` above, so it is said in the one sentence for it, not filed as a
        # charter crash; before, those commands answered "none" over what they had not read.
        util.err(str(e))
        return 1
    except util.ProcTimeout as e:
        # A child that outlived its budget is a condition, not a bug. Only
        # KeyboardInterrupt was caught here, so a timeout reached the user as a traceback
        # from inside charter — which reads as charter crashing rather than as the tool it
        # called failing to answer.
        util.err(str(e))
        return 1
    except Exception as e:
        # Anything reaching here IS a charter bug — the two clauses above are exactly the
        # conditions, and that distinction predates this feature. charter is the only thing
        # that reliably observes its own crash (no hook does: PostToolUse matches only
        # Write|Edit|MultiEdit and Task|Agent, and PreToolUse runs *before* the command),
        # and it already holds the exception, the subcommand and the version that a hook
        # would have to reconstruct from a string.
        _record_crash(e, argv[0] if argv else "?")
        raise  # Recording is not handling. The developer still gets their traceback.
