# charter-app now has one port of contain.one_line, in shown.rs, and perso

_2026-09-20 10:04 · persistent_

charter-app now has one port of contain.one_line, in shown.rs, and personas::one_line and doctor::one_line delegate to it. M2.2 and M2.4 had each landed a separate copy with its own Unicode Cf range table; three copies of that table means three places for it to go stale separately, which shows up as one charter escaping a character another prints on a report line. Same argument put news frontmatter reading through personas::frontmatter.
