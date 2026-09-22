# Windows gets charter's guards, or it gets no charter

**Accepted by the operator on 2026-09-22, as written.** The evidence below is measured and
re-runnable, and the decision is settled: build on it.

Until that date this record opened by saying it was a draft needing his sign-off before anything
was built on it, and its decision was a proposal.
[ADR 0041](0041-a-plugin-is-a-subprocess-or-charter-has-no-plugins.md) was written against it in
that state, leant on it, and made the sign-off item 1 of its gate rather than cite a proposal as
a precedent — which is what surfaced that the rule had been quoted as settled elsewhere while it
was not. Nothing in the decision, the evidence, the issue list or the estimate changed at
sign-off. Only its standing did.

The work it describes is charter-app's, and the file is here because the decision is
charter's: this sequence runs `0001`–`0030` in one place, and a Windows decision kept in the
other repo would split it. That matters more than it sounds. `0029` and `0030` were both free
when this was drafted and were both taken while it was being written (charter#1153, the
footer; charter#1152, the version a Rust charter reports), so this is the third number it has
had. Several agents allocate from this sequence at once and nothing reserves one — worth a
glance at `git ls-tree origin/main docs/adr/` immediately before this merges.

ADR 0025 rebuilt charter as a desktop app on a Rust core and named three platforms: macOS,
Linux and Windows. macOS and Linux build, test and package. Nothing has ever been compiled on
Windows — charter-app#93 is the first time any of this code has run there — and the estimate
for the whole rebuild has been resting on that gap.

Every path below (`crates/charter-core/…`, `app/src-tauri/…`, `tests/differential/run.py`) is
in `diazoxide/charter-app`, and every bare `#nnn` is an issue there.

**The decision: Windows does not ship until charter's containment guards have a Windows
expression, and until then every guard that cannot be expressed there REFUSES rather than
degrades.** A platform charter declines to run on is a known quantity. A platform where
charter runs with its gate open is not, and the difference is not visible from inside the
app — which is exactly why it has to be decided here rather than discovered in a review.

This is not a decision to drop Windows. It is a decision about the order: the guards first,
then the port, and the guards are the part that needs a design rather than a translation.

## What is already in the tree, and why it is the problem

The core was written with Windows in mind. Before charter-app#93, eleven places carried an
explicit `#[cfg(not(unix))]` arm, and several more simply omit a `#[cfg(unix)]` block that
sets a mode. (That PR adds five more, in `hookwire`, and they are all refusals — which is what
this ADR is asking for everywhere else.)
**None of them has ever been compiled.** They were written to be right rather than left
broken, which was the correct instinct, and several of them are right. But a handful are not a
translation of the guard — they are the guard removed, with a comment where the guard used to
be:

- `contain::nofollow` is `options` unchanged. `open_no_link` and `create_no_link` exist to
  move the last component's link question from charter to the kernel, at the instant of the
  open; without the flag they are `no_link_on_the_way` alone, which is the version the module
  measured at 1881 escapes per 20,000 reads and 7600 per 20,000 writes. The three tests that
  prove the flag bites are `cfg(unix)`, so nothing on Windows goes red when it is gone.
- `plane::private_dir` and `plane::write_private` drop `0700` and `0600` — and `.charter/` is
  the directory the vault registry lives in.
- `profiletrust::write_private` drops `0600` from the record of the operator's consent to run
  a command.
- `usage::write_row` and `memstore::write_private` drop the same.

One is a guard that answers `true` to everything: `doctor::profiles::on_path` asks whether a
program is one this process could run, and off unix the answer is "it is a file". Every file
on `PATH` is then runnable, `PATHEXT` is not consulted, and the `program.contains('/')` that
decides whether a name is a path does not know about `\`.

Two more are not a removed guard but a coin toss that nobody has called:

- `glstate::alive` answers `false` off unix — every refresh lock reads as abandoned, so two
  refreshers can run at once.
- `news::alive` answers `true` off unix — every marker reads as live, so a stale one stops the
  check for ever.

Two modules for the same question with opposite defaults is not a platform decision; it is
two people guessing on different days.

## The guards, one at a time, and what Windows has instead

**Reparse points are not symlinks, and `is_symlink` does not say so.**
`contain::no_link_on_the_way` walks every component and refuses a `symlink_metadata` whose
file type is a symlink. On Windows the standard library answers that question for exactly two
reparse tags — `IO_REPARSE_TAG_SYMLINK` and `IO_REPARSE_TAG_MOUNT_POINT`. A path redirected
through any other tag reads as an ordinary file or directory: a Store app execution alias
(`IO_REPARSE_TAG_APPEXECLINK`), a OneDrive placeholder (`IO_REPARSE_TAG_CLOUD*`), a WSL
symlink (`IO_REPARSE_TAG_LX_SYMLINK`), a container's projected file. A plane inside a synced
folder is not an exotic case; it is where a lot of people keep their repositories. The walk
would pass, and `contain::resolved` — which asks `fs::read_link` the same question — would
resolve the path to itself and call it contained.

The Windows expression is a question about the reparse **tag**, not about `is_symlink`: refuse
any component carrying `FILE_ATTRIBUTE_REPARSE_POINT` at all. That is stricter than unix and
it is the right way round: charter's own paths are made by charter, so a reparse point
anywhere on the way has no honest use.

**`O_NOFOLLOW` has a near-equivalent that answers a different question.**
`FILE_FLAG_OPEN_REPARSE_POINT` does not refuse a reparse point; it opens the point itself
instead of following it. So the atomic refusal `open_no_link` gives on unix becomes "open,
then ask the handle whether it is a reparse point, then decide" — still atomic with respect to
a swap, because the second question is asked of the handle and not of the path, but a
different shape of code and a different error. The `O_NONBLOCK` half has no counterpart and
needs none: a Windows named pipe lives in `\\.\pipe\`, so the FIFO-at-an-arbitrary-path hazard
that flag exists for does not arise. `contain.rs` already says this arm "needs its own decision
at M4, not a guess now". This is that decision, and the answer is that it is a rewrite of the
pair rather than a flag swap.

**A mode bit is not an ACL.** `0600` and `0700` are how charter keeps the vault registry, the
trust record, the memory store and the usage trend off every other account on the machine.
Windows has no mode; it has a DACL, and the equivalent is creating the file or directory with
a security descriptor that grants the owner's SID alone. That is `CreateFileW` with
`SECURITY_ATTRIBUTES`, which is `unsafe` — and the workspace is `unsafe_code = "forbid"`. So it
is a crate (`windows-acl`, or `windows-sys` behind a small wrapper), a licence review, and a
test that proves the ACL bites, which means a second account on the runner. None of that is
hard. All of it is work that has not been costed, and until it is done the honest arm is a
refusal: charter cannot write private state on this platform.

**Windows resolves names charter believes are ordinary.** `contain::segment_ok` refuses a
separator, a NUL, `.`, `..`, an absolute path and a drive-qualified name — and it is used
*alone*, without the `^[A-Za-z0-9][A-Za-z0-9._-]*$` alphabet, on session ids, memory
identifiers, repo names on clone, worktree names and inventory entries. It does not refuse:

- a reserved device name — `con`, `nul`, `prn`, `aux`, `com1`–`com9`, `lpt1`–`lpt9`, with or
  without an extension. The alphabet does not catch these either: `persona_name_ok("nul")` is
  `true` today, and a session id of `nul` makes `.charter/sessions/nul.usage` the null device;
- a trailing dot — `alpha.` resolves to `alpha`, and the alphabet admits `.` deliberately, for
  names like `my-repo.v2`. Two workspaces the plane believes are distinct are one directory;
- an alternate data stream — `drive_qualified` catches `C:x` by looking at the *second*
  character, so `alpha:evil` passes `segment_ok` and names a stream of `alpha`. The alphabet
  does catch this one, so today it is reachable through the `segment_ok`-only callers and not
  through a workspace name;
- an 8.3 short name — `PROGRA~1` names a directory whose long name it does not begin with, so
  `contained`'s `starts_with` refuses a path that is in fact inside. Fail-closed, so a
  usability bug rather than a hole, but it should be known rather than discovered.

And the case rule runs the other way from the one `persona_name_ok` already documents:
personas are lowercase-only *because* a case-insensitive filesystem would let `DevOps` reach
`devops`'s files, but `workspace_name_ok` admits mixed case, so a committed plane holding both
`workspaces/Alpha` and `workspaces/alpha` cannot be checked out on Windows at all.

Every one of these is a string rule, which makes them the cheapest guards on this list and the
ones to write first — and each needs a test, because `segment_ok`'s existing tests run on a
platform where none of these strings mean anything.

**`ETXTBSY` does not exist, and its absence is not good news.** `crates/stand-in` is charter's
one answer to writing a program a test is about to run, and it is `#[cfg(unix)]` from top to
bottom: `/bin/sh` writes the bytes, `/bin/cp` copies the binary, `chmod 0755`, then a rename.
On Windows the crate compiles to nothing and every test that writes a stand-in fails to
compile. The failure it defends against is different too — a sharing violation, not `ETXTBSY`
— and the shape of the answer is different: there is no executable bit to set, the extension
decides, and a running image cannot be deleted though it can be renamed. This is a rewrite of
`stand-in`, not a `cfg` arm, and it gates most of the test suite.

**`env_clear()` means something else on Windows.** `worktree::git` clears the environment and
puts back only `HOME`, `PATH`, `GIT_TERMINAL_PROMPT` and `LC_ALL`. On Windows a process
started without `SystemRoot` cannot initialise winsock, so every git call that crosses a
network fails in a way that has nothing to do with git; `HOME` is not where git looks for a
global config (`USERPROFILE`, or `HOMEDRIVE`+`HOMEPATH`); the `PATH` it builds is joined with
`:` and needs `;`; and the four fixed directories it searches — `/usr/bin`, `/usr/local/bin`,
`/opt/homebrew/bin`, `/bin` — hold no `git.exe`, while the search looks for `git` and not
`git.exe` in any case. The guard's *reasoning* survives: an attacker-settable `PATH` must not
choose the binary. Its implementation does not.

**Before any of that: charter-app had no `.gitattributes`.** Git for Windows turns
`core.autocrlf` on by default, and almost every test here is a byte comparison —
`tests/fixtures/planes/**` is regenerated and diffed byte for byte, the differential compares
every file under two plane copies, `fixtures/corpora/*.raw` are raw terminal recordings full of
escape sequences. A checkout that rewrote a line ending would make all of them measure the
checkout instead of the code, silently and on one platform only. charter-app#93 adds
`* -text`; it marks nothing in the tree as changed, because everything here is already LF, and
it is the precondition for trusting any Windows measurement at all.

**And when a chat does start, it never says anything.** `harness::hook_command` builds each
armed state hook as `shell_quoted(binary) + " hook <word>"`, POSIX single-quoting, and on
Windows a hook command runs through `cmd.exe`, where `'` quotes nothing: the program is
literally named `'C:\…\charter.exe'` and there is none. A session's state comes from hooks
only (ADR 0018), so a Windows charter's board would never move and would have no way to say
why. #103.

**And a chat has no program to run.** `app/src-tauri/src/sessions.rs:296` is
`std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_owned())`. On Windows `SHELL` is
unset and `/bin/sh` is not there, so every chat fails to start before any of the above is
reached. The Windows shape is `%ComSpec%`, or PowerShell — which is a product decision as much
as a technical one, and it changes what a profile's command line means.

**A unix socket with `0600` on it is the hook channel.** There is no expression at all: Rust's
standard library does not surface `AF_UNIX` on Windows, and a named pipe's access is an ACL
again. charter-app#93 changes the `compile_error!` that used to stand here into a refusal, so
the crate can be built and the rest of the platform measured; that refusal is the shipped
behaviour until a named pipe with a security descriptor exists.

## What was measured

charter-app#93 adds a non-gating `windows-latest` job to CI — deliberately not one of the nine
required checks, because a required check on a platform with no port blocks every merge in the
repo including the ports that would make it green. It reports the whole `cargo check` error
list rather than its first line, and it runs `tools/windows-probe`, which asks a real ConPTY
the three things `session.rs` takes from a unix pty.

Run 35521489314, `windows-latest`, commit `0358f0d`. What it found, including the parts that
went the other way from the reading above.

**`charter-core`'s library is six errors from compiling, in two files.** That is the whole
list, and it is far better news than the reading predicted:

```
crates\charter-core\src\forge.rs:503  error[E0433] cannot find `unix` in `os`
crates\charter-core\src\forge.rs:504  error[E0599] no method named `mode` for `Permissions`
crates\charter-core\src\wiring.rs:770 error[E0433] unresolved module `rustix`   (×2)
crates\charter-core\src\wiring.rs:780 error[E0433] unresolved module `rustix`   (×2)
error: could not compile `charter-core` (lib) due to 6 previous errors
```

`forge::is_executable` reaches for `PermissionsExt` with no `cfg`; `wiring::Lock` calls
`rustix::fs::flock`, and `rustix` is a `cfg(unix)` dependency. Everything else in 63,000 lines
compiles. `stand-in` builds too — to an empty library, with one unused-import warning, which
is what makes the test targets a wall rather than the lib.

**It is a floor, not the list.** `cargo check --workspace --all-targets` stops at the crate
that fails, so `charter-cli`, `app/src-tauri` and *every test target* were never reached. The
next layer's errors only become visible once these six are gone.

**So they were removed, and the next layer is run 35522081785, commit `4cef5d9`.**
`charter-core`'s **library compiles on Windows.** The error list has moved one rung up, to
`charter-cli`, and it is six sites in three files:

```
crates\charter-cli\src\main.rs:1011       error[E0433] cannot find `unix` in `os`
crates\charter-cli\src\main.rs:1024       error[E0599] no method `process_group` on `Command`
crates\charter-cli\src\statusline.rs:171  error[E0433] cannot find `unix` in `os`
crates\charter-cli\src\statusline.rs:270  error[E0433] cannot find `unix` in `os`   (test)
crates\charter-cli\src\statusline.rs:272  error[E0433] cannot find `unix` in `os`   (test)
crates\charter-cli\tests\memory.rs:145    error[E0433] cannot find `unix` in `os`   (test)
```

Two of them are the hook channel again under another name — `statusline.rs` reaches for
`std::os::unix::net::UnixStream` directly rather than through `hookwire`, which is the second
copy charter-app#95 asks to remove. One is `detach_self`'s `process_group(0)`. Three are
tests.

These are fixed here too, and the same way: the surface check answers "no app is listening",
which the module's own doc already says means **render**; `detach_self` gets
`CREATE_NEW_PROCESS_GROUP`, with a comment saying plainly that it is the nearest thing and
not the same guarantee; and the two unix-only tests are marked as *missing on Windows*, not
as not applying.

**And the rung after that, run 35523107470, commit `9c63c3a`. This is the state this PR
leaves the platform in, and it is the number the estimate below should be read against.**

```
cargo build -p charter-cli
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 12.66s

cargo check --workspace --all-targets
crates\charter-cli\tests\repo_commands.rs:619  error[E0425] cannot find `program` in `stand_in`
crates\charter-cli\tests\init.rs:79            error[E0433] cannot find `unix` in `os`
```

**The `charter` binary builds on Windows.** `charter-core`'s library and `charter-cli`'s
binary both compile; `cargo build -p charter-cli` produces an executable. Everything a plane
runs as a command is, at the level of "it compiles", there.

What does not is the **test suite**, and the first of the two remaining errors is the wall
itself: `stand_in::program` is `#[cfg(unix)]`, and rustc says so — *"found an item that was
configured out"*. That is charter-app#101 arriving exactly where it was predicted.

Two things this PR's own `cfg` work leaves behind, said here so a reviewer does not have to
find them: three constants in `hookwire` and `session` became unix-only and are now marked so
(they were dead-code warnings for one run), and the empty-enum `Listener` produces four
`unreachable definition` warnings at its call sites in `crates/charter-cli/tests/statusline.rs`.
Warnings, because this job clears `-D warnings` — but the day Windows becomes a gate they are
errors, and that is the right moment to decide whether those tests should be `cfg(unix)` too.

**What is still not known, and how far the next rungs are.** `app/src-tauri` had begun
compiling when the run aborted, and `charter-core`'s own test targets were scheduled but not
proven either way — cargo stops handing out new units once one fails. Counted by hand, so the
next two runs have something to be checked against rather than discovered:

- **`charter-core`'s test targets: 14 of its 20 integration tests** reach for `stand_in::` or
  `std::os::unix`, plus the `#[cfg(test)]` modules inside the source. This is the stand-in
  wall (charter-app#101) and it is the big one.
- **`app/src-tauri`: 12 sites across three files** — `chats.rs` (8), `panels.rs` (2, its own
  inline stand-in, which is the duplication charter-app#81 already wanted removed) and
  `sessions.rs` (2, one of them the `SHELL` fallback above).

Each run moves the frontier by one rung. That is the shape of the remaining work rather than
a surprise, and it is why the estimate below counts test infrastructure separately.

**The `-c core.hooksPath=/dev/null` guard still bites.** Measured rather than assumed, and
this is a refutation of a worry rather than a finding: without the flag the planted
`pre-commit` ran and refused the commit (`THE-HOOK-RAN`, exit 1); with it the commit went
through (exit 0). Git for Windows maps `/dev/null`, and charter's hook guard survives the
platform unchanged.

**None of the four directories `worktree::git` searches exists**, as Windows resolves them —
`\usr\bin\git.exe`, `\usr\local\bin\git.exe`, `\opt\homebrew\bin\git.exe`, `\bin\git.exe`, all
absent. Git is at `C:\Program Files\Git\bin\git.exe`, which the `PATH` fallback also misses
because it joins `git` and not `git.exe`.

**The differential cannot run here, and now there is a measurement rather than a reading.**
`os.symlink` works (the runner is privileged), but `fcntl`, `termios`, `pwd` and `grp` are all
absent, `/bin/sh` does not exist, and `chmod 0o755` leaves a file at `0o666` — so the mode
comparison at the heart of the harness compares a number Windows does not keep.

**ConPTY: all four questions answered, over three runs, and the first two runs are kept here
because what they got wrong is part of the answer.**

- *Confirmed.* `drop(pair.slave)` does not end the output: the reader was still open ten
  seconds later, and reached EOF `20.01s` in — at the instant the **master** was dropped, and
  not before. `Session::when_it_ends` is built on the opposite.
- *Refuted.* Dropping a master did **not** block. `ClosePseudoConsole` returned at once in all
  three cases, which the reading had flagged as a hazard for the UI thread.
- *Blocked, by a fourth thing nobody was looking for — and it is the most important sentence
  in this ADR about sessions.* The exit code, the `259` case and the kill's reach were all
  reported as "unanswered" in the first run. The second run, with a control outside the pty
  and the bytes printed, says why in four bytes:

  ```
  no-pty-baseline: Some(7), stdout "hello", stderr ""
  pty-child-pid: Some(3184)
  exit-code: UNANSWERED — 10s and the program had not ended
  pty-said-by-then: 4 bytes, "\u{1b}[6n"
  ```

  The same `.bat`, the same working directory, run **without** a pty, exits `7` and prints
  `hello`. Run **through** ConPTY it produces `ESC[6n` — a cursor-position report request —
  and then nothing: no `hello`, no exit, for as long as it is watched.

  **ConPTY asks the terminal where the cursor is and holds the program until it is told.**
  `portable-pty` opens the pseudo console with `PSUEDOCONSOLE_INHERIT_CURSOR`, and that is the
  consequence. A unix pty owes nothing at startup; ConPTY owes an answer before the program
  runs a single line, and a session that does not pay it never starts at all. Every other
  question here was measuring that.

  This is a real constraint on `Session::start` and not a probe artefact. charter's engine
  does answer a DSR — `alacritty_terminal` raises it and `read_until_the_output_ends` calls
  `take_replies` on **every** read, with no view open — and `Session::start` already takes the
  writer and starts the reader before it spawns. So charter satisfies this today, by an
  ordering that was chosen for other reasons. On Windows it stops being an accident: anything
  that moved the spawn earlier, or started the engine lazily on first output, would produce a
  chat that opens and then does nothing at all, with no error anywhere. That belongs in a test
  whose name says so.

  A hypothesis worth recording as **wrong**: an almost-empty environment block would also have
  explained a program that never ran, but `CommandBuilder::new` calls `get_base_env()` and
  inherits, so that was never it.

**With the query answered, the other three answer too — run 35523107470, commit `9c63c3a`.**
The control and the questions are in one run, so each of these is a finding and not a
symptom:

```
no-pty-baseline: Some(7), stdout "hello", stderr ""
cursor-query: answered after 8.327ms (Ok(()))
exit-code: the program exited 7, and portable-pty reports 7
pty-said-by-then: 68 bytes, "\e[6n\e[?9001h\e[?1004h\e[m\e]0;C:\Windows\system32\cmd.exe\a\e[?25hhello\r\n"
eof-after-exit: NO, the reader was still open 10s after the program exited
eof-after-master-drop: YES, after 10.0537668s
exit-259: NO — 10s of try_wait and the program still reads as running
grandchild-ticks: 21 bytes before the kill, 28 just after, 56 eight seconds later
kill-reaches-descendants: NO — what the program started outlived the kill
```

- **The exit code is right.** Eight milliseconds after the reply, the program ran, printed
  `hello` and exited `7`, and `portable-pty` reported `7`. Nothing is wrong with the ordinary
  path once the query is paid.
- **`drop(pair.slave)` does not end the output.** Third run in a row. EOF arrives when the
  master drops and at no other time.
- **A program that exits `259` never exits**, now measured against a working control in the
  same run. `WinChild::is_complete` reads `STILL_ACTIVE` — which is 259 — as "not finished",
  so `Session::when_it_ends` would wait for ever on a harness that happened to exit with it.
- **A kill reaches the program and nothing it started.** The ticker the program launched kept
  writing after `TerminateProcess`: 21 bytes, then 28, then 56. On unix `session::end` kills
  the process *group* precisely so this cannot happen; there is no group here, and
  `portable-pty` puts the child in no job object. **Every chat closed on Windows would leak
  its whole subtree**, which for a harness is the harness's own children.

One more thing the preamble shows, worth knowing before a pane is pointed at it: ConPTY opens
with `ESC[?9001h` (win32-input-mode) and `ESC[?1004h` (focus reporting), neither of which a
unix harness turns on by itself.

## The work, as issues

Each of these is filed on charter-app, so this ADR decides the order rather than holding the
detail:

| issue | what it is | shape |
| --- | --- | --- |
| #95 | the hook channel: a named pipe, and an ACL where the `0600` was | design |
| #96 | `segment_ok` accepts four kinds of name Windows resolves elsewhere | string rules, cheap |
| #97 | every gate asks "is this a symlink", which misses most reparse tags | design |
| #98 | the `0600`/`0700` on charter's own state silently vanishes | design |
| #99 | ConPTY breaks the session lifecycle, and holds the program until the terminal answers `ESC[6n` | fix, sized |
| #100 | charter cannot find or run git, and two more lookups share the bugs | fix, sized |
| #101 | `crates/stand-in` is `cfg(unix)` end to end, so the tests cannot compile | rewrite |
| #102 | `glstate::alive` and `news::alive` disagree off unix | decide once |
| #103 | the armed state hooks are POSIX shell commands, so no chat ever reports | design |

## The options, and the one this takes

**A. Port mechanically and accept the degraded guards on Windows.** Rejected. The attacker
`contain.rs` exists for holds a *commit*, not a process — a committed
`workspaces/evil -> ../../elsewhere` travels to every machine that clones the plane. That
commit reaches a Windows clone too, and on that clone the gate is open. A guard that is a
comment on one of three platforms is a guard that is documented rather than enforced.

**B. Refuse on Windows until each guard has an expression.** Taken. The string rules are
cheap and can land immediately; the ACL, the reparse-tag walk and `stand-in` are each a small
piece of design with a test that has to be seen to fail. Until they land, a Windows charter
refuses to start rather than starting without them.

**C. Do Windows together with the descriptor-based containment rewrite.** This is the
recommendation for the *order*, not an alternative to B. ADR 0028 already puts an
`openat`-beneath-a-descriptor rewrite at M3 — "what is beneath this descriptor" rather than
"where does this name land" — and that is the same question Windows is asking. Handle-based
containment on Windows (`NtCreateFile` with `OBJ_DONT_REPARSE`, or `CreateFileW` with
`FILE_FLAG_OPEN_REPARSE_POINT` and a tag check) is the same shape as `openat` with
`O_NOFOLLOW`. Building a path-based Windows model now would mean building the model twice and
throwing the first away.

So: the string rules and the two coin-toss `alive` defaults are worth fixing now, because they
are cheap and they are wrong on every platform's terms. Everything else waits for M3 and lands
with the rewrite, and charter refuses on Windows in the meantime.

## What is left, in weeks rather than in adjectives

The estimate ADR 0025 rested on had no Windows number in it at all. This is one, with its
basis written next to it so it can be argued with. It is the work to reach a Windows charter
as trustworthy as the macOS and Linux ones — not a Windows charter that starts.

| | work | basis | estimate |
| --- | --- | --- | --- |
| **A** | the string rules (#96), one `alive` answer (#102), and the mechanical half of the program lookups (#100: `git.exe`, `join_paths`, `USERPROFILE`, the `SystemRoot` allowlist, `PATHEXT`) | each is a named function with a test that can go red on macOS today; and the *compiling* half of A is already done — the `charter` binary builds there | **3–5 days** |
| **B** | the guards that need a design: ACLs for private state (#98), the reparse-tag walk (#97), the named-pipe channel (#95) | each is a crate choice, a `deny.toml` licence review, and a test that needs a second account on the runner | **3–5 weeks** |
| **C** | the session lifecycle (#99): end from a wait on the handle, a job object for the kill, `259` | needs either an upstream `portable-pty` change or charter assigning the job after `spawn_command` | **1 week**, and it cannot be trusted until the scenario tests run on Windows |
| **D** | test infrastructure (#101): `stand-in` rewritten, and the 44 files that reach for `std::os::unix` | 1177 tests; 21 `#!/bin/sh` stand-ins across 12 files; symlink tests need Developer Mode or admin on the runner; `mkfifo` has no counterpart | **2–3 weeks** |
| **E** | not attempted and not costed here: the Tauri bundle, WebView2 bootstrapping, signing, the tray, single-instance, and the scenario suite on Windows | nothing has been built, so any number would be invented | **unknown** |

**6–10 weeks** for A–D, of which roughly half is test infrastructure that buys no shipped
behaviour — plus E.

**Taking option C above moves the number.** The reparse-tag work in B is the same work as the
`openat`-beneath-a-descriptor rewrite ADR 0028 already puts at M3, so doing Windows after that
rewrite rather than before it takes B down to the ACLs and the pipe. A–D then lands nearer
**4–6 weeks**. That is the strongest argument for the order this ADR recommends, and it is an
argument about cost rather than about safety, which is why it comes second.

## What this costs, stated so it is not a surprise

Windows is not a differential platform and will not become one. `tests/differential/run.py`
plants symlinks in almost every scenario, writes `#!/bin/sh` stand-ins and `chmod 0755`s them,
and compares each file's mode; the oracle it compares against is the Python charter, which
imports `fcntl` and `termios` and drives tmux. Windows can be a build-and-unit-test platform
and nothing more, which means the guarantee spec decision 15 gives on macOS and Linux — that
the two implementations leave the same plane — has no Windows counterpart, and the Windows
port is covered by unit tests alone. That is a real reduction in what is known about the
platform and it belongs in the estimate.
