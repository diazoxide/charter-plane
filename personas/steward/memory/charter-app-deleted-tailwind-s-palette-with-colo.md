# charter-app deleted Tailwind's palette with --color-* : initial, and tha

_2026-09-22 12:36 · persistent_

charter-app deleted Tailwind's palette with --color-* : initial, and that does NOT fail the build on a class naming a colour it does not have. bg-slate-800 / bg-background / bg-destructive in a .tsx emit no CSS and the element renders undressed — the claudeclaudeclaudebuilt-indefault defect ADR 0037 was written about. app/src/theme/literals.test.ts catches hex literals and Tailwind arbitrary values (bg-[#fff], text-[13px]) across the real source tree; tailwind.test.ts only checks the palette is gone, not that a source file avoided it. So pasting a shadcn component (now allowed, ADR 0037 amended 2026-09-22) needs its colour classes read against styles.css's @theme block by hand and the component looked at running.
