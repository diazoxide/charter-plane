# A local bare repo can stand in for a forge in a charter test only if the

_2026-09-20 09:58 · persistent_

A local bare repo can stand in for a forge in a charter test only if the insteadOf rewrite is keyed on the HTTPS prefix while origin is the SSH form. Measured 2026-09-20 porting charter save to Rust (charter-app M2.5): remote get-url APPLIES url.<base>.insteadOf, so with origin https://github.com/acme/plane.git and a rewrite keyed on that same prefix, both charters read origin back as a file:// URL, answered 'origin isn't on a forge charter knows', and the scenario passed while pushing nothing. With origin as the scp form and the rewrite keyed on the HTTPS prefix, get-url returns the SSH URL untouched, charter rewrites it to HTTPS itself, and the transport lands on the bare repo for push and fetch alike. The un-rewritten value is config --get remote.origin.url; pushInsteadOf leaves get-url alone but does not cover fetch.
