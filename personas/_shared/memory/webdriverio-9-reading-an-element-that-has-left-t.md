# WebdriverIO 9: reading an element that has left the DOM does not fail fa

_2026-09-27 02:26 · persistent_

WebdriverIO 9: reading an element that has left the DOM does not fail fast — its stale-element recovery (refetchElement) re-finds by selector+index and waits ~80 s before throwing the original error. So a POLLED read of a list that changes must be one browser.execute returning plain values (charter app/e2e/reading.ts, PR #507), never $$().getElements() then per-element reads.
