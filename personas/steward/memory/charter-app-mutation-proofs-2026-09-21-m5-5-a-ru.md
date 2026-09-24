# charter-app mutation proofs (2026-09-21, M5.5): a Rust mutation must sti

_2026-09-21 06:00 · persistent_

charter-app mutation proofs (2026-09-21, M5.5): a Rust mutation must still compile under RUSTFLAGS='-D warnings' or it proves only that the compiler noticed. Deleting the branch that was the last caller of a pub method inside a PRIVATE module trips dead_code; deleting the only push to a 'let mut v' trips unused_mut. Substitute, never delete — keep Holding::front called via front.is_some(), keep dropped.push() but remove the 'continue'. Second trap: reverting a mutation you have ALREADY committed cannot be 'checkout -- <file>' (that restores from HEAD, which is the mutation commit); use 'checkout <sha-before> -- <file>' and then check the diff against <sha-before> is empty.
