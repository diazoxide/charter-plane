# charter-app hookwire: removing any guard that keeps ONE plane to ONE lis

_2026-09-21 01:05 · persistent_

charter-app hookwire: removing any guard that keeps ONE plane to ONE listener does not turn a test red, it WEDGES cargo test forever (measured on PR 111, two separate CI runs cancelled). Reading::drop wakes its own blocked accept by connecting to self.path — if a second Listener::bind has since unlinked and recreated that path, the connect wakes the SECOND listener and the first thread blocks in accept while drop joins it forever. So Planes::open answering an already-open root, and canonicalising the root before keying the registry, are both deadlock guards, not merely tidiness. When mutation-testing anything socket-identity-shaped in this repo, expect a hang and budget a cancelled run rather than reading a red test.
