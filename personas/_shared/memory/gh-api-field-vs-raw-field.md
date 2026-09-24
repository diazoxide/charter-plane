# gh api: -F/--field gives a value magic meaning (leading @ = read that 

_2026-08-21 17:53 · persistent_

gh api: -F/--field gives a value magic meaning (leading @ = read that file, @- = read stdin); -f/--raw-field sends the literal string. Verified on gh 2.83.2. Never pass external data (branch names, remote paths) via -F. For GraphQL variables use -f and do NOT percent-encode — GitHub does not decode them, so quoting turns feature/x into feature%2Fx and matches no ref. Percent-encode only URL path/query segments.
