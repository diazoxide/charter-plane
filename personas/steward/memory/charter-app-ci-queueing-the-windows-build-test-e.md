# charter-app CI queueing: the 'windows (build, test, evidence only)' job

_2026-09-21 04:14 · persistent_

charter-app CI queueing: the 'windows (build, test, evidence only)' job runs a full 'cargo check --workspace --all-targets' and is the last job of a run to finish — so the ci.yml concurrency group (ci-$github.ref) holds the NEXT push's run at 'pending' for many minutes even though every required check has already reported. 'gh run cancel <previous run id>' does not land immediately either; the Windows step finishes first. Budget for it when doing PROOF-ONLY mutation rounds, where each round is a push, or cancel the superseded run as soon as its required checks are in.
