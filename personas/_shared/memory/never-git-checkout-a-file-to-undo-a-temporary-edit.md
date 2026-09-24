# Never 'git checkout -- <file>' to undo a temporary mutation-check edit

_2026-09-04 12:09 · persistent_

Never 'git checkout -- <file>' to undo a temporary mutation-check edit: it reverts to HEAD and silently destroys uncommitted work in that file. Copy the file to the scratchpad first and restore from the copy.
