# Measured 2026-09-23 on macOS 26.2 Apple Silicon: an ad-hoc-signed app in

_2026-09-23 09:58 · persistent_

Measured 2026-09-23 on macOS 26.2 Apple Silicon: an ad-hoc-signed app in /Applications CAN replace its own bundle via the tauri updater's path (rename aside, remove, rename in) with NO App Management prompt and no TCC entry recorded — despite having no Team ID. Control: the same process was DENIED reading ~/Library/Application Support/com.apple.TCC/TCC.db, proving TCC was enforcing. Quarantine on the old bundle does not survive onto the new tree. Probe must be launched via 'open' (LaunchServices) not from the shell, or it inherits the terminal's TCC identity and measures nothing.
