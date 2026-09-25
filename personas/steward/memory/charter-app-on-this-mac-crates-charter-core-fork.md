# charter-app on this Mac: crates/charter-core forklock::tests two_program

_2026-09-22 23:11 · persistent_

charter-app on this Mac: crates/charter-core forklock::tests two_programs_can_start_at_the_same_time and waiting_for_a_program_to_finish_does_not_hold_a_terminal_back fail with Err(Timeout) when 'cargo test -p charter-core -p charter-cli' runs both test binaries in parallel, and pass every time on 'cargo test -p charter-core --lib' alone. Wall-clock deadline starved by load, not a regression — reproduced on a tree whose diff touches nothing forklock reads. Check the crate alone before believing it.
