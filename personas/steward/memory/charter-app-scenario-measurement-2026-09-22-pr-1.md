# charter-app scenario measurement, 2026-09-22 (PR #170): a TABLE CELL IS

_2026-09-22 22:50 · persistent_

charter-app scenario measurement, 2026-09-22 (PR #170): a TABLE CELL IS AS TALL AS ITS ROW, so measuring a td/th height to detect a wrapped cell measures the whole row — the bottom bar's check went red on CI because the pipeline cell (which is meant to wrap) made every other cell two lines tall. Measure a Range over the cell's CONTENT instead: document.createRange(); range.selectNodeContents(cell); range.getBoundingClientRect().height is one line box whatever the row is doing. Also: a forge refresher runs DURING the scenario suite, so a pipeline cell says 'not fetched' early in a run and 'no pipeline recorded' later — wait for the .none cell, never for either sentence.
