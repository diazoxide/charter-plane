# Piping a test run to tail (or head) makes the shell report the pipelin

_2026-08-21 10:41 · persistent_

Piping a test run to tail (or head) makes the shell report the pipeline's exit status, which is tail's 0, even when the suite failed. Capture the runner's exit code explicitly or read its summary line. Also never edit files a running suite reads (a version bump mid-run produced five spurious lockstep failures).
