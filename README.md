# grace-pmo-mcp — Grace PMO Assistant

A retrieval-first PMO assistant built as **four MCP services on Cloud Run**
plus a **Skill bundle** consumed by an Anthropic Claude project.

| Component | Tech | Role |
|-----------|------|------|
| `grace-pmo-director` Skill | Markdown bundle | Behavior — 4 gates, 3 modes, response shaping |
| `grace-site-mirror` MCP | Python 3.12 + FastMCP + httpx | Tier 1 — wraps the SiteMirrorQuery Apps Script |
| `grace-sheets` MCP | Python 3.12 + FastMCP + Google APIs | Tier 2 — Drive Map + Doc reader + Onboarding Tracker |
| `grace-slack` MCP | Python 3.12 + FastMCP + slack-sdk | Tier 3 — `#zennify_pmo` w/ authoritative-sender filter |
| `grace-orchestrator` MCP | Python 3.12 + FastMCP + httpx | Parallel fan-out, ranking, dedup |

## Quick start

```bash
make sync   # install workspace + dev deps via uv
make lint   # ruff
make test   # pytest -q  (118 tests)
make skill  # build grace-pmo-director.skill
```

## Layout

```
grace-pmo-mcp/
├── libs/shared/              # grace_shared — app, config, errors, url_canon
├── services/
│   ├── site-mirror/          # MCP 1 — Tier 1
│   ├── sheets/               # MCP 2 — Tier 2 + tracker + doc reader
│   ├── slack/                # MCP 3 — Tier 3
│   └── orchestrator/         # MCP 4 — composer
├── skills/grace-pmo-director/  # The Skill (zips to .skill)
├── infra/terraform/          # GCP provisioning
├── deploy/GUIDE.md           # End-to-end deployment guide
└── .github/workflows/        # CI/CD via WIF
```

## Deployment

`deploy/GUIDE.md` is the full step-by-step (~45 min of operator work).
The default path is **CLI-only via `gcloud` + `docker`** — no Terraform or
GitHub Actions required. The Terraform module in `infra/terraform/` and
the workflow in `.github/workflows/deploy.yml` are equivalent IaC for
operators who prefer that path.

## Design

See the canonical solution design document — this repo is the implementation.
The non-negotiable contract is in `skills/grace-pmo-director/system/prime_directive.md`.
