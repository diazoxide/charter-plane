# Upstream reports are filed under the Reporter's own GitHub identity

charter lets a Reporter file bugs and feature gaps against `diazoxide/charter-plane` from inside
a running session. Those issues are created with the Reporter's own `gh` credentials, so
they appear under their name — charter operates no service and holds no credentials of its
own for this.

The alternative was a charter-owned relay: charter POSTs a report to a hosted endpoint,
which files under a machine account. That was rejected because it makes the maintainer the
operator of an anonymous write endpoint into their own issue tracker, with the moderation
and abuse burden that implies, in exchange for infrastructure that must be paid for and
kept alive. Filing as the Reporter costs nothing to run, inherits GitHub's own spam
controls for free, and — the part that actually matters — produces an attributed issue the
maintainer can ask follow-up questions on.

## Consequences

A Reporter with no GitHub identity cannot file directly. charter supports GitLab forges,
so this is a real population, not an edge case. They get a prefilled
`issues/new?title=…&body=…` URL to click instead, which needs no service and reuses the
existing `util.urlenc`. That fallback doubles as the escape hatch when `gh` is missing,
broken, or rate-limited.
