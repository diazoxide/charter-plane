---
version: unreleased
headline: `charter recall`, `charter change list` and every other reader of memory or changes name a directory they could not read, where they used to say there was nothing in it
---

A memory directory or a `changes/` charter was not allowed to list looked empty. At mode 000
`charter recall` searched around it and said:

```
• No memories match 'keycloak' across workspace, persona, shared, refs.
```

`charter change list` said `No changes in workspace 'alpha'`, `workspace recall` said the
workspace had no memories yet, and the session briefing counted `0 own`. A search that did not
look read the same as one that found nothing.

Now each names the directory it could not read, in the sentence `charter doctor` already uses,
and does not say the search or listing is complete:

```
✗ workspaces/alpha/memory cannot be checked — restoring read access to it clears this.
• No memories match 'keycloak' across workspace, persona, shared, refs; 1 base(s) not searched — charter could not read them.
```

- `charter recall`, `charter persona recall` and `charter workspace recall` still show what
  the other memory directories hold.
- `charter change list` exits 1, as it does for a record it could not read. `charter doctor`
  names the `changes/` beside the changes it did read.
- `charter doctor`'s `memory indexes` row names each memory in a directory at mode 666 (its
  names listed, the files not reachable). It used to call that an index charter will not touch.
- `persona optimize` and `workspace optimize` name it and go on to the next directory. With
  `--apply` they do not change anything in a directory they could not list.
- The session briefing shows `? own` and the sentence, not `0 own`.
- `charter docs` leaves README's persona roster as it is and names the directory, where it
  wrote `0` memories for that persona.
- Commands that have no partial answer to give, such as `persona dedupe`, `persona stats` and
  `ws todo`, print the sentence and exit 1. They used to report nothing to deduplicate, a
  dormant persona or no open todos.

A symlink loop gets `fix the symlink loop at …` in place of the read-access remedy. The same
answer on Python 3.11–3.14.

Nothing to adopt ([#1084](https://github.com/diazoxide/charter/issues/1084)).
