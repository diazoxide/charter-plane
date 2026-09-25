# charter-app, testing react-resizable-panels under vitest/jsdom: jsdom gi

_2026-09-22 13:33 · persistent_

charter-app, testing react-resizable-panels under vitest/jsdom: jsdom gives every element a size of zero, so the Group computes groupSize 0 and sets defaultLayoutDeferred — it NEVER applies defaultSize or defaultLayout, never fires onLayoutChanged, and lays every panel out as an equal flex share. So no vitest test can read a panel's width, a defaultSize or a remembered layout out of the DOM, and a test that appears to check a size is checking nothing. The split that works (charter-app#149): mock the library in one file to assert what it was TOLD (defaultSize, minSize/maxSize, collapse/expand/resize calls, the onLayoutChanged gate), use the real library in the others for everything that is about the TREE (which slot content lands in, order, unmounting, the separator staying in the group), and put the real widths in a scenario spec.
