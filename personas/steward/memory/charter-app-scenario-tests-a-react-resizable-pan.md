# charter-app scenario tests: a react-resizable-panels resize CAN be drive

_2026-09-22 13:49 · persistent_

charter-app scenario tests: a react-resizable-panels resize CAN be driven from a wdio spec without a pointer drag — click the 1px '[role="separator"][aria-controls="<panel id>"]' to focus it (tabindex=0) and press ArrowRight/ArrowLeft; the library reports it with isUserInteraction true, exactly as it reports a drag. Verified green on BOTH macos-latest and ubuntu-24.04 (PR #149). A pixel drag path is timing-bound on a shared runner and 'scenario tests' is a required check, so the keyboard is the one to use. One app process serves the whole run, so a spec that changes a width must put it back.
