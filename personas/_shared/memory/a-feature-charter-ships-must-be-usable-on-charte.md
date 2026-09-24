# A feature charter ships must work on charter's own plane, not only aga

_2026-09-25 · persistent_

A feature charter ships must work on charter's own plane, not only against synthetic configs. This failed twice in the retired Python CLI: a new charter.toml key reddened tests the moment the operator used it on this plane, and config tests compared the plane's committed arrangement against a constant, so registering a documented feature on this plane turned the suite red. charter.toml is a tracked file here, so committing a config that breaks tests turns CI red for everyone. Before adding a new setting or contribution to this plane's charter.toml, run the charter-app tests that read real plane config, and exercise every new key against this plane as well as against a fixture.
