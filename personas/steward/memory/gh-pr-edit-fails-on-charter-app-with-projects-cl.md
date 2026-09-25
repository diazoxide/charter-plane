# gh pr edit fails on charter-app with 'Projects (classic) is being deprec

_2026-09-25 12:19 · persistent_

gh pr edit fails on charter-app with 'Projects (classic) is being deprecated' (GraphQL projectCards). Update a PR body with the REST API instead: gh api -X PATCH repos/diazoxide/charter/pulls/N -F body=@file.md. GitHub native issue links work via REST too: POST issues/N/sub_issues (sub_issue_id=<database id>) and POST issues/N/dependencies/blocked_by (issue_id=<database id>).
