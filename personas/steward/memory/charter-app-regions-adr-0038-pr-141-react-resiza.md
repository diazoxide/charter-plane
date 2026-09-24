# charter-app regions (ADR 0038, PR #141): react-resizable-panels v4 THROW

_2026-09-22 02:03 · persistent_

charter-app regions (ADR 0038, PR #141): react-resizable-panels v4 THROWS from a document listener when a Panel leaves a mounted Group — 'Panel constraints not found for index N', because a live Separator recalculates its aria values against the constraint list the panel just left. Clamping the panel's minSize/maxSize to 0 throws the same way (changing a constraint re-registers the panel and a recalc lands in the gap). The only thing that works is constant constraints written once plus collapsible + panelRef.collapse()/expand(); render the children conditionally so the content still unmounts. Found in jsdom, but it is a layout-math/registration race, not a jsdom artefact.
