# Heredoc delimiter reading, measured 2026-09-11 with /bin/bash 3.2.57 a

_2026-09-25 · persistent_

Heredoc delimiter reading, measured 2026-09-11 with /bin/bash 3.2.57 and /bin/zsh on macOS: <<EO'F', <<'EO'F, <<"EO"F and <<\EOF all terminate at a line reading EOF, and all four bodies are LITERAL ($HOME is not expanded). Quoting or an escape anywhere in the delimiter word both joins the word and stops expansion. A naive regex yields EO for the first three and nothing for <<\EOF. The consequence for guards: a wrong delimiter errs SAFE when the body is being hidden from a guard (the terminator is never found, the body stays visible) and errs DANGEROUSLY when the body is being DROPPED (it drops to end of input and swallows the real commands after the heredoc). Anything in charter-app's shell reader that drops a body must take the delimiter from a full word-level reading of the header, never from a regex.
