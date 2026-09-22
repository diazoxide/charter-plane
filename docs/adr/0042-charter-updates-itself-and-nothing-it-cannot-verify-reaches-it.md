# charter updates itself from two channels, and nothing it cannot verify reaches either

charter-app is one desktop app with the `charter` binary inside it, and
[ADR 0030](0030-a-rust-charter-reports-the-charter-it-brought.md) already says what follows
from that: *the app is what moves it*. What 0030 left open is how the app moves. Until this
record the answer was that it did not. `release.yml` built unsigned bundles on request, its
header said so, and its job summary told the operator to type `xattr -dr
com.apple.quarantine` to get past Gatekeeper.

On 2026-09-22 the operator asked for *"right release workaround, charter app update
functionality. automatic updates, update channels (dev/stable)"*. He was grilled on it and made
four decisions. This record states them, what they cost, and what had to be measured before
the third could be relied on.

## 1. Tauri's updater, against GitHub Releases, with no server

The app uses `tauri-plugin-updater`. It fetches a static JSON manifest published as a release
asset, downloads the bundle the manifest names, verifies a minisign signature over the
downloaded bytes, and only then unpacks it. There is no update server to run, patch, or keep
alive. The manifest is a file, and GitHub already serves files.

This is the standard mechanism for a Tauri app. It was chosen over writing one, and the choice
holds the rest of this record to the plugin's contract. The plugin does two things well that
charter must not undo, and leaves two things to the application that charter has to do itself:

- **It always verifies.** `minisign-verify` is an ordinary dependency of the plugin, not a
  feature. No build of it skips the check, and nothing in charter-app tries to.
- **It refuses plain HTTP** in a release build unless `dangerousInsecureTransportProtocol` is
  set. charter-app sets none of the plugin's `dangerous*` options, nor `allowDowngrades`, and a
  test fails if any of them appears in `tauri.conf.json`.
- **It does not know whether its public key is a key.** `pubkey` is a required string, and a
  placeholder deserialises fine. The failure then arrives at the *end* of an update, after the
  download. charter asks first (§3).
- **It does not bind a version to an artifact unless asked** (§3, `requireSignedVersion`).

`tauri-action`, the official GitHub Action, was the obvious alternative to extending
`release.yml`, because it builds, creates the release and writes `latest.json` in one step. It
was not taken for two reasons. It would replace a workflow that encodes several things measured
the hard way: the bundler deleting an intermediate `.app`, `ditto` to keep the executable bit,
the sidecar checks, `dpkg -c` dying of SIGPIPE under `pipefail`. And it writes the manifest
without the checks §3 needs. The manifest is instead written by `crates/release-manifest`, a
small crate whose every refusal has a test.

## 2. Two channels, two manifests, and only the operator tags

**stable** is cut from a `v*` tag and from nothing else. **dev** is cut from any green `main`.
Each channel is its own manifest file, `latest.json` or `dev.json`, not one file with a
channel field. The installed app reads whichever file the machine's setting names, and **the
default is stable**.

Two files and not one field, because the thing that keeps the channels apart is not charter's
code. It is GitHub's own `/releases/latest/download/` pointer, which resolves to the newest
release that is **not** a prerelease. Stable reads through that pointer. Dev reads a fixed
prerelease named `dev`, whose assets each green `main` replaces. However recent a dev build
is, it cannot become what a stable machine downloads, because GitHub will not call a
prerelease *latest*. The workflow checks before every dev publish that `dev` is still a
prerelease.

**Nothing in CI creates or moves a tag, and that is the operator's standing rule kept by
construction.** The rule is that the release is prepared unasked and tagged only on his word.
The two places a workflow could break it are both closed:

- The stable release is created with `gh release create --verify-tag`, which refuses unless the
  tag the operator pushed is already on the remote. It cannot mint one.
- GitHub has no release without a tag, so the dev channel needs one to hang on. **The operator
  creates `dev` once, by hand** (`docs/updating.md`, step 4). The workflow only ever uploads
  assets to it and edits its notes. If `dev` is missing, the run stops and prints the command.
  A workflow that could create this one tag would be a workflow that had taken the decision
  about whether to write tags, and that decision is not a workflow's.

A tag whose version disagrees with `Cargo.toml` is refused. The manifest announces the tag's
number and the app compares its own against it, so a mismatch would publish a release no
installed app could place. `main` carries the version that will be released *next*, bumped
right after each release, and a dev build is `X.Y.Z-dev.<run number>`. That makes it newer
than every stable release before it, older than the release it becomes, and newer than the dev
build before it.

**Only a green `ci` on a push to this repository's `main` publishes a dev build.**
`workflow_run` fires on every `ci` completion, red ones included, and its `branches: [main]`
filter matches a pull request *from a fork* whose branch happens to be called `main`. Without
the `event == 'push'` and same-repository conditions on the `plan` job, a stranger's pull
request would be built and signed with the operator's key.

### Where the channel lives: the machine store, which amends ADR 0034

The channel is a fact about *this installation*: one binary serves every plane on the machine
and cannot be on two channels at once. That is exactly
[ADR 0034](0034-charter-keeps-a-little-state-outside-every-plane.md)'s test for what may live
outside every plane: *about the operator or the machine, and false inside any one plane*. Its
deletion test passes too. Losing the file costs the operator one preference, which falls back
to stable, and every plane still opens with everything it had. So the channel is the **sixth
fact** in 0034's list (0040 added the fifth), and 0034 is amended to say so.

It was weighed against a small file of its own beside the store, and that lost on two counts.
It would need a second copy of the store's hardened read (`open_no_link`, `fstat` of the
descriptor, the size bound, the `0700` directory), which is a second place to get containment
right. And it would need a lock of its own, because the app and a `charter` in a terminal both
write it. `machine::update`'s `flock` already makes the store's read-modify-write one act
across processes.

**Every way of not knowing reads as stable.** A missing field, a word charter did not write
(`Dev`, `dev `, `nightly`), a store charter will not open, a platform with no store: all stable,
and a word that was dropped is recorded with its reason. The reader is exact, with no trimming
and no case folding. The two directions are not symmetric: reading a corrupt store as stable
costs one trip to the setting, while reading it as dev puts a machine on a stream cut from any
green `main` without anybody asking.

Until M6.4's status bar exists there is no window control for the channel, so
`charter update` names it and `charter update --channel dev|stable` moves it. That command
already opens with `THE_APP_MOVES_IT`, so the channel sits under the sentence that names the
app as the mover. The flag is charter-app's and not Python charter's: this binary moves as the
app moves, so it has a channel and a Python package does not.

## 3. Two signatures, held apart: minisign is mandatory, Developer ID yes, notarization no

Two different signatures are easy to conflate, and this decision depends on keeping them apart.

### minisign: mandatory, free, and what the updater checks

Tauri's updater verifies a minisign signature over the bundle before installing it. Without the
keypair there is no updater. The private key is a CI secret (`TAURI_SIGNING_PRIVATE_KEY`), and
its public half is committed in `tauri.conf.json`. **An updater without signature verification
is a remote-code-execution channel.** Nothing here builds one, and no switch makes verification
optional. The ways a missing key could otherwise slip through silently are each closed:

- **The bundler signs nothing, quietly, when the key is unset.** It writes no `.sig` and says so
  in one log line. So a publish with no key is refused twice: first by the workflow's `plan`
  job, before any building, and then by `release-manifest`, which reports a missing `.sig` as
  *an unsigned build* and never as an empty signature it might forgive.
- **The repository ships a placeholder public key**, because the plugin requires the field and
  the keypair is the operator's to generate, not this repository's. The placeholder is spelled
  so neither a person nor `updates::pubkey_usable` can mistake it for a key. The app checks the
  key *it was built with*, read back from its running config, before offering an update, and
  says in one sentence that it cannot verify rather than downloading first. The workflow
  refuses to publish while the placeholder is committed. A test accepts the placeholder or a
  real minisign key and fails on anything in between, including the comment line of the `.pub`
  pasted in place of the key line. That is the mistake that looks right.
- **A signature by the wrong key** (a secret rotated without the committed key, or the reverse)
  would be refused by every app on the channel at once. `release-manifest` runs the same
  `minisign-verify` call the updater makes, over the artifact's actual bytes, against the key
  in `tauri.conf.json`, and refuses to write the manifest. The one guard a CI run cannot give
  is whose key it is. Nothing inside a binary can audit its own trust root, and this record
  does not pretend otherwise.

**`requireSignedVersion` is on, and it is off by default upstream.** The manifest is fetched
over TLS but is **not signed**. The signature covers only the artifact. Without this setting,
anyone who can serve a manifest can pair an inflated `version` with the url and signature of a
genuine *older* release and push every machine back onto a build with a known hole. The
signature is valid; it just belongs to another version. With the setting on, the app reads the
version out of the signature's *trusted comment*, which minisign's global signature covers, and
refuses a mismatch. `release-manifest` checks the same pairing at release time, after
verifying the signature, because the comment is only trustworthy once the signature over it
has been checked.

**That setting needed a toolchain bump, and this was measured, not assumed.** The repository's
lockfile pinned `@tauri-apps/cli` 2.11.4. A signature from 2.11.4 carries
`timestamp:…\tfile:…` and nothing else, and that CLI has no `--app-version` flag. 2.11.5 is the
first release that writes `\tversion:X`, and `tauri build` sets it automatically. An app with
`requireSignedVersion` refuses every 2.11.4 signature with `MissingSignedVersion`, so turning
the setting on without the bump would have shipped an updater that rejects every update.
charter-app has published nothing yet, so every release it will ever have carries the version
and nothing is left behind by turning it on from the first one.

### Developer ID: required for a publish, and checked on the bundle

A published macOS build is signed with a **Developer ID Application** certificate
(`APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`). The workflow
does not trust that the secrets being set means the bundle is signed correctly. It runs
`codesign` on the built `.app` and on the `charter` sidecar inside it, and fails unless both
carry `Authority=Developer ID Application:`. A set-but-wrong secret (expired, the wrong
identity, an Apple *Development* certificate) otherwise produces a bundle signed with
something else, and nothing downstream notices until someone installs it.

**The team must not change.** macOS lets an app replace its own bundle in `/Applications`
without asking for App Management permission only when the new bundle is signed by the same
team. This is Apple's documented behaviour and was not measured here. It is one more reason the
certificate, like the minisign key, is chosen once and kept.

### Notarization: declined, and what that costs a first-time installer

No `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID` or `APPLE_API_*` is passed anywhere, so Tauri's
bundler never notarizes. **A browser-downloaded first install still meets Gatekeeper.** A
browser marks what it downloads as quarantined, and macOS 15 and later answer a quarantined app
Apple has not notarized with **"charter" Not Opened**, offering only *Done* and *Move to
Trash*. The way past is **System Settings → Privacy & Security → Open Anyway**, confirmed with
a password, or `xattr -dr com.apple.quarantine /Applications/charter.app` before the first
launch. The release job summary and `docs/updating.md` both say this, in those words.

What makes the decision workable is an asymmetry, and it was **measured on macOS 26.2 rather
than taken on trust**: **quarantine is applied by the downloader, not by the updater.** The
updater's macOS install (tauri-plugin-updater 2.12.0) downloads into memory with `reqwest`,
unpacks with the `tar` crate into a tempdir, and `rename`s the result over the installed bundle.
A replica of exactly that code was run on an ad-hoc-signed probe app:

| | `com.apple.quarantine` | `spctl` (Gatekeeper's verdict if asked) | launched via LaunchServices |
|---|---|---|---|
| installed copy, replaced by the updater's path | none | rejected | **yes** |
| a copy quarantined as a browser marks it | set | rejected | not attempted (it would put a dialog on the operator's screen) |
| **that same quarantined copy, then replaced by the updater's path** | **none** | rejected | **yes** |
| downloaded with `curl` | none | — | — |

The third row is the case that matters. A bundle that arrived quarantined and was approved once
is *replaced*, not modified: the new tree is renamed over the old, and the attribute leaves
with the old tree. Gatekeeper assesses quarantined files, so an update never meets the dialog.
The only attribute left on the new files is `com.apple.provenance`, which macOS 13 and later
add to everything a process writes, and which Gatekeeper does not block on.

**What was not tested, stated so nobody has to rediscover it.** A Developer ID signature, since
no certificate was available, and the probe was *ad-hoc* signed. That is strictly weaker, and
it still launched, so a Developer ID bundle has more standing, not less. The actual dialog text
on a quarantined Developer ID bundle is Apple's documented behaviour, not observed. A real
browser download was replaced by the attribute a browser writes, set by hand. The first release
cut under this record should confirm the dialog and the in-place update on a real machine, and
this section should be amended if either differs.

## 4. A plane's pin never blocks an update, and the skew is reported where it already is

The app updates itself and its sidecar. It never looks at a plane's `[charter] version` before
doing so, because one app serves every plane on the machine, and no plane's pin can speak for
the others. When the charter the app brought no longer matches a plane's pin, **`charter
version` already says so**, exits 1, and tells the operator how to conform the plane. That is
ADR 0030's output, and this record does not add a second way of describing the same skew.

Surfacing it in the window is M6.4's status bar, which does not exist yet. That is where both
halves go: the offer this updater emits (`update://checked`, `update://installed`,
`update://failed`), and the skew row, which asks `adopt::version_report` and nothing of its own.
The app's `updates.rs` names that hook in its module note.

## Automatic means it checks on its own; installing is one click

The operator asked for automatic updates. The app checks a minute after launch and every six
hours after that, and a new version raises a notification, because closing the window only
hides it (ADR 0025). It **installs when asked**. That is an implementation consequence, not a
re-opened decision: every session in the app is a child of this process, and installing on
macOS replaces the bundle and needs a relaunch. A silent install would be charter ending the
operator's work from a timer.

The timer never runs in a fenced (test) build, where the network is a reach outside the run's
own tree (charter-app#129), nor in a debug build, whose version is always `0.1.0`.

## What is published, and for whom

- **`darwin-aarch64`**, the `.app.tar.gz`. It is the bare key, because a Mac has one artifact.
- **`linux-x86_64-appimage`**, the AppImage. This is the *qualified* key, deliberately. Tauri
  looks for `{os}-{arch}-{installer}` first and `{os}-{arch}` second, so a bare `linux-x86_64`
  key would catch a `.deb` install and hand AppImage bytes to `dpkg`'s installer. With only the
  qualified key, a `.deb` install is answered *no update for this target*, which is the truth:
  `dpkg` owns it, and `apt` updates it.
- **An Intel Mac and arm64 Linux get no updates at all**, because the release matrix has no
  runner for either. That is a gap, named here and in `docs/updating.md`.

## What was rejected

- **An escape hatch for unsigned updates**, in any form: a flag, an empty key, a debug-only
  bypass. There is exactly one build path with no updater artifacts. A `workflow_dispatch`
  build on a repository that has no key yet sets `createUpdaterArtifacts: false`, is published
  nowhere, says *unsigned* in its summary, and never reaches `release-manifest`. It cannot
  reach a machine through the updater, because no manifest names it.
- **Silently skipping a stable publish when setup is missing.** A `v*` tag is the operator's
  deliberate act, and a tag that quietly did nothing is worse than a red run. A green `main`
  without a key *does* skip, with a warning, because otherwise every merge before setup would
  be a red twenty-minute build. Skipping a publish weakens nothing.
- **Notarization.** It was the operator's call, and its cost is stated above.
- **Exposing the plugin's own `updater:default` commands to the webview.** They would be a
  second install path that skips the channel and the key check. The app's four commands are
  the only surface.
- **A `latest.json` with a channel field**, rejected for §2's reason.

## Consequences, including the ones that cost something

- **The minisign private key is forever.** Every installed charter trusts the key it was built
  with. Lose it, and no installed app can ever be updated again: every operator reinstalls by
  hand. Leak it, and whoever has it can sign an update every installed charter accepts.
  `docs/updating.md` says to keep it and its password in a password manager.
- **Until the operator acts, nothing is published and no app offers an update.** The steps are
  in `docs/updating.md`: generate the minisign keypair, commit its public half, store three
  Apple secrets and two Tauri secrets, and create the `dev` release once.
- **A dev machine can see a few seconds of mismatch** while a build's assets replace the last
  one's. Assets are uploaded before the manifest, so the manifest never names a file that is not
  there, but it can briefly name a file that has just been replaced. That fails verification
  and installs nothing, which is the safe way to be wrong.
- **`cargo deny` allows one more licence**, `CDLA-Permissive-2.0`, for `webpki-root-certs`:
  Mozilla's CA list as data, which TLS checks the update endpoint against.
- The machine store gains a field, and a store with no channel is byte-identical to one written
  before this record. An older charter reading a newer store ignores the field.
