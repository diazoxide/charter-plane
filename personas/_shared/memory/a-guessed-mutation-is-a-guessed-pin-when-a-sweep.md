# A guessed mutation is a guessed pin. When CI's mutation run names a su

_2026-09-25 · persistent_

A guessed mutation is a guessed pin. When CI's mutation run names a survivor, apply that mutation verbatim from its artifact (download the run's output with gh run download and take the exact diff or replacement it records), never retyped from the log's summary line. On charter #989 (2026-09-12), three hand-written mutations all died locally and contradicted CI. The easy read was 'CI is flaky', but CI's real mutants survived, and that exposed guards pinned only by macOS's /var to /private/var symlink, which were unpinned on every Linux run. A survivor that went red once and then green on confirmation is platform-dependent, not flaky. A fixture that needs a symlink must create one itself rather than rely on the platform's temp directory.
