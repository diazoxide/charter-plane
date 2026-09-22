# Containment checks a path and does not hold it

Every containment gate in `charter-core` is a `stat` followed by a separate open.
`contain::readable`, `contain::writable` and `contain::no_link_on_the_way` resolve a path and
answer a question about it; the caller then hands the same path, by name, to `fs::write`,
`File::open`, `remove_file` or a `git` subprocess. Nothing holds a file descriptor across the
two, and no call uses `openat` or `O_NOFOLLOW`. A writer that can change what the name points
at, in the window between the answer and the open, gets the open it wants.

This is a known property — `contain.rs` has said so in its own module docs since M1.1, and
Python charter's `contain.py` says it of `file_refusal`: *"Not a TOCTOU guard, and not sold as
one: the attacker here holds a commit, not a process racing the read."* What it has not had is
a decision, a measurement, or a statement of which adversary it is or is not for. M1.9 is where
those are written down, because the alternative is that each new milestone rediscovers the
window and re-argues it from scratch.

**The gates stay checks on a path. The race between the check and the open is accepted, and
the reason is that a process racing charter on the operator's own machine is not this plane's
adversary — `SECURITY.md` already declines to defend against one, in those words, about a
guard with far more to lose. Two things change. The record charter keeps under
`.charter/app/` — the one file in the plane no Python charter writes — has its last component
opened with `O_NOFOLLOW`, so the kernel answers the link question at the instant of the open
instead of charter answering it a moment before. And the `openat`-beneath-a-descriptor rewrite
of the whole core goes to M3, with the external review decision 16 already requires for a
security-critical part, rather than into M1 one module at a time.**

## Who the plane's adversary is

The gate exists for a **committed symlink that travels with a clone**. That is not a
reconstruction; it is what the code was written for. `workspaces/evil -> ../../elsewhere`, with
a name that passes every lexical rule, made `charter workspace vision` print a file from
outside the plane (charter #442). `personas/x/persona.md -> ../../.charter/vaults/devops.json`
did the same to the secrets home from inside the plane, which is why the boundary is the data
directories and not "the plane, minus `.charter/`" (charter #336). Both attackers hold a
commit. Neither holds a process.

A racing writer is a different principal, and there are four candidates. They get four
different answers, and only one of them is hard.

**A `git checkout` is in the model as a state, not as a race.** An attacker who controls two
branches controls what is on disk after a checkout; they do not control when charter reads it.
The state they can produce — a link where charter expected a directory — is exactly what the
gate refuses when it looks, with no race involved, which is the whole point of the gate. To
turn a checkout into a race they would have to aim it at a window measured in microseconds, on
a clock that belongs to the operator. What a checkout concurrent with a plane write *can* do is
leave charter's own file half-written somewhere unhelpful, and that is a robustness problem
with a different fix (charter writes beside and renames over), not a containment one.

**The operator's editor is not an adversary.** It is the operator.

**Another chat, another agent, or a hook charter itself started is the candidate that has to be
answered rather than waved at, and the answer is already written down.** `SECURITY.md`, about
the `PreToolUse` guard that stands between a model and a vault — a guard with much more to lose
than this one — says it plainly: *"It is a guard against mistakes, not an attacker with shell
access as your user."* It then spends two pages enumerating what that means: a glob, a
variable, a command substitution, an interpreter, `base64`, `git show`, a program charter does
not know walking a directory. Each is one keystroke from a denied form and each is allowed.

An agent that can write plane files has a shell as the operator. To put bytes outside the plane
it does not need to win a microsecond against `fs::write`; it needs `cp`. Closing the race
while that page stands would be tightening the one hinge on a gate that is propped open, and
this repository has a name for that shape — `contain.py` refused to do half of a symlink fix
and file the rest, on the reasoning that *"doing half of this while claiming all of it would be
worse than filing it."*

**A confined agent would be in the model, and charter does not have one.** The honest version
of the third answer is conditional: the race is out of scope *because* nothing in charter makes
an agent less privileged than charter itself. The moment something does — a sandboxed harness,
a per-chat user, a seccomp or Seatbelt profile that denies writes outside the plane — the
racing writer becomes a principal that can do through charter what it cannot do directly, and
this decision is the first thing that has to be re-opened. That is written here so the
re-opening is a lookup rather than a rediscovery.

**What the race buys an attacker who already has a shell is worth naming, because it is not
nothing.** Charter writes content *charter* chose, with the operator's hand, to a path the
attacker chose. The record under `.charter/app/` is the sharpest case: it holds the command
lines the next launch runs, and a launch that reads it from outside the plane runs a command
line nobody consented to, with no prompt in the way. That is an escalation of attribution and
of trust, not of privilege — the attacker could have written the file directly — but it is the
reason the record, and not the whole core, gets a fix in this milestone.

## What was measured

**By the shipped gates themselves**, in
`the_window_each_gate_leaves` (`crates/charter-core/tests/nothing_escapes_while_a_writer_races.rs`
in charter-app), on CI's `ubuntu-24.04` runner. One thread runs a gate and then the caller's own
open, 20,000 rounds; a second plants and removes a symlink at the path. It is committed and
`#[ignore]`d, so it can be run again rather than believed:

```console
cargo test -p charter-core --test nothing_escapes_while_a_writer_races -- \
    --ignored --nocapture the_window_each_gate_leaves
```

| Gate, and what the caller does next | Escapes per 20,000 |
| --- | --- |
| `contain::readable`, then `fs::read` — personas, workspaces, memory, `start` | **5025** |
| `contain::no_link_on_the_way`, then `fs::read` — the record read at launch | **1881** |
| `contain::no_link_on_the_way`, then `fs::write` — the record written at quit | **7600** |
| `contain::open_no_link` — the same read | **0** |
| `contain::create_no_link` — the same write | **0** |

An "escape" on the read rows is a read that returned the planted file's contents from outside
the plane — on the record row, a command line a launch would have run. On the write row it is
the whole record, byte for byte, landing outside the plane.

**A quarter to two fifths. The reviewer's 34 and 63 per 20,000 were not the ceiling, and neither
was this ADR's first draft.** That draft measured a transcription of these functions into
Python, because the machine the work was done on would not start a newly linked Mach-O — every
freshly compiled binary and dylib stalled in `_dyld_start` at 0% CPU, and `cargo` stalled one
level down, with `sample` putting rustc in `dyld4::APIs::dlopen` loading a proc-macro dylib. It
reported 1300, 9 and 5 and called them an **upper** bound, on the reasoning that a slower victim
leaves a wider window.

That reasoning was wrong, and wrong in the unsafe direction. The transcription's *racer* was
Python too, so it planted far less often per victim iteration, and the counts came out two
orders of magnitude LOW. The correction is recorded rather than quietly applied, because a
module that understates its own window by that much is exactly the thing this ADR exists to
stop, and because the next person to reach for a transcription should know what it cost.

Three things in that table are worth more than the counts.

**`contain::readable` is the widest window and the most-used gate.** It resolves with a
`readlink` per component and a prefix comparison before it answers — 22 µs against
`no_link_on_the_way`'s 5.6 µs — and the attacker gets all of it. Every persona read, every
workspace read, every memory read and the persona a chat starts on go through it. It is also the
one row `O_NOFOLLOW` cannot help.

**The escapes come through the last component, and the reason is structural.** The attack that
writes a whole record outside the plane plants a link at `reopen.json.writing`, the file charter
is about to create. Swapping a *directory* component — `.charter/app` for a link out — was
attempted for 20,000 rounds and never won once: a directory cannot be replaced by a symlink with
a single `rename` (both macOS and Linux answer `ENOTDIR`), so the attacker has to `rmdir` and
then `symlink`, and charter's own `create_dir_all` competes for the same gap. This is not a
claim that directory components are safe. It is the measured reason the fix below is aimed where
it is.

**`O_NOFOLLOW` costs nothing.** With nobody racing, an open with it and an open without it
measured 9.37 µs and 9.30 µs — the same number twice. It is a flag on a call that is already
being made, so there is no throughput question to answer: ADR 0026's 13 MB burst is terminal
output, and the record is written when a chat changes or the app quits.

**And the tests were watched failing before they were trusted.** Each guard was removed in turn,
on a throwaway branch, and CI recorded which tests went red: `O_NOFOLLOW` removed took the two
planted-link tests; `O_NONBLOCK` removed took the FIFO test with "opening a fifo must not
block: Timeout"; the walk dropped from the pair took the directory-link test *and* three
pre-existing `reopen` tests, which is how the wiring into the call sites is proved; and the call
sites reverted to check-then-open took both end-to-end racing tests, 423 planted command lines
taken in 4,000 rounds.

## What is closed, and it is the half charter owns alone

`contain::no_link_on_the_way` refuses **every** link on the way, including the last component.
Its callers — the reopen record and the hook socket, both under `.charter/app/` — are the only
paths in the plane that no Python charter writes; `docs/plane-format.md` records the reopen
file as the desktop app's own. So opening the last component with `O_NOFOLLOW` enforces the
predicate those callers already declare, atomically, and there is no Python behaviour for it to
diverge from. The walk stays: a link at a directory component is still refused by the `lstat`
that finds it, and the pair is written as one function so the two halves cannot drift apart —
which is the failure this module's own docs say the repository has found five times.

The record's other two questions move onto the descriptor at the same time. Today
`read_or_refusal` calls `symlink_metadata` to ask whether the record is a plain file and
whether it is within its size bound, and then opens the path again to read it; those are two
different objects with a window between them, and a FIFO swapped in after the check blocks the
read for ever at launch, before there is a window or a tray to kill. Asking an open descriptor
is the same information with nothing in between.

## What is not closed, and why it waits for M3

Stated at full size, because a partial fix presented as a complete one is the failure mode this
ADR is written against.

- **`contain::readable` and `contain::writable` are unchanged**, and they are the 5025 row —
  a quarter of every read, with a racer on the machine.
  `O_NOFOLLOW` cannot be applied to them: those gates deliberately **follow** a link that lands
  back inside the plane, because refusing every symlink would break a plane that legitimately
  links a persona directory, and because Python's `os.path.realpath` follows them too. Refusing
  them in Rust alone is a divergence in the half of the pair that decision 15 requires to match.
- **Directory components above the last one** are still a check and not a handle, in every gate
  including the one being fixed.
- **Every path handed to `git`** — `worktree add`, `remove`, `merge`, `publish` — is a path,
  and a descriptor cannot be handed to a subprocess. ADR 0027's workspace confinement is
  check-then-name by construction, and the verb it most matters for is the destructive one.
- **The hook socket's `bind` is path-based.** There is no portable `bindat`, and the
  `remove_file` of a stale socket and the `set_permissions` after the bind are two more
  path calls after the walk.
- **A hard link is invisible to all of this**, as the record's own docs already say.

The reason all of that waits is not the dependency. `rustix` is **already** a dependency of
`charter-core` under `cfg(unix)` with the `fs` feature, so `openat`, `O_NOFOLLOW`,
`O_DIRECTORY` and `renameat` cost nothing new and `cargo-deny` has nothing new to say. The
reason is that doing it properly is a different containment model, not a patch to this one:
resolution moves from "where does this name land" to "what is beneath this descriptor", every
plane read and write changes shape, the behaviour that follows an inside-landing link has to be
rebuilt on top of it or deliberately dropped, and the differential against Python has to be
re-argued either way. Decision 16 says security-critical parts get the differential proof
**plus an external review** before the Rust one answers for real, and names M3 as where that
review happens. Deciding the shape of the containment layer at M1.9 and reviewing it at M3 is
those two steps in the wrong order.

## What this rules out

- Presenting the gates as a defence against a process racing charter, in the module docs, a
  release note, or anywhere else. The window is now written into `contain.rs` with the
  measurement, so the next reader meets it as a decision rather than as a defect.
- Closing the race one call site at a time. A gate that is atomic here and a check there is
  the drift this module is built to avoid; the next change to this is the whole core at once.
- `O_NOFOLLOW` on `contain::readable` or `contain::writable`, which would refuse a link that
  lands back inside the plane and diverge from Python while doing it.
- A new crate for syscalls while `rustix` is already in the tree.
- Treating "an agent can write plane files" as out of the model *silently*. It is out of the
  model because nothing confines an agent; the day something does, this ADR is re-opened.
- Holding a milestone behind the `openat` rewrite, or landing that rewrite without the external
  review decision 16 requires.

## Amendment, 2026-09-22: the re-opening clause fired, and the answer is that the ground has not moved

This record accepts the `stat`-then-open race on one condition, and states the condition rather
than hiding it:

> A confined agent would be in the model, and charter does not have one. The honest version of the
> third answer is conditional: the race is out of scope *because* nothing in charter makes an agent
> less privileged than charter itself. The moment something does … this decision is the first thing
> that has to be re-opened.

**[ADR 0041](0041-a-plugin-is-a-subprocess-or-charter-has-no-plugins.md) is that moment arriving,
and its own gate item 7 requires this re-opening in the same change as the ruling that triggered
it.** The whole proposition of a plugin boundary is that a plugin is *less* privileged than
charter. If that were true, the accepted race would stop being an accident nobody can exploit
without already having the operator's shell: it would become a way for a confined principal to
have charter write charter's own bytes to a path the plugin chose.

**It is not true, and that is the answer.** The operator ruled on 2026-09-22 to ship the plugin
runtime with **no OS sandbox**. A subprocess runs as the same user, with the same filesystem and
the same ability to `exec`; a plugin can write the plane directly without asking charter for
anything. So a plugin is not a principal confined below charter, nothing in charter makes one, and
the condition this record's third answer rests on still holds. The race stays out of scope, on the
grounds it was always out of scope on, and not because nobody looked.

**What has changed is that the clause is now load-bearing rather than hypothetical.** It has one
named trigger with a date on it, and the trigger is a sandbox rather than a plugin:

- **The day a sandbox lands** — Seatbelt on macOS, seccomp or Landlock on Linux, AppContainer on
  Windows, any of them, for any subprocess charter starts — the condition is false and this record
  is re-opened for real. Not amended again: re-opened, because the answer changes rather than the
  wording.
- **A plugin runtime without one does not re-open it**, and this amendment is written so that the
  next reader does not have to re-derive that from ADR 0041's honesty paragraph.
- **The `openat` rewrite is still the fix when it comes**, on the terms the section above sets: the
  whole core at once, with the external review decision 16 requires, and not one call site at a
  time.
