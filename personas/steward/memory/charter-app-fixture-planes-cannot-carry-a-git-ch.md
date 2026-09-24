# charter-app fixture planes (tests/fixtures/planes) carry no git checko

_2026-09-25 · persistent_

charter-app fixture planes (tests/fixtures/planes) carry no git checkout — git will not track a .git inside a tracked path — so a test that needs a repository must create one in its own setup. Use 'git init' in place, not 'git clone': a clone records its origin's ABSOLUTE path, which differs from run to run. When a test compares facts about such a checkout, make the facts function FAIL when the checkout is absent, or it compares <none> against <none> and reports ok for any implementation at all.
