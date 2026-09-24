# charter-core has 43 local test failures on this machine that are environ

_2026-09-23 04:30 · persistent_

charter-core has 43 local test failures on this machine that are environmental, not regressions: they panic with '1Password: agent returned an error / fatal: failed to write commit object'. The operators global VCS config turns on commit signing through the 1Password SSH signer; the repo config overrides it off, but those tests create fresh temporary repositories that inherit only the global config. CI is unaffected. Check this before believing a red suite here.
