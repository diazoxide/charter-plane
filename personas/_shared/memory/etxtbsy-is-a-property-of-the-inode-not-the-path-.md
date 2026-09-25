# ETXTBSY is a property of the INODE, not the path. Write-to-temp-then-ren

_2026-09-20 18:20 · persistent_

ETXTBSY is a property of the INODE, not the path. Write-to-temp-then-rename does NOT fix 'Text file busy' on exec: rename hands execve the same inode, and a child forked while the parent held the write fd still counts against it. Proved on CI in charter-app#82 - the rename fix failed at round 20 of 250 with the issue's own error. The fix is to never open the program for writing in THIS process at all (hand the bytes to /bin/sh), so fork cannot copy a descriptor the parent does not have. Rename IS right for the other direction - writing OVER a program that is currently running (charter-app#39) - so both live side by side and the comments say which bug each answers.
