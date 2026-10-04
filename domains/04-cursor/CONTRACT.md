# 04-cursor contract

Job: Cursor Cloud session economy — caps, launch discipline, archive, and harness routing as data.

IN: `cloud-sessions.yaml`; Loom measured caps; box-archive-path gates.

OUT: Validated policy file at pinned SHA; harness reads YAML only.

GATE: Warden PR; Cris merge; no org API changes in this domain.

ESC: Warden → Cris.

Verify: `make validate` (schema + `domains/04-cursor/tests/`).
