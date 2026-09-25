# ETXTBSY on exec follows the inode, not the path: renaming a freshly writ

_2026-09-20 18:10 · persistent_

ETXTBSY on exec follows the inode, not the path: renaming a freshly written program into place does not stop a forked child's write descriptor from blocking execve. The fix is to have a child write the file so this process never holds one. See charter-app crates/stand-in and PR 82.
