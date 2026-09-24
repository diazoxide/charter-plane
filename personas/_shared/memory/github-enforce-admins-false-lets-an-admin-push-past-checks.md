# GitHub branch protection: enforce_admins=false lets an admin's DIRECT 

_2026-08-30 10:39 · persistent_

GitHub branch protection: enforce_admins=false lets an admin's DIRECT PUSH through a required-status-check rule — git prints 'remote: Bypassed rule violations' on stderr and exits 0. With enforce_admins=true the same push is rejected GH006 'N of N required status checks are expected'. Measured on diazoxide/charter, 2026-08-30.
