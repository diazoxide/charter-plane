# Repo names come from a FORGE, not from charter: org/.github is real an

_2026-09-25 · persistent_

Repo names come from a FORGE, not from charter: org/.github is real and common, and a leading dot fails charter's workspace/persona name rule. Never reuse the creation-time name validator to contain a repo name read from a file or a forge; containment is a different question (is this path segment safe?) and needs the permissive segment check. The name rule is ergonomics for things charter creates; it must not reject things the forge already created.
