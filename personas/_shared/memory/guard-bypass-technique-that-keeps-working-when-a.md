# Guard-bypass technique that keeps working: when a parse bug is found i

_2026-09-25 · persistent_

Guard-bypass technique that keeps working: when a parse bug is found in a shell guard, search for the same SHAPE, not the same spelling. In the Python guard (2026-08), fixing one option-parsing bug and sweeping siblings found live bypasses of the same shape: env -C with a glued value, sudo -D, xargs -a, env assignments whose name is not an identifier, and values glued to bundled short options (diazoxide/charter #547, #555, #556, all fixed). charter-app's Rust port of the shell reader inherits the same risk: any fix to one command's option parsing should be followed by a sweep of every command whose options take a directory or file, confirmed by reproduction, not reasoning.
