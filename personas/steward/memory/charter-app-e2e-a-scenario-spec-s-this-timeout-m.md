# charter-app e2e: a scenario spec's this.timeout() MUST go on the describ

_2026-09-21 00:05 · persistent_

charter-app e2e: a scenario spec's this.timeout() MUST go on the describe(), never in the test body. WebdriverIO's executeAsync (@wdio/utils) snapshots this._runnable._timeout BEFORE the body runs and races the body against its own timer, rejecting with a bare 'Error: Timeout'. A this.timeout() in the body moves mocha's runnable and arrives too late, so the spec silently runs under mochaOpts.timeout. That is why 'fifty tabs (macos-latest)' was red 5 of 6 runs on 2026-09-20: it asked for 900 s and got 180, against a macOS runner needing 170-218 s (Linux 128-145 s). Guard: app/e2e/budget.test.ts. PR charter-app#116.
