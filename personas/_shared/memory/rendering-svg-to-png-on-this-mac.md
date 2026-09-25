# Rendering an SVG to PNG on this Mac (no rsvg-convert/cairosvg/magick):

_2026-08-20 00:25 · persistent_

Rendering an SVG to PNG on this Mac (no rsvg-convert/cairosvg/magick): qlmanage -t -s <size> always emits a square thumbnail and clips a wide image, so pad the SVG to a square viewBox with the content centred, render, then crop back with 'sips -c H W'. A square qlmanage output is therefore no evidence about a wide image's right edge. Headless Chrome --screenshot writes the PNG and never exits: background it, poll for the file, and kill its own $! (never pkill by name). Check glyph legibility at the size the image will actually be displayed, not only zoomed in.
