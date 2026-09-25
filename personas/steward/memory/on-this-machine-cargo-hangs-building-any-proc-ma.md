# On this machine cargo HANGS building any proc macro (serde/thiserror der

_2026-09-20 17:11 · persistent_

On this machine cargo HANGS building any proc macro (serde/thiserror derive) at _dyld_start, so the first CI push is the first compile — but rustfmt's binary is prebuilt and runs fine, and 'rustfmt --edition 2024 <file>' PARSES the file, so it catches every syntax error locally. What it cannot catch is what cost M2.11 two CI rounds: -D warnings. Two of them are predictable by hand — a binary crate's 'pub use' that nothing calls is an unused_imports ERROR, and clippy's manual_checked_ops fires on 'if total == 0 {..} else { 100*x/total }'. Check those by eye before pushing.
