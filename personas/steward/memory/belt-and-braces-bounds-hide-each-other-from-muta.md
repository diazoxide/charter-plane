# Belt-and-braces bounds hide each other from mutation testing: in charter

_2026-09-22 12:09 · persistent_

Belt-and-braces bounds hide each other from mutation testing: in charter-app's readable_text, an fstat size bound plus a take(MAX_BYTES) on the read means dropping EITHER leaves the test green — the take truncates and the truncated JSON still fails to parse, so the settings test cannot tell 'refused' from 'truncated'. The test that gives the fstat bound a real bite is at a call site where truncation is visible and wrong: guest::mirrored copying half of somebody's .claude/agents/*.md into their repo. Measured on 2026-09-22; first mutation pass credited the fstat bound with nothing.
