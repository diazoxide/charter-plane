# A git worktree shares its clone's info/exclude (the common dir), so an

_2026-09-25 · persistent_

A git worktree shares its clone's info/exclude (the common dir), so anything that 'unwires' a worktree by editing its exclude file edits the clone's exclude too. The clone's git status then fills with the generated files the exclude hid. And git worktree remove already deletes excluded generated files along with the directory, so removing a worktree needs no separate unwire step. Measured on the retired Python CLI (#951, 2026-09-10). Also, code that discovers a workspace's repos by scanning only direct children will not see worktrees nested deeper, so check where worktrees actually live before trusting a scan.
