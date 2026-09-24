# cargo test --workspace in charter-app on this machine fails ~18 planegit

_2026-09-21 10:26 · persistent_

cargo test --workspace in charter-app on this machine fails ~18 planegit/wscmd tests with: error 1Password agent returned an error, fatal failed to write commit object. The operator global git config signs commits through the 1Password agent and those tests init real repos and commit. They pass when charter-core runs alone, so it is the agent rate-limiting under parallel load. Not a regression, invisible on CI which has no 1Password. Two forklock timing tests also flake under the same load.
