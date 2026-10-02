# AGENTS.md

Python 3.12, Home Assistant custom component. Tests: `pytest` (pytest-homeassistant-custom-component). Lint: `ruff check . && ruff format --check .`.

- Never commit credentials. Never log passwords, tokens, cookies, or full VIN/coords at INFO.
- `api.py` must not import `homeassistant`.
- Branches: `develop` is integration; one branch per Epic (`epic/E##-slug`), PR into `develop`, final PR `develop` -> `master`.

## Agent skills

- Issue tracker: GitHub (`docs/agents/issue-tracker.md`)
- Triage labels: `docs/agents/triage-labels.md`
- Domain docs: `docs/agents/domain.md` (single context: `CONTEXT.md` + `docs/adr/`)
