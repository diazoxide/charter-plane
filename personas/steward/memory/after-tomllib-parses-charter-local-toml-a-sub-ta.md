# Once charter.local.toml is parsed, a sub-table written [harness.claude

_2026-09-25 · persistent_

Once charter.local.toml is parsed, a sub-table written [harness.claude.alt] and an inline table written enviroment = { CLAUDE_CONFIG_DIR = ... } under [harness.claude] are the same thing: a table-valued key inside the profile's table. So any rule that treats nested tables as dotted profile names must still validate a parent that has keys of its own, or a typo'd env table is silently dropped and the profile launches the default account. Settled rule (kept in charter-app crates/charter-core/src/profiles.rs): a parent holding only sub-tables declares nothing (built-in kept, children named by dotted spelling); a parent with its own keys refuses the nested table as an unknown profile key.
