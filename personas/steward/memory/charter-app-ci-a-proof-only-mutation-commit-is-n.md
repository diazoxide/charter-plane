# charter-app CI: a PROOF ONLY mutation commit is NOT free now that Rust r

_2026-09-22 13:28 · persistent_

charter-app CI: a PROOF ONLY mutation commit is NOT free now that Rust runs locally. Two attempts on PR 145 both had to be cancelled — combining 'no O_NOFOLLOW/O_NONBLOCK' with 'no not-a-plain-file refusal' HANGS the suite rather than failing it (a plain blocking open of a FIFO a reader holds waits for a writer that never comes), and a second, non-hanging five-guard commit still had not finished cargo test after 14 min on the Linux runner while the same five finish in 20 s on macOS. The local one-at-a-time sweep against a green baseline is the stronger evidence anyway: it attributes each guard to a named test, which one all-at-once CI commit cannot.
