# On macOS sockaddr_un holds 104 bytes, so a Unix socket under a Claude 

_2026-09-11 01:41 · persistent_

On macOS sockaddr_un holds 104 bytes, so a Unix socket under a Claude Code scratchpad path (measured 146 bytes) fails with 'File name too long'. Put sockets under a short mktemp dir in /tmp instead.
