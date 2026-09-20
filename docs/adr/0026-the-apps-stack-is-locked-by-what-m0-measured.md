# The app's stack is locked by what M0 measured

ADR 0025 chose Tauri 2, React and TypeScript for the UI, with a Rust core holding every
terminal headless on `alacritty_terminal`, and it named the condition for changing its mind:
GPUI "stays the fallback only if the M0 skeleton misses a limit a person would notice". The
skeleton exists. This is what it measures against the spec's limits, and the decision that
follows.

**The stack is locked as ADR 0025 chose it, and xterm.js draws with its own DOM renderer.**
One limit is missed and one is met with a hazard beside it; neither belongs to the drawing
layer, and both are recorded here rather than designed around.

## How it was measured

`node tools/bench.mjs` in charter-app at commit `2b85efc`, with nothing uncommitted — the run
records both, so a number can be tied to the code that produced it. On the operator's machine:
Apple M4 Pro, 14 cores, 48 GB, macOS 26.2, tmux 3.7c, Node v24.12.0, cargo 1.98.1, on
2026-09-17 from 00:03 local. Raw results: `target/bench/2026-09-17T20-03-53/results.json`.

The method is research §9.3, adapted: the limits are the perceptible ones the spec lists, and
tmux is re-measured beside the app as a reference, not a gate.

- **Release builds only.** A debug build's numbers say nothing about what a person feels. The
  app is built twice: as it ships, for cold start, and again with the `e2e` feature, which is
  what WebDriver can drive.
- **The frame is 150×42**, the size the recorded corpus was taken at, held there against the
  pane's own fitting.
- **The load is `fake-harness`**, replaying `fixtures/corpora/claude-code-session.raw` — 132 KB
  of real Claude Code output — ×16 for 2 MB and ×99 for 13 MB, and its synthetic
  harness-shaped output where a `?2026` animation is needed, because that recording has none.
- **A burst starts once the pane is watching** (`--wait-for-input`), since output written
  before the view opens arrives as a snapshot of the screen instead of as a stream.
- **"Painted" means the text has been parsed into the terminal's grid and one more frame has
  then been presented.** The pane hands xterm.js's `write` a callback, so the clock stops on
  the parse and not on the IPC message: arrival is not paint, because xterm.js drains its write
  queue on its own schedule.

What the numbers do **not** cover, stated once here rather than implied row by row:

- **Every throughput row is one sample**, as are the tmux rows. Run to run they move by about
  ±10%. The percentile rows say their sample count.
- **Memory is the app's own process.** A pane's terminal lives in WebKit's content process,
  which this does not measure, so "the app at 140 MB" is the native side alone. The
  idle-hidden-session row is unaffected: a hidden session has no pane, and its cost is its
  terminal in the core.
- **The keystroke rows drive xterm.js's `input`**, which is what a key press turns into once
  the browser has delivered it. The browser's own key-event leg — a few milliseconds, at most
  one frame — is outside them.
- **The benchmark polls the window while it measures**, about twenty script evaluations a
  second, and brings the window forward. Both cost the app, not the limit, so they make these
  numbers pessimistic rather than flattering.
- **Nothing can draw more often than the display changes.** An earlier run read the DOM
  renderer at 22 draws a second because the display had dropped to 26 frames a second with
  nobody at the machine. Every run now holds the display at full rate and refuses to measure
  below 50 frames a second; both arms below were at 60.

A benchmark of a window also needs the window drawn at all: covered, asleep or on a locked
screen, WebKit hands out no frames, and a measurement waiting for a paint waits forever. The
runner brings each window forward, holds the display awake, and skips the paint measurements
with a reason rather than reporting zeros.

## What it measured

| Limit | Measured | |
| --- | --- | --- |
| **Live sessions: 50** | 50 running, 49 of them streaming; harnesses using 605% CPU between them; the app's own process at 144 MB | met |
| **2 MB burst: no freeze, input and other panes responsive** | painted 82 ms after the first byte (25.8 MB/s); longest frame 42 ms | met |
| **13 MB burst: the same** | 460 ms (28.4 MB/s); longest frame 52 ms; in the pane beside it, the one keystroke that landed while the burst was still arriving took **110 ms**, and the other nineteen took 23–34 ms | met — no freeze, one hitch |
| **Keystroke to screen ≤ 50 ms while 49 others stream** | worst 26 ms with 49 streaming at ~1 MB/s each, worst 26 ms with 49 flat out (30 samples each) | met |
| **Tab or pane switch ≤ 100 ms** | back to a light tab worst 39 ms; to a tab whose session holds all 5000 lines of history worst 48 ms; back to the typed tab under the 49-session load worst 41 ms (10 samples each) | met |
| **Hook call ≤ 50 ms** | `charter hook pretooluse` through Python charter: **p50 107.6 ms**, worst 114 ms (30 samples) | **missed here; met in M1.3** |
| **Cold start ≤ 2 s** | p50 370 ms to the first frame on screen; worst 510 ms, the first launch after the build and the only one cold on disk | met on macOS; **missed on a Linux whose desktop portal cannot start** (26–31 s) — see the amendment below |
| **Idle hidden session ≤ 50 MB at the shipped scrollback cap** | **20.2 MB** each: fifty sessions holding 5000 lines at 150 columns took the app's process from 118.9 MB to 1129.7 MB | met |
| **`?2026` animation ≥ 30 fps** | **52.4 draws/s** for a 3 KB repaint written whole, **52.0** for a 10 KB full-screen repaint written whole, both against a 60 fps display; **1.0 draws/s** when the writer pauses inside an open update | met, with a hazard recorded below |
| tmux, as a reference | 26.0 MB/s at 2 MB, 26.1 MB/s at 13 MB, in a 150×42 window with a client attached through a pseudo-terminal | the app is above it |

Two more numbers that no limit asks for, because they are what a person does:

- **Opening a pane by splitting**, until the new pane has painted: p50 55 ms, worst 117 ms with
  a handful of panes. Splitting on up to twenty panes costs far more — p50 191 ms, and 1380 ms
  for the seventeenth — because every split re-lays out every pane.
- **Twenty panes on screen at once** all drew, each with its own live session.

## The renderer is xterm.js's own, not WebGL

The research expected WebGL and warned that WebKit caps a page at 16 WebGL contexts (§5.1), so
both were measured, in the same run, on the same machine.

| | DOM | WebGL |
| --- | --- | --- |
| 13 MB burst | 28.4 MB/s | 28.0 MB/s |
| 2 MB burst | 25.8 MB/s | 22.5 MB/s |
| 132 KB corpus, first byte to painted | 50 ms | 40 ms |
| Keystroke with 49 streaming, worst | 26 ms | 34 ms |
| Switch to a light tab, p50 | 32 ms | 40 ms |
| Switch to a tab with 5000 lines of history, p50 | 47 ms | 49 ms |
| Splitting up to twenty panes, p50 / worst | 191 / 1380 ms | 108 / 538 ms |
| The app's process with 50 sessions | 144 MB | 167 MB |
| Per idle hidden session | 20.2 MB | 20.9 MB |
| `?2026`, repaints written whole | 52.4 draws/s | 51.6 draws/s |

**Both arms meet every limit**, and neither is faster at the same things. WebGL paints a first
screen sooner and builds a many-pane layout in about half the time; the DOM renderer switches
tabs sooner, answers a keystroke under load sooner, and costs 23 MB less. So this is not a
speed decision, and priority 3 does not decide it — **priority 1 does: the DOM renderer is
what xterm.js does by itself.** No addon, no GPU context per pane, nothing to fall back from.

The context cap did not bite either way: **twenty panes each kept a live WebGL context, none
fell back.** That is worth knowing and changes nothing today.

`@xterm/addon-webgl` stays in the tree behind `app/src/renderer.ts` — 113 KB of the shipped
bundle that the shipped build never loads, because the switch is only reachable from the
benchmark. It is kept so the arm can be re-measured rather than re-argued: **if many panes on
screen at once becomes an ordinary way to work, the twenty-pane row above is the lever to
pull.**

## The hook call is missed, and not by this stack

**Met on 2026-09-18, in M1.3, earlier than this ADR expected.** The Rust binary answers
`charter hook stop` at **p50 1.7 ms**, worst 2.2 — 30 samples, the same method, now an arm of
`node tools/bench.mjs --only hook` in charter-app. The like-for-like Python row measures
93.2 ms on that run (`charter hook stop`, not the guard). Everything below stands as the
reasoning; only "M3 is where it is met" was wrong, and it was wrong because the EVENT path
turned out to be separable from the guard, which is still Python's and still misses the limit.

`charter hook pretooluse` costs 107.6 ms at the median. That is the Python start ADR 0025
already counted as a reason for the rewrite, measured again: the hook path today is Python
charter's, and no drawing layer changes it. The Rust `charter` binary answers `charter root` in
**1.8 ms** on the same machine, which is the floor the limit will be held to once M2 and M3
move hooks off Python. **The limit stays missed until then, and M3 is where it is met.** It is
not a reason to reopen the stack.

## The `?2026` hazard, and the decision it needs

xterm.js skips any render that falls while a synchronized update is open
(`RenderService._renderRows`), and forces one only on a one-second safety timeout. Measured:

- A repaint written whole, 3 KB or 10 KB: **52 draws a second** against a 60 fps display, well
  past the 30 the limit asks.
- Repaints written 4 KB at a time with 16 ms between writes, so an update stays open across
  frames: **1.0 draws a second** — the pane updates on the safety timeout and nothing else.
  This is xterm.js#6071, and it is why the spec lists the limit at all.

What decides it is not that a repaint reaches the pane in pieces: **every repaint does.** A
repaint written in one write arrives as roughly one message per kilobyte — a 3 KB repaint in
about five messages, a 10 KB one in about eleven, a 32 KB one in about thirty-three — because
that is what the pseudo-terminal hands over, one message per read (`session.rs`, a 64 KB
buffer). Those arrive back to back and are parsed before the next frame, which is why the
prompt cases draw at 52/s. **A writer that opens an update and then pauses is the case that
stalls**, and no harness is known to do it: the recorded Claude Code session uses no `?2026` at
all.

It is still a hazard the app can close for good, in the core rather than the UI: **the core
already parses every session's output and knows when an update is open** — `alacritty_terminal`
exposes vte's sync state, which `engine/alacritty.rs` already uses — **so it need never hand a
pane a chunk that ends inside one.** That is the recommendation, and it belongs to M1. It needs
a deadline of its own: a harness that opens an update and never closes it must not hold its
pane's output for ever, which is the one thing xterm.js's one-second timeout does get right.

GPUI would also make the hazard impossible, by not having xterm.js. That is the trade ADR 0025
weighed and priced, and one animation shape that no harness writes does not change it.

## The scrollback cap

The spec left open "the scrollback cap that the idle-session limit is measured at". It is
**5000 lines**, `SCROLLBACK` in the app, and it is measured: a hidden session holding 5000
lines at 150 columns costs **20.2 MB**, against a 50 MB limit. Fifty of them add about 1.01 GB
to the app's process, which is the number to weigh before raising the cap — the limit is per
session, and the product's scale is fifty.

## What would reopen this

- A limit a person notices that the drawing layer causes and the core cannot close. The
  `?2026` stall is the only candidate so far, and the core can close it.
- Many panes on screen becoming an ordinary way to work: that is the one thing the DOM renderer
  is measurably worse at, and it is a switch in `renderer.ts`, not a change of stack.
- Tauri's WebKit refusing contexts or frames at a pane count the app needs. Twenty panes, each
  with its own session, draw today.
- A harness whose output the app cannot keep up with. It is at 28 MB/s on a 13 MB burst, above
  tmux on the same machine, with the parse into the grid inside the measurement.

Until one of those happens, GPUI is not the fallback it was: it is an option that costs a
rewrite of the UI and buys nothing the limits ask for.

## The benchmark

`node tools/bench.mjs` in charter-app, with a line in its README. It builds what it needs,
measures cold start, the hook call, tmux and the window — the window once per renderer arm, one
WebdriverIO run per spec file so no spec measures what the one before it left running — and
writes `target/bench/<time>/results.json`, with the commit, the machine and the tool versions
beside the numbers. Every number here can be taken again with one command, which is the point
of it.

## Amendment, 2026-09-19: cold start is met on macOS and missed on a Linux whose portal cannot start

The cold-start row above was measured on macOS only. On Linux the same app took 25 s to reach
its own `setup` (charter-app#24), twelve times the limit, and nothing recorded it. This
amendment records the miss on Linux, names its cause, and says which milestone owns it.

**How it was measured.** On GitHub's `ubuntu-24.04` runner, charter-app at `f93129b`, a debug
build (`npx tauri build --debug --no-bundle`) under `xvfb-run`, in an empty plane. The runner
was used because it is exactly the kind of machine the issue is about. Each condition was
launched three times, timing to the window's first frame (`CHARTER_BENCH_LOG`) and to the
startup markers (`CHARTER_LAUNCH_LOG`). To name the wait, the app was also attached with `gdb`
during it and the session bus was watched with `dbus-monitor` while it started. A debug build
on a shared runner is not comparable with the release build on the operator's machine, so the
fast rows below show the order of magnitude, not a Linux figure to hold the limit against. The
slow row is two timeouts and does not depend on the build.

| The session bus | First frame, 3 launches | |
| --- | --- | --- |
| A working one (`dbus-run-session`) | 706 ms, 702 ms; 2898 ms for the first launch, the only one cold on disk | met |
| **The runner's own: present, with an activatable desktop portal that cannot start** | **30.5 s, 30.5 s, 26.4 s** | **missed** |
| None reachable (`DBUS_SESSION_BUS_ADDRESS` pointing at nothing) | 482 ms, 463 ms, 526 ms | met |

**The cause is two waits, and charter makes neither call.**

1. **25.0 s inside `tauri::Builder::build()`.** Tauri's event loop (tao 0.35) creates a
   `GtkApplication` and registers it. At startup GTK 3 looks for a session manager
   (`org.gnome.SessionManager`, then `org.xfce.SessionManager`, both with auto-start off, and
   both answered at once with "no such name"). With neither found, it creates a proxy for
   `org.freedesktop.portal.Desktop` **with auto-start on**. On the runner that name is
   activatable, so the bus starts `xdg-desktop-portal`. The portal then waits for its GTK
   backend, `xdg-desktop-portal-gtk`, which cannot start without a desktop session. The app's
   `StartServiceByName` got no reply until D-Bus's default 25-second timeout ran out: sent at
   `…455.4427`, next traffic at `…480.4486` on the bus monitor. The backtrace during the wait
   is `g_dbus_proxy_new_sync` ← GTK ← `g_application_register` ←
   `tao::…::EventLoop::new_gtk` ← `tauri::Builder::build` ← `charter_app_lib::run`.
2. **5.0 s while the window is created**, before the app's `setup` runs. WebKitGTK asks the
   same portal for `org.freedesktop.appearance` / `color-scheme` and gives up on its own
   5-second timeout. Run 3 above skipped most of this wait, and its first frame was sooner by
   the same amount.

**The issue's suspect, `tauri-plugin-single-instance`, is cleared.** Its
`RequestName("dev.charter.app.SingleInstance")` is on the bus at `…480.4545`, after the wait
and answered at once. **"Without a session D-Bus" is the wrong description:** a machine with
no session bus at all starts in under 0.6 s, because every bus call fails immediately. The miss
needs a session bus that is up **and** a desktop portal that is installed and activatable but
cannot come up. CI runners, containers with desktop packages, and a remote X session without a
desktop all fit that description. A full Linux desktop, where the portal is already running,
would answer straight away. That follows from the trace and was not measured on a desktop.

**Why it is not fixed now.** The wait belongs to GTK and xdg-desktop-portal, reached through
tao, and charter cannot switch the proxy's auto-start off. The only lever inside the app is
process-wide: give the app no session bus when the portal looks dead. That would also remove
the three things charter uses the bus for, and one of them is a guarantee the core depends on.
The single-instance name is what makes it safe for `hookwire` to remove a stale hook socket at
startup (charter-app `crates/charter-core/src/hookwire.rs`: "there is no second live app whose
socket this could be"). Notifications and the tray would go as well. Trading a startup delay
for two live apps on one plane makes the product worse, not faster.

**The decision.** The 2 s cold-start limit is **met on macOS** (p50 370 ms, above) and
**missed on a Linux whose session bus has a desktop portal that cannot start** (26–31 s), with
the cause named above and tracked in
[charter-app#24](https://github.com/diazoxide/charter-app/issues/24). It belongs to **M4**,
where Linux becomes a platform charter ships for, alongside the rest of the Linux desktop
integration. At that point either tao or GTK can register without the portal proxy's
auto-start, or charter finds a narrower lever than removing the whole bus. The limit itself
stays at 2 s: an operator waiting half a minute for a window is noticing, and the number is
right. M1 is macOS, and nothing in M1 depends on this.

The scenario job keeps running the Linux relaunch test under `dbus-run-session` (charter-app
#23). That is a Linux desktop with a working bus, and passing it proves nothing about this
miss.

**Addendum, 2026-09-20: the miss is no longer silent.** Everything above stands — the trade is
still the wrong one to take and the fix is still M4's. What has changed is the part charter
owns. The worst of a 26-second start was that nothing said anything: no window, on some
desktops not even an icon, and the only record of the wait was a marker behind an environment
variable that nobody sets before they have a reason to. charter-app#108 makes the wait visible
on the two channels that exist before there is a window. At the 2 s limit the app writes one
line to standard error naming what it is waiting for, which is what a terminal launch, a
`.desktop` file's journal and a CI log have; and when the window does arrive it says on screen
how long the start took and why, which is the only channel an operator who clicked an icon has.
The cause is named on Linux alone and hedged even there, because a slow Linux start can also be
a cold disk.

This changes the caveat, not the row: **cold start is still missed** in this configuration. An
operator who is told why they are waiting is still waiting.
