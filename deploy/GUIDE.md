# Grace — Deployment Guide

End-to-end deployment instructions for the four Grace MCP services and the
`grace-pmo-director` Skill bundle. Estimated total time: **~60 minutes**.

> Operator pre-reqs: a Google Cloud account with billing, Workspace admin
> rights to grant Drive and Slack scopes, a GitHub account with admin on
> the target repo, and an Anthropic Claude account.

---

## At a glance

| # | Step | Time |
|---|------|------|
| 1 | Provision GCP project + link billing | 5 min |
| 2 | Verify the SiteMirrorQuery Apps Script responds | 1 min |
| 3 | Clone the repo and run tests locally | 5 min |
| 4 | `terraform init && terraform apply` | 5 min |
| 5 | Share Workspace resources with the runtime SA | 5 min |
| 6 | Create Slack bot, install, look up 6 user IDs | 10 min |
| 7 | Populate 4 secrets via `gcloud secrets versions add` | 5 min |
| 8 | Configure GitHub Actions variables and push to `main` | 5 min |
| 9 | Smoke-test each service (7 checks) | 10 min |
| 10 | Wire the 4 MCP URLs into the Anthropic project, upload the Skill | 5 min |

---

## Step 0 — Tooling

Install on your workstation:

```bash
# uv (the Python workspace manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Terraform 1.6+
brew install terraform           # macOS
# OR
apt-get install -y terraform     # Ubuntu

# Google Cloud SDK
brew install --cask google-cloud-sdk  # macOS
gcloud auth login
```

Confirm versions:

```bash
uv --version          # >= 0.4
terraform --version   # >= 1.6
gcloud --version
```

---

## Step 1 — GCP project + billing

```bash
export GCP_PROJECT=grace-pmo-prod          # or your chosen ID
export GCP_REGION=us-central1
export BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX

gcloud projects create "$GCP_PROJECT" --name="Grace PMO"
gcloud beta billing projects link "$GCP_PROJECT" \
  --billing-account="$BILLING_ACCOUNT_ID"
gcloud config set project "$GCP_PROJECT"
```

Terraform's `google_project_service` resources enable the required APIs
in step 4 — no manual `gcloud services enable` calls needed.

---

## Step 2 — Verify the SiteMirrorQuery Apps Script

This Apps Script Web App pre-exists (it is owned by the PMO). Confirm it
still answers before you start:

```bash
curl -sS \
  'https://script.google.com/macros/s/AKfycbyCJ5Fkyw8JySwT5G-aqWTDAtR6nN8n-Nv-PifbnOHJ4_gxkXwjWXl162Pl-Tjf3fE0/exec?action=getURLIndex' \
  | jq '.pages | length'
```

A number around 60 confirms the mirror is up. **Save this URL — you will
load it into Secret Manager in step 7.**

---

## Step 3 — Repo + local tests

```bash
git clone git@github.com:mishleyotis/grace.git
cd grace
git checkout claude/implement-stress-test-deploy-2m2XU   # or main

make sync          # uv sync --all-packages
make lint          # ruff
make test          # pytest -q  →  118 passed
make skill         # builds grace-pmo-director.skill at repo root
```

If any step fails, **stop and fix locally before deploying.** This entire
guide assumes the local suite is green.

---

## Step 4 — Terraform apply

```bash
cd infra/terraform

cat > terraform.tfvars <<EOF
gcp_project    = "$GCP_PROJECT"
gcp_region     = "$GCP_REGION"
github_repo    = "mishleyotis/grace"
alert_email    = "pmo-grace-alerts@zennify.com"  # optional; leave "" to skip
min_instances  = 0                                # set to 1 for no cold starts
EOF

terraform init
terraform plan -out plan.tfplan
terraform apply plan.tfplan

terraform output -json > ../../outputs.json
```

Capture the outputs you will need shortly:

```bash
SITE_MIRROR_URL=$(terraform output -raw site_mirror_url)
SHEETS_URL=$(terraform output -raw sheets_url)
SLACK_URL=$(terraform output -raw slack_url)
ORCHESTRATOR_URL=$(terraform output -raw orchestrator_url)
RUNTIME_SA=$(terraform output -raw runtime_sa_email)
DEPLOYER_SA=$(terraform output -raw deployer_sa_email)
WIF_PROVIDER=$(terraform output -raw wif_provider)
ARTIFACT_REGISTRY=$(terraform output -raw artifact_registry_repo)
```

> **Note:** The Cloud Run services exist now but each one points at an image
> tag that doesn't yet exist (`:latest`). Health checks will fail until the
> CI/CD pipeline runs in step 8.

---

## Step 5 — Share Workspace resources with the runtime SA

The runtime SA is **not a Terraform resource** for Drive / Sheets ACLs —
those are Workspace-managed. Grant the following access manually via the
Google Workspace UI:

| Resource | Access | Email |
|----------|--------|-------|
| Drive Map sheet (`19VQxsUb7pnnxTWP0vQzLLjIZWKU3k382lOEVYSnyiKE`) | **Viewer** | `$RUNTIME_SA` |
| Onboarding Tracker (`197CSSit_xi872N8oF3_uhV-LYxvRQwA42rfkknLCgEc`) | **Editor** | `$RUNTIME_SA` |
| ZennSource shared Drive (`0AGq-3ZBpQU5MUk9PVA`) | **Viewer** (drive member) | `$RUNTIME_SA` |

Verify by hitting Drive's `files.get` with the runtime SA:

```bash
gcloud auth print-access-token --impersonate-service-account="$RUNTIME_SA" \
  | xargs -I {} curl -sS -H "Authorization: Bearer {}" \
    "https://www.googleapis.com/drive/v3/files/19VQxsUb7pnnxTWP0vQzLLjIZWKU3k382lOEVYSnyiKE?fields=id,name"
```

Expected: a JSON body with the file's id and name. A 404/403 means the
share isn't propagated yet — wait 60 seconds and retry.

---

## Step 6 — Slack bot + authoritative-sender lookup

1. **Create a Slack app** at https://api.slack.com/apps?new_app=1.
   - App name: `Grace PMO Bot`
   - Workspace: Zennify
2. **OAuth & Permissions → Scopes (Bot Token Scopes)**: add
   `channels:history`, `channels:read`, `users:read`.
3. **Install to workspace** and capture the `xoxb-…` bot token.
4. Invite the bot to `#zennify_pmo`:
   ```
   /invite @grace-pmo-bot
   ```
5. Look up the **6 authoritative senders' Slack user IDs**. In the Slack
   client: profile → ••• menu → "Copy member ID". Names → IDs:

   | Name | User ID |
   |------|---------|
   | Kallen | U… |
   | Mike Theiler | U… |
   | Bryan Babb | U… |
   | Stephanie Brooks | U… |
   | Michael Rouleau | U… |
   | Tom Hedgecoth | U… |

6. **Compose** the comma-separated list, e.g.:
   ```
   U03ABC,U04DEF,U05GHI,U06JKL,U07MNO,U08PQR
   ```

---

## Step 7 — Populate Secret Manager

Bearer token (one shared across all 4 services):

```bash
BEARER_TOKEN=$(openssl rand -hex 32)
echo -n "$BEARER_TOKEN" | gcloud secrets versions add \
  grace-mcp-bearer-token --data-file=- --project="$GCP_PROJECT"
```

Slack bot token:

```bash
echo -n "xoxb-XXXXXXXXXXXXX-XXXXXXXXXXXXX-XXXXXXXXXXXXXXXX" | \
  gcloud secrets versions add grace-slack-bot-token \
    --data-file=- --project="$GCP_PROJECT"
```

Apps Script URL:

```bash
echo -n "https://script.google.com/macros/s/AKfycbyCJ5Fkyw8JySwT5G-aqWTDAtR6nN8n-Nv-PifbnOHJ4_gxkXwjWXl162Pl-Tjf3fE0/exec" | \
  gcloud secrets versions add grace-apps-script-url \
    --data-file=- --project="$GCP_PROJECT"
```

Authoritative Slack user IDs (comma-separated, no spaces):

```bash
echo -n "U03ABC,U04DEF,U05GHI,U06JKL,U07MNO,U08PQR" | \
  gcloud secrets versions add grace-authoritative-slack-user-ids \
    --data-file=- --project="$GCP_PROJECT"
```

**Confirm** each secret has exactly one enabled version:

```bash
for s in grace-mcp-bearer-token grace-slack-bot-token \
         grace-apps-script-url grace-authoritative-slack-user-ids; do
  gcloud secrets versions list "$s" --project="$GCP_PROJECT" --limit=1
done
```

---

## Step 8 — Configure GitHub Actions + push

In the GitHub repo, **Settings → Secrets and variables → Actions →
Variables** (not Secrets — these are non-sensitive):

| Variable | Value |
|----------|-------|
| `GCP_PROJECT` | `$GCP_PROJECT` |
| `GCP_REGION` | `$GCP_REGION` |
| `WIF_PROVIDER` | `$WIF_PROVIDER` |
| `DEPLOYER_SA` | `$DEPLOYER_SA` |
| `ARTIFACT_REGISTRY` | `$ARTIFACT_REGISTRY` |

Then push to `main`:

```bash
git push origin claude/implement-stress-test-deploy-2m2XU
# Merge via PR, OR fast-forward main and push.
```

The `test-build-deploy` workflow will:

1. Run `uv sync --all-packages`, `ruff`, `pytest -q`.
2. For each of the 4 services in parallel:
   - Authenticate via Workload Identity Federation.
   - Build the Docker image.
   - Push to Artifact Registry.
   - `gcloud run deploy` the new image.
   - Smoke-test `$URL/healthz` (5 retries × 5 s).

Watch the run at `https://github.com/mishleyotis/grace/actions`.

---

## Step 9 — Post-deployment smoke tests

These match the E2E suite from the solution design (section 11.1). Run
locally with `curl` after deploy completes.

```bash
for URL in "$SITE_MIRROR_URL" "$SHEETS_URL" "$SLACK_URL" "$ORCHESTRATOR_URL"; do
  echo "=== $URL ==="
  curl -sS "$URL/healthz" -w "\nHTTP %{http_code}\n"
done
```

Each must return `{"status":"ok","service":"<name>"}` with HTTP 200.

**E2E-2 — Bearer auth gate** (must 401 without a token):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "$ORCHESTRATOR_URL/mcp/"
# Expected: 401
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $BEARER_TOKEN" "$ORCHESTRATOR_URL/mcp/"
# Expected: 200 (or 405, depending on MCP transport — but NOT 401)
```

**E2E-3 — Tier 1 canonical URLs:**

```bash
curl -sS -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"kickoff","limit":3}' \
  "$SITE_MIRROR_URL/mcp/tools/site_mirror_search/invoke" | \
  jq '.results[].siteUrl' | grep -qE '^"https://sites\.google\.com/zennify\.com/delivery/' && \
  echo "PASS" || echo "FAIL"
```

**E2E-4 — Drive Map ZS_ priority:**

```bash
curl -sS -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"delivery checklist","limit":5}' \
  "$SHEETS_URL/mcp/tools/drive_map_search/invoke" | \
  jq '.results[0] | {name, score}'
# Expect: name starting with "ZS_", score > 100
```

**E2E-5 — `drive_doc_read`:**

```bash
curl -sS -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"file_id":"1AsE2UFl0HGouxxAwRIEsPuc2KxLY7Xw4EtKOeUPVLDQ","max_chars":2000}' \
  "$SHEETS_URL/mcp/tools/drive_doc_read/invoke" | \
  jq '{status, char_count, mime_type}'
# Expect: status=ok, char_count>0
```

**E2E-6 — Slack authoritative-only default:**

```bash
curl -sS -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"kickoff","limit":3}' \
  "$SLACK_URL/mcp/tools/slack_search_pmo/invoke" | \
  jq '{authoritative_only, authoritative_senders_configured, all_auth: ([.results[].is_authoritative] | all)}'
# Expect: authoritative_only=true, configured=6, all_auth=true
```

**E2E-7 — Orchestrator fan-out:**

```bash
curl -sS -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"change requests","per_tier_limit":5}' \
  "$ORCHESTRATOR_URL/mcp/tools/pmo_retrieve_grounding_bundle/invoke" | \
  jq '{tiers: (.tiers | to_entries | map({(.key): .value.status}) | add), n: .evidence_count}'
# Expect: each tier shows ok/no_results/error: …, n >= 1
```

If any check fails, see "Troubleshooting" below.

---

## Step 10 — Wire the Skill into a Claude project

1. In the Anthropic console, create (or open) a Claude project named
   "Grace — PMO Assistant".
2. **Settings → MCP servers → Add server.** Add four entries, each with
   the corresponding Cloud Run URL and the bearer token (`$BEARER_TOKEN`):

   | Name | URL |
   |------|-----|
   | grace-site-mirror | `$SITE_MIRROR_URL/mcp` |
   | grace-sheets | `$SHEETS_URL/mcp` |
   | grace-slack | `$SLACK_URL/mcp` |
   | grace-orchestrator | `$ORCHESTRATOR_URL/mcp` |

3. **Skills → Upload** the `grace-pmo-director.skill` artifact built in
   step 3.
4. Smoke-test in the project chat:
   - "How do we handle change requests?" → should return a grounded
     answer with a 3-tier grounding block.
   - "What's a good lunch spot?" → should return the canned refusal.
   - "What's the URL of the underlying mirror document?" → canned refusal.

You are live. Send the project link to the PMO team.

---

## Operations runbook

### View logs

```bash
gcloud logging tail "resource.type=cloud_run_revision AND \
  resource.labels.service_name=grace-orchestrator" \
  --project="$GCP_PROJECT"
```

### Read recent errors

```bash
gcloud logging read 'severity>=ERROR resource.type="cloud_run_revision"' \
  --limit=50 --format='value(jsonPayload.message)' --project="$GCP_PROJECT"
```

### Rotate the bearer token

> Plan a short outage window — the Skill will 401 between step 2 and step 3.

```bash
NEW=$(openssl rand -hex 32)
echo -n "$NEW" | gcloud secrets versions add grace-mcp-bearer-token \
  --data-file=- --project="$GCP_PROJECT"
# Force a Cloud Run revision so the new secret value is picked up:
NONCE=$(date +%s)
for svc in grace-site-mirror grace-sheets grace-slack grace-orchestrator; do
  gcloud run services update "$svc" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --update-env-vars="ROTATION_NONCE=$NONCE"
done
# Then update the Anthropic project's MCP server configs with $NEW.
```

### Rotate the Slack bot token

```bash
echo -n "xoxb-NEW…" | gcloud secrets versions add grace-slack-bot-token \
  --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-slack \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

### Update the Apps Script URL

```bash
echo -n "https://script.google.com/macros/s/NEW…/exec" | \
  gcloud secrets versions add grace-apps-script-url \
  --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-site-mirror \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

### Update the authoritative-sender list

```bash
echo -n "U…,U…,U…,U…,U…,U…" | \
  gcloud secrets versions add grace-authoritative-slack-user-ids \
  --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-slack \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

### Rollback a service

```bash
gcloud run services update-traffic grace-orchestrator \
  --to-revisions=grace-orchestrator-00012-abc=100 \
  --region="$GCP_REGION" --project="$GCP_PROJECT"
```

### Teardown

```bash
# Delete the secret values first (Terraform won't manage secret versions).
for s in grace-mcp-bearer-token grace-slack-bot-token \
         grace-apps-script-url grace-authoritative-slack-user-ids; do
  gcloud secrets delete "$s" --project="$GCP_PROJECT" --quiet
done
cd infra/terraform && terraform destroy
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `/healthz` 200 but `/mcp/...` 401 with correct token | Skill MCP server config has stale bearer | Update Anthropic console |
| `grace-sheets` returns `upstream_error: permission denied` | Runtime SA missing Editor on Tracker / Viewer on Drive Map | Re-do step 5 |
| `grace-slack` returns `no_results` + `warning: AUTHORITATIVE_SLACK_USER_IDS env var not set` | Secret value empty or not redeployed | Re-add secret + nonce env update |
| `grace-site-mirror` returns `upstream_error: request failed` | Apps Script down or wrong URL | curl the URL directly (step 2) |
| Cloud Run service stuck at "Provisioning" | Image tag doesn't exist | Run GHA deploy on `main` |
| `gcloud run deploy` fails with permission denied | Deployer SA missing `roles/run.admin` | `terraform apply` (re-creates IAM) |
| WIF authentication fails in GHA | Wrong `github_repo` in tfvars | Update tfvars, `terraform apply` |
| Tests pass locally, fail in CI | Different Python version | `.python-version` pins 3.12; check GHA logs |
| Internal URL appears in a response | Bug — file a P0 | `url_canon.py` must scrub everything |

---

## Cost envelope

| Component | Typical monthly cost |
|-----------|----------------------|
| Cloud Run × 4 (min=0, ~10K req/mo) | $0 – $5 |
| Cloud Logging + Monitoring | < $5 |
| Secret Manager (4 secrets) | < $1 |
| Artifact Registry (4 images) | < $1 |
| **Total** | **~$5 – $15 / month** |

Set `min_instances = 1` to eliminate cold starts at ~$30/mo per service
(~$120/mo total).

---

## Acceptance checklist

A deployment is **acceptable** when all of these hold:

- [ ] `terraform apply` succeeded, all 4 Cloud Run services healthy.
- [ ] All 4 services return 200 on `/healthz`.
- [ ] All 4 services return 401 on `/mcp/*` without a bearer; 200 with correct bearer.
- [ ] `site_mirror_search` returns `sites.google.com/zennify.com/...` URLs only; never the mirror doc ID or Apps Script URL.
- [ ] `drive_map_search("delivery checklist")` top result starts with `ZS_` and has score > 100.
- [ ] `drive_doc_read` on a known ZS_ doc returns non-empty `text`.
- [ ] `slack_search_pmo` defaults to `authoritative_only=true`, reports `authoritative_senders_configured: 6`, and only auth senders appear.
- [ ] `pmo_retrieve_grounding_bundle` returns all 3 tiers' statuses; failing tiers don't kill the others.
- [ ] Skill in Claude project: off-topic question → canned refusal verbatim.
- [ ] Skill: in-scope question → grounded answer with grounding block.
- [ ] Skill: "make it specific to Zennify" → fresh MCP calls (verifiable in Cloud Logging).
- [ ] Skill: no response contains the mirror doc ID or Apps Script URL.
- [ ] Skill: no response contains "typically", "generally", "as I mentioned earlier", or other forbidden inference markers.
