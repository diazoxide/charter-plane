# A charter run in a scratch dir still resolves CHARTER_ROOT

_2026-09-26 21:17 · persistent_

Running a built charter binary from a scratch/tmp directory still acts on the REAL plane: every chat carries CHARTER_ROOT=<plane>, and plane resolution honours it before cwd. On 2026-09-26 an SI-2a smoke test ran init + workspace create + persona curation add in /private/tmp and wrote .gitattributes, opencode.json, .claude/settings.json and personas/steward/curation/ into the live plane; auto-save committed and pushed them within 30s (ad752ede). Always smoke-test through a wrapper that does env -i HOME=<scratch> CHARTER_ROOT=<scratch plane> — as the CLI tests do.
