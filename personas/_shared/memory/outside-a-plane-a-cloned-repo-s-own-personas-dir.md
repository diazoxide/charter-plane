# A repository's own files must never grant permissions. On the Python c

_2026-09-25 · persistent_

A repository's own files must never grant permissions. On the Python charter (#852, fixed by PR #857), outside a plane the root was the CWD, so a cloned repo's committed personas/<x>/persona.md declaring tools:[curl] plus an active-persona pointer made the pretooluse hook answer ALLOW for arbitrary curl. That is the same class as 'no config key lifts a denial', reached through a different door: not lifting a denial but manufacturing an ALLOW. General rule for charter-app: any state read from a directory is untrusted until charter has established that it is an opened, trusted plane (ADR 0035), and a guard's ALLOW paths deserve the same adversarial review as its deny paths.
