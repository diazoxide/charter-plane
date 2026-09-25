# Repo sync must refuse three things the retired Python charter did sile

_2026-09-25 · persistent_

Repo sync must refuse three things the retired Python charter did silently (charter#1143, charter#1144): an ff-only merge that would overwrite an ignored local file the upstream starts tracking; treating a detached HEAD as a branch and moving it to origin/HEAD; and letting the operator's url.<base>.insteadOf config turn an https clone into ssh. charter-app's Rust sync refuses all three. Keep scenarios for each so a refactor cannot quietly reintroduce them.
