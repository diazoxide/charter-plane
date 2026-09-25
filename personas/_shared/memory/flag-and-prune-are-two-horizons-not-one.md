# A surface that deletes the record it draws from turns the most alarmin

_2026-08-20 14:41 · persistent_

A surface that deletes the record it draws from turns the most alarming state into the blank one: 'presumed dead' and 'never happened' render identically. One retention number cannot do both jobs; split it into a flag threshold (keep the record, mark it stale) and a much later prune horizon. Once records outlive the flag threshold, anything that retires records by age must skip flagged ones first, or finishing a live peer deletes the stuck one.
