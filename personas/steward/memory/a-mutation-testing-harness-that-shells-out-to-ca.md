# A mutation-testing harness that shells out to cargo MUST assert a green

_2026-09-22 14:26 · persistent_

A mutation-testing harness that shells out to cargo MUST assert a green baseline first, and must treat 'no test result: line' as an error. Running it with a bare subprocess env on this machine left cargo unable to find rustc ('could not execute process rustc -vV'), every run failed before a test executed, and all 28 mutations came back 'HELD BY NOTHING' — a proof run that proved nothing, which is exactly the defect the exercise exists to catch (charter-app#110 found four such guards). Also: a guard whose removal makes a test HANG rather than fail is still held by it — dropping contain::open_no_link makes the FIFO test block forever, because contain::nofollow sets O_NONBLOCK. Catch TimeoutExpired and report it as held.
