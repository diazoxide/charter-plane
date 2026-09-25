# On this machine a freshly written executable shell script that a subproc

_2026-09-20 09:58 · persistent_

On this machine a freshly written executable shell script that a subprocess execs hangs for minutes — the same syspolicyd pressure that hangs freshly built binaries at _dyld_start. Measured 2026-09-20: a gpg.program script and a bare repository's pre-receive hook each hung a plain commit and a plain push for over 60 seconds, while the identical flow with no new executable ran in 0.03s. So a test whose evidence is 'a program charter made the tool run' cannot be verified here at all; write it, push it, and read the answer off CI, which runs on ubuntu and is fine with it. A local probe of the Python oracle should avoid new executables and point at a path that does not exist wherever 'the program was never run' is all that matters.
