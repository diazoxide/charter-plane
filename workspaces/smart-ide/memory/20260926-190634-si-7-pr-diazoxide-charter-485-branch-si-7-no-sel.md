# SI-7 (PR diazoxide/charter#485, branch si-7-no-select, commit efb8b09): 

_2026-09-26 19:06 · persistent_

SI-7 (PR diazoxide/charter#485, branch si-7-no-select, commit efb8b09): text selection is off at :root in App.css; one zero-specificity :where rule opts content in (fields except xterm's helper textarea, code/pre, .view-body, .trouble, [role=alert], .alert-detail, [role=dialog], [role=alertdialog]) and a later :where rule keeps controls (button, tab, menuitem, option, label, summary, and code/pre inside them) unselectable. app/src/selection.test.ts resolves the rules against surface fixtures and refuses a user-select declared anywhere else in App.css — a new selectable surface goes into the opt-in list, not a local rule.
