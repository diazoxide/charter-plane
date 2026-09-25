# Persona inheritance order trap: a persona's lineage is listed CHILD-FI

_2026-09-25 · persistent_

Persona inheritance order trap: a persona's lineage is listed CHILD-FIRST ([name, parent, grandparent]). Folding it in that order with 'later overwrites earlier' makes the most distant ancestor win, the opposite of the documented 'child wins' rule; the Python CLI shipped exactly this bug in its MCP-server union (#296, PR 297). Any union over a lineage must iterate it reversed (root first, child last) and have a test where child and ancestor disagree. Related: an approval keyed on a program's basename ('tools: foo.sh') approves any foo.sh anywhere unless it is pinned to the persona's own bin/ directory (PR 295).
