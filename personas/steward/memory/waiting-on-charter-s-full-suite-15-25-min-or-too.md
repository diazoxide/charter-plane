# Never wait on a long run (a full test suite, a mutation run, a CI poll

_2026-09-25 · persistent_

Never wait on a long run (a full test suite, a mutation run, a CI poll) inside a foreground tool call from an agent session. On a machine loaded by sibling agents, even short sleep loops overrun the call timeout, and the stream watchdog stops the whole agent after ~600 s of silence, killing the unfinished run with it (happened twice 2026-09-11). The harness also refuses a foreground 'sleep N; cmd'. What works: start the run with run_in_background writing to a file, then arm a Monitor whose script prints only the lines to act on (the result trailer, failures, a heartbeat every ~10 min) and exits when the run ends; its notifications wake the agent.
