# Python's str.splitlines() is NOT a newline-delimited-JSON reader: it als

_2026-09-21 04:04 · persistent_

Python's str.splitlines() is NOT a newline-delimited-JSON reader: it also breaks on U+000B, U+000C, U+001C-U+001F, U+0085, U+2028 and U+2029, and serde_json escapes only the sub-0x20 group because the other three are ordinary characters inside a JSON string. charter-app's shellseg differential read the Rust example's stdout with splitlines() and reported 'answered 18,510 of 10,000 cases' the first time the fuzz alphabet included U+0085/U+2028/U+2029. Use split(chr(10)) for NDJSON.
