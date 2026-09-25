# charter-app hand-mutation proofs: ci.yml is 'on: pull_request' + 'push:

_2026-09-20 19:13 · persistent_

charter-app hand-mutation proofs: ci.yml is 'on: pull_request' + 'push: branches: [main]' only, so pushing a PROOF-ONLY probe BRANCH fires no CI at all, and ci.yml has no workflow_dispatch (adding one on the probe branch does not work either — dispatch triggers must already exist on the default branch). The only way to get a hand mutation onto CI is to push it onto the PR's own branch and revert it with the next commit; the squash-merge hides the PROOF ONLY commits from main. mutants.yml has workflow_dispatch but runs cargo-mutants over charter-core only, so it does not cover app/src-tauri or your own hand mutations. Measured 2026-09-20 on PR #87.
