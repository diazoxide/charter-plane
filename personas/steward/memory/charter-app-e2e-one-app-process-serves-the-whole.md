# charter-app e2e: one app process serves the whole wdio run, so a spec's

_2026-09-27 01:35 · persistent_

charter-app e2e: one app process serves the whole wdio run, so a spec's after() that closes its project with a bare ask("close_plane") leaves the window drawing that dead project in front and breaks the NEXT spec (workspace-explorer saw an empty strip). Close through the tab's × (or the window's own close request) and assert the project left both open_planes and the strip. And a palette row that closes its own window can surface as WebDriver 'Channel closed'/'No window could be found' — ignore only that answer and still assert the window went (PR #504).
