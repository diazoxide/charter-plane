# A refusal test must assert which refusal fired, by its message or spec

_2026-09-25 · persistent_

A refusal test must assert which refusal fired, by its message or specific variant, never by the error type alone. Error type is not the reason. In charter's old mutation tool, a parser's refusal could be deleted outright and every test still passed, because the fallback parse raised the same ValueError for other reasons ('--shard wants N/M' vs 'invalid literal for int()'). The same thing happened with release.yml (#558): deleting its -z refusal left the run still exiting 1 because the next check caught the empty string. In Rust the same trap is `assert!(result.is_err())` or `matches!(e, Error::Invalid(_))` when several paths produce that variant. Assert the message or the distinguishing field. When two refusals share a condition, mutate each conjunct separately, because a whole-condition mutation cannot tell them apart.
