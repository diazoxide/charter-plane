# A test whose expected value is computed from the thing under test cann

_2026-09-25 · persistent_

A test whose expected value is computed from the thing under test cannot fail. The tell is that the expectation mentions the code under test: assert_eq!(err, MSG.replace(...)), an expected path built from the same helper the code uses, an expected string built from a constant read back from the module. Change the template, the constant or the helper and the test stays green, because both sides move together. Fix: write the expected value out literally. This shape cost the chat-handoff plan four review rounds across three PRs. The one exception is an indirection through a value the operator configures (a theme colour, an accent): spelling the literal would pin one operator's settings and fail falsely. Then keep the indirection, and close its one hole, an empty value that makes every contains-check pass, with a literal assertion beside it.
