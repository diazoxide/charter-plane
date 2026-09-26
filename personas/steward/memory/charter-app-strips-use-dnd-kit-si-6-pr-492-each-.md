# charter-app strips use @dnd-kit (SI-6, PR #492). Each DndContext keeps a

_2026-09-26 20:36 · persistent_

charter-app strips use @dnd-kit (SI-6, PR #492). Each DndContext keeps a hidden role=status live region that stays empty until a drag, so a test that asks for THE status on the page finds several. Use sayingSomething() from app/src/test-strips.ts, which returns status regions with text. Keyboard pick-up is Shift+Space, because bare Space and Enter select a focused tab (Window.keyboard.test.tsx).
