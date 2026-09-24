# charter-app: 'in a plane' means the charter.toml MARKER file exists at

_2026-09-25 · persistent_

charter-app: 'in a plane' means the charter.toml MARKER file exists at the root, not that plane::resolve succeeded — plane::resolve takes $CHARTER_ROOT on trust and returns it unchecked. Code that gates on 'resolve succeeded' runs every plane-gated guard arm in a directory that is not a plane (charter#852 one level down). Found in M3.1 stage 6 (charter-app#181) by pretooluse-outside-a-plane scenarios, not by any unit test; keep a behaviour test that runs the hook outside a plane.
