# charter-app panel contract (PR 206 / charter ADR 0043): a contributed pa

_2026-09-23 12:11 · persistent_

charter-app panel contract (PR 206 / charter ADR 0043): a contributed panel is declarative data against a closed vocabulary in crates/charter-core/src/panel.rs. A declared row may NOT carry 'runs' (a catalogue offer id) because ADR 0041 stage 1 has no executor — panel::NO_VERB is that refusal. charter's own panels may, and that asymmetry lifts only via a stage-2 grant, never a special case.
