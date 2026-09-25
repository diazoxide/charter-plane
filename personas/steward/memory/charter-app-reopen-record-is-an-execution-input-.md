# charter-app reopen record is an execution input read before any window e

_2026-09-20 23:27 · persistent_

charter-app reopen record is an execution input read before any window exists. The app setup calls Chats put_back under the comment that says before a single session is started because put_back below starts them, and start_recorded sends a chat with no profile straight to Chats start, where what runs is decided from the record alone. A chat with a profile is safe by a different route: the profile is looked up again in machine-local charter.local.toml, never taken from the record, and profiletrust gates its command. The state directory being gitignored is not protection once an opener opens a directory, because directories arrive by zip, shared folder and USB, not only by git clone.
