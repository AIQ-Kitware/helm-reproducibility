# reproduce/

This directory is the human-readable runbook layer for `helm_audit`.

Each scenario folder contains a small numbered sequence:

- `00_*`: environment or indexing setup
- `10_*`: manifest generation or analysis selection
- `20_*`: execution or rebuild step
- `30_*`: comparison or follow-on reporting

Current scenarios:

- `smoke/`
- `apples/`
- `historic_grid/`
- `machine_compare/`

These scripts are intentionally thin. They should read like operator notes and
delegate real work to the Python CLI entrypoints.
