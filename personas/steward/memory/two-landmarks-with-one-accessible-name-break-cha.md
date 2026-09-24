# Two landmarks with one accessible name break charter-app's scenario spec

_2026-09-21 10:44 · persistent_

Two landmarks with one accessible name break charter-app's scenario specs silently: adding a second nav[aria-label='Workspaces'] (the new workspace strip, beside the sidebar's) made picker.e2e's nav lookup find the strip and read 'alpha4beta' off it. A strip is a tablist, not a landmark — use a div with role=tablist. Every role=tab query in app/src and app/e2e is scoped by the tablist's aria-label (Projects, Workspaces, Tabs) for the same reason.
