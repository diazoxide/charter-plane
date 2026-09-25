# charter-app's ci.yml triggers on pull_request and pushes to main only,

_2026-09-25 · persistent_

charter-app's ci.yml triggers on pull_request and pushes to main only, so a PROOF-ONLY probe branch gets no CI at all. To watch a mutation go red without opening a PR, add .github/workflows/probe.yml with 'on: push' on the probe branch itself (copy the jobs you need from ci.yml, e.g. the rust test job); it lives only on that branch and is deleted with it.
