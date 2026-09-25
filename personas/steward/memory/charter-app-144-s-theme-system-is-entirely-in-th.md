# charter-app #144's theme system is entirely in the TypeScript bundle: tw

_2026-09-22 14:26 · persistent_

charter-app #144's theme system is entirely in the TypeScript bundle: two built-in themes compiled in, theme.ts's load() written for file-borne themes but called by nothing, and NOTHING written to or read from the machine store's directory. Briefs circulating on 2026-09-22 claimed #144 'took the file-beside-machine.json route so ADR 0034 needed no amendment' — it did not take any on-disk route at all. charter-app#150 (extension registry, ADR 0041 stage 1) is what creates it, at $CHARTER_CONFIG_HOME/charter/extensions.json. Separately: specta refuses to generate bindings when two modules export types of the same name ('Detected multiple types with the same name: Ask'), which caught the plugin/extension naming collision ADR 0041 warns about, at the type level.
