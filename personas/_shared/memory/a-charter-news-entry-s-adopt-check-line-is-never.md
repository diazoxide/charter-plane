# A charter news entry's adopt:/check: line is never a shell string. The

_2026-09-25 · persistent_

A charter news entry's adopt:/check: line is never a shell string. The parser (crates/charter-core/src/news.rs, the SHELLISH set, ported from the retired news.py _SHELLISH) refuses any action that holds ; | & < > $ backtick ( ) backslash, a newline, or a single or double quote, and splits the rest on whitespace. So a command whose argument needs quoting cannot be an adopt: line: give it a fixed-word subcommand instead, or describe the step in prose. Before adding a news entry, check that its action parses against the live parser. Do not assume a skill's mention of 'adopt: manual' is handled; grep news.rs for it first.
