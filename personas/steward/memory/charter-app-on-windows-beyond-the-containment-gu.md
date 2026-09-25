# Windows porting pitfalls found in charter-app's M4 audit (2026-09-20, 

_2026-09-25 · persistent_

Windows porting pitfalls found in charter-app's M4 audit (2026-09-20, issues 100 and 103), useful for any Windows regression: env SHELL / /bin/sh do not exist there; POSIX single quoting in a hook command means nothing to cmd.exe (the apostrophe is an ordinary character), and since session state comes only from hooks (ADR 0018) a mis-quoted hook leaves the board silent with no reason; git is git.exe, PATH joins with ';', Windows git wants USERPROFILE not HOME, and env_clear drops SystemRoot, without which winsock will not initialise so every network git fails looking like DNS; without a .gitattributes, Git for Windows' core.autocrlf breaks byte-comparison tests. Check the current code and ADR 0031 before assuming any of these is still open.
