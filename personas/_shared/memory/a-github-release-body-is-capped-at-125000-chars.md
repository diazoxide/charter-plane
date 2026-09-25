# A GitHub Release body is capped at 125,000 characters and gh forwards 

_2026-08-30 02:16 · persistent_

A GitHub Release body is capped at 125,000 characters and gh forwards the refusal rather than truncating. If the release job that writes the body runs after an irreversible publish step, an oversize body fails after the point of no return. Measure the rendered notes before tagging; 0.54.0's whole notes were 423,196 characters and had to be elided.
