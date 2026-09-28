# SI-9a merged: memory edit/archive core API (PR #519, f54402c)

_2026-09-28 16:50 · persistent_

SI-9a merged in diazoxide/charter #519 (squash f54402c), ADR 0065. Core: memstore::edit(root,dir,ident,title,text,Base::Read(text)|Base::Overwrite) -> Result<PathBuf, EditRefused::{Stale,Io}>; memstore::archive_one / memstore::unarchive(.., restore_as); memstore::open. Workspace and Persona (incl. _shared via plane.persona("_shared")) have open_memory -> workspaces::Opened{path,text,entry}, edit_memory, archive_memory, unarchive_memory(slug, restore_as). CLI: workspace edit|archive|unarchive, persona edit-memory|archive-memory|unarchive-memory [--shared]. SI-9b builds on these.
