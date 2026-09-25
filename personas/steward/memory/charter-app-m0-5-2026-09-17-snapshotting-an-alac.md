# charter-app M0.5 (2026-09-17), snapshotting an alacritty_terminal grid b

_2026-09-17 18:58 · persistent_

charter-app M0.5 (2026-09-17), snapshotting an alacritty_terminal grid back to escape sequences: (1) a cell can hold '\t' — alacritty's put_tab stores the tab CHARACTER in the cell, so writing cell.c verbatim emits HT, the receiving terminal jumps to its own tab stop and every column after it is wrong; write a space instead (also in Screen.lines). (2) snapshot() must call parser.stop_sync() UNCONDITIONALLY, not only on expiry: bytes inside an open ?2026 block are already read from the pty and reach no view, so a view attaching then loses them permanently. (3) Term::inactive_grid is private, so the main screen behind an open alternate screen cannot be carried, and a grid-comparison property test cannot even SEE that loss (term.grid() is the active grid only). (4) Term::cursor_style() IS public — carry it with DECSCUSR.
