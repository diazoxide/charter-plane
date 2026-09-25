# A feature whose promise is about the environment (gitignored, committe

_2026-08-20 09:44 · persistent_

A feature whose promise is about the environment (gitignored, committed, on PATH, reachable) cannot be verified by tests that only exercise the code. A 'write a local-only settings file' feature shipped with 16 green tests and not one asked whether git would keep the file out; the generated .gitignore lacked the line. Assert the property against a real fresh artifact (a newly initialised plane, a real .gitignore), and fix it both in the template and at the point of use, or every plane created before the fix stays broken.
