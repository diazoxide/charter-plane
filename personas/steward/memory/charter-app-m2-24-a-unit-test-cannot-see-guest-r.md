# charter-app M2.24: a unit test CANNOT see guest.rs's info/exclude crea

_2026-09-25 · persistent_

charter-app M2.24: a unit test CANNOT see guest.rs's info/exclude created-vs-refreshed split, because a unit test builds .git as an empty directory, so info/exclude does not exist and reads as empty, while a real 'git init' writes a default exclude full of template comments. Only a test over a real 'git init' repository tells the two apart — measured by mutation on PR 118.
