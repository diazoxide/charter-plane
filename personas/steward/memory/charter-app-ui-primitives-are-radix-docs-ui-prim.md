# charter-app UI primitives are Radix (docs/ui-primitives.md, PR #137). Me

_2026-09-22 00:00 · persistent_

charter-app UI primitives are Radix (docs/ui-primitives.md, PR #137). Measured on the repo, not estimated: dialog+radio-group+checkbox+collapsible adds +60.6 kB to the bundle for Radix vs +84.2 kB for Base UI (@base-ui/react 1.8.0); adding menu+popover makes it +101.6 vs +165.9 kB. Both tree-shake and both ship ZERO CSS files, so the argument is cost and install size (2.3 MB vs 20 MB), not styling. Material was refused on visual language (Zed is the reference) plus Emotion's per-render serialisation against the 0.022 ms strip measurement in #133. Note @base-ui-components/react is the DEAD package name — it was renamed to @base-ui/react, and npm's 'latest' on the old name is a stale 1.0.0-rc.0.
