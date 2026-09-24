# Local green can lie because the local invocation differs from CI's. On

_2026-09-25 · persistent_

Local green can lie because the local invocation differs from CI's. On the Python suite, a relative import passed under 'python -m unittest tests.<mod>' and failed under CI's discover, and no local re-run could reproduce it. The same class exists in charter-app: 'cargo test -p <crate>' versus the workspace run, --lib versus integration tests, features enabled only in CI, the e2e runner, or a different OS in the matrix. Before trusting a green local run, run it THE WAY CI RUNS IT (read .github/workflows for the exact command), not the way that is convenient.
