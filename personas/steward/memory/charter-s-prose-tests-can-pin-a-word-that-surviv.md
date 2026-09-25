# charter's prose tests can pin a word that survives the change they were

_2026-09-22 12:36 · persistent_

charter's prose tests can pin a word that survives the change they were meant to catch. tests/test_the_plugin_threat_model_is_written_down.py had test_it_says_adr_0031_is_still_a_draft asserting only assertIn('DRAFT', text) on ADR 0041. When 0031 was signed off (2026-09-22, PR charter#1171) and 0041 rewritten to keep the draft status as HISTORY, the assertion stayed green while the test's name and failure message became lies. A tripwire on a word is not a tripwire on a claim: pin the sentence ('0031 was marked `DRAFT'), and where two files make one claim, read both and fail on disagreement in either direction. Same lesson found twice: a first mutation probe showed assertIn('ui-primitives.md', amendment) survived deleting the sentence that named it, because the string recurred later in the section.
