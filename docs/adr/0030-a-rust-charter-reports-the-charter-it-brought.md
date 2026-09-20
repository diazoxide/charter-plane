# A Rust charter reports the charter it brought, and names the pin it does not meet

`charter version` in Python prints three numbers, and all three are facts about a **Python
package**: the `charter-cp` wheel `uv tool install` put on this machine, the release
`[charter] version` pins, and the newest release on PyPI. It compares the first two and exits
1 when they differ, which is the thing scripts and `charter doctor` read.

charter-app's `charter` is a different artifact. It has no wheel, no index and no
`uv tool install`; it ships inside a signed app and moves when the app moves. Two of the three
rows therefore have no subject, and the one number the binary does carry — the workspace's
`0.1.0` — counts a different thing from the number a plane pins. `charter/news.py`'s port ran
into this first: `--until` cannot default to `charter.__version__`, because `0.1.0` is below
every entry in the corpus and every range would be empty.

**`charter version` on a Rust charter reports the charter release this build's news corpus
comes up to, the build carrying it, and the pin as written — and when the pin is one the
corpus does not reach, it says so and exits 1, as charter does. It does not print an
`installed` wheel, it does not print a `latest`, and it does not reuse charter's *"in sync with
the lock"*.**

## The number that can be compared

`news::shipped_version()` is the newest released version the compiled-in corpus names. Its own
docstring already argues why it stands in for `charter.__version__`: a news entry travels with
the code that implements it, so the newest entry a binary ships is the newest thing that binary
brought. That makes it the same question `__version__` was standing in for, asked of the thing
that actually moved — and it is the only number in the binary on the same scale as a pin.

Comparing the workspace version against a pin instead would compare `0.1.0` with `0.62.1` and
call every plane adrift, forever. `charter doctor`'s `version lock` row declined exactly that:
it reports the pin and says the comparison *"is not ported to this charter yet"* rather than
comparing against the wrong number. This ADR supplies the right number; moving that row onto
it is the follow-up named at the end, and until it lands `version` is the surface that
compares and `doctor` is the surface that defers — which is stated in both rather than left
for a reader to discover.

## Why the verdict is not charter's sentence

Python says **in sync with the lock (X)** when the two numbers agree. A Rust charter that said
that would be claiming something it cannot substantiate. M2 is still porting commands: a binary
whose corpus reaches 0.62.1 is not everything charter 0.62.1 does, and a plane pinning 0.62.1
is pinning the Python charter's behaviour, not this one's. ADR 0013's rule — the absence of
information is not evidence of health — applies to charter's claims about itself, so the line
states what is true and stops:

    ✓ this charter brought 0.62.1, which is what this control plane pins.

and on drift:

    ! drift: this control plane pins 0.61.0, and this charter brought 0.62.1.

For the same reason the remedy is not charter's. `charter version sync` installs a published
`charter-cp` release over a machine-global binary; it cannot reach a binary inside an app
bundle, so pointing at it would be advice that does not work. What the operator can actually
do is move the pin, or run the charter-cp the plane names, and that is what is printed.

## What is compared, and what is not

The words legitimately differ, so the differential scenarios say so — and what they compare is
the **exit status**, in all three states: no pin (0), the pin met (0), drift (1). That is what
a wrapper branches on, and it is the half that must not diverge. A scenario whose stdout and
stderr both carry a `_differs` note and which compared nothing else would be a scenario
asserting only that both binaries ran; this one asserts the contract a script depends on, and
the fixture planes it runs on are chosen so that all three states are exercised.

The equality the scenarios turn on is a coincidence worth naming: at the pinned oracle commit
the newest news entry and `charter.__version__` are both `0.62.1`, so a plane pinning that
number is *in sync* for Python and *brought* for charter-app. They move together because both
come from the same commit — the vendored corpus and the oracle are pinned to it by
construction — but they are not the same field, and the day they part the pin-met scenario
goes red and says so.

## `version sync` and `version bump`

Both are registered, with charter's own flags, and both refuse by name. They were clap usage
errors, which is the failure M2.21 removed from `docs list` and `docs show`: a script that
calls a verb the tool being replaced has is owed a sentence, not a parser's exit 2. Neither can
be ported — one installs a wheel, the other installs and verifies one before writing the pin —
so the refusal is the implementation, and it names the mechanism rather than apologising.

The sentence it names the mechanism with is one constant, `adopt::THE_APP_MOVES_IT`, shared
with `charter update`'s refusal. Two commands describing one artifact in two paragraphs is two
paragraphs to keep in step, and the day they drift an operator gets two accounts of the same
binary.

## What this rules out

- Printing the workspace version as the answer to "which charter is this", anywhere.
- Comparing a `charter-cp` pin against `charter-app`'s own version, in any surface.
- An `installed` row or a `latest` row on a binary that is not installed from an index — there
  is no honest value for either, and a dash with a footnote is a row that teaches nothing.
- Saying *in sync with the lock*, or any other sentence that asserts parity with a charter
  release, while the port is partial.
- Pointing an operator at `charter version sync` from inside the app.
- A second sentence, in a second command, for the fact that the app is what moves this charter.
- Two surfaces comparing a pin two ways: when `doctor`'s `version lock` row stops deferring, it
  asks `adopt::version_report`'s comparison, not one of its own.

## The follow-up this leaves open

`charter doctor`'s `version lock` row still reports *"whether the charter serving this plane
matches the pin is not ported to this charter yet"*. It can now be ported, against
`shipped_version()`, and it should be — but that row's render is compared byte for byte against
Python's `doctor` in `tests/differential/doctor_scenarios.py`, and moving it is a change to
`doctor`'s output rather than to this decision. It is deliberately not in the same commit as
the decision it depends on.
