# forge::resolve_host must fail closed on host-confusion URLs: user@gith

_2026-08-22 10:05 · persistent_

forge::resolve_host must fail closed on host-confusion URLs: user@github.com@evil.example, github.com.evil.example, github.com:token@evil.example, and a managed host name appearing only in the path all resolve to None (unmanaged), never to a managed forge. The answer decides which credential helper and insteadOf a clone gets, so a false match hands a token to another host. Keep these cases pinned in tests when touching URL parsing.
