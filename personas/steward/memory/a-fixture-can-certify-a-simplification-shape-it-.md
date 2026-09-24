# A fixture can certify a simplification: shape it to hold the case that C

_2026-09-17 19:01 · persistent_

A fixture can certify a simplification: shape it to hold the case that CONTRADICTS the implementation. Measured 2026-09-17 on charter-app#12 — the Rust find_root implements only 'nearest charter.toml wins', and my fixture's one clone carried no manifest, so the wrong rule and the right rule agreed and the test passed. A reviewer caught it. Fix: clone a repo that carries its own charter.toml (charter bug #200's case), pin today's behaviour in one test and assert the spec's in an #[ignore]d one. Second half of the same lesson: with both fixture manifests truncated to 0 bytes every test still passed — a test that only checks a filename exists tests itself, so read content.
