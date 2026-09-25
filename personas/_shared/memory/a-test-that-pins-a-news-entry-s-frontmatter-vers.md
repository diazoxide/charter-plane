# A test that pins a news entry's frontmatter to 'version: unreleased' b

_2026-09-25 · persistent_

A test that pins a news entry's frontmatter to 'version: unreleased' breaks the release that stamps the version onto it (it broke the 0.61.0 bump, PR #1006). charter-app still keeps unreleased entries under crates/charter-core/news/. A news-shape test must accept either 'unreleased' or the version the tree ships as (the app's own version), never 'unreleased' alone.
