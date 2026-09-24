# Probing a harness through a user-declared command IS running that comm

_2026-09-25 · persistent_

Probing a harness through a user-declared command IS running that command. Found while planning harness profiles (2026-09-11): detecting a profile's wiring by invoking [*command, plugin, list, --json] would have executed a command nobody approved, from a diagnostic path that runs on its own. Rule for charter-app's harness adapters and project extensions (ADR 0048, ADR 0050): gate every probe on the same approval record a launch needs; an unapproved extension or profile is shown as not-approved-yet and is never probed.
