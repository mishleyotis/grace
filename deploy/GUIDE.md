# Grace — Deployment Guide (Cloud Run via bash/CLI)

End-to-end deployment of the four Grace MCP services and the
`grace-pmo-director` Skill using **only `gcloud` and `docker` on your
shell**, into the existing GCP project `digital-maturity-assessor` (billing
already enabled). No Terraform, no GitHub Actions, no Workload Identity
Federation. Estimated total time: **~40 minutes** of operator work plus
image-build time.

> Pre-reqs: project-owner (or equivalent) rights on
> `digital-maturity-assessor`, Workspace admin to share Drive/Sheets
> resources, Slack workspace admin to install a bot app, an Anthropic
> Claude account.
>
> Tools on your workstation: `gcloud` (>=470), `docker` (>=24), `openssl`,
> `curl`, `jq`. Optional: `uv` if you want to re-run the test suite.

> **Note on the OAuth web client you provided** (client_id
> `306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp...` with redirect
> `https://oauth.n8n.cloud/oauth2/callback`): that's an unrelated 3-legged
> OAuth client (used by n8n). Grace's runtime uses **service-account
> credentials**, not 3LO — we do not reference that client_id, the client
> secret, or its redirect anywhere below. Don't paste its credentials into
> Secret Manager or the source tree.

> **Need IaC instead?** `infra/terraform/` is the equivalent Terraform
> module; `.github/workflows/deploy.yml` runs the same steps via WIF.
> This guide is the **manual CLI alternative**.

---

## At a glance

| # | Step | Time |
|---|------|------|
| 0 | Set shell variables + activate the project | 2 min |
| 1 | Enable required APIs | 1 min |
| 2 | Create the Artifact Registry repo | 1 min |
| 3 | Create the runtime service account | 2 min |
| 4 | Verify the SiteMirrorQuery Apps Script | 1 min |
| 5 | Share Drive Map, Tracker, ZennSource Drive with the runtime SA | 5 min |
| 6 | Create the Slack bot + look up the 6 user IDs | 10 min |
| 7 | Create + populate the 4 secrets | 4 min |
| 8 | Build + push the 4 images | 8 min |
| 9 | Deploy `grace-site-mirror`, `grace-sheets`, `grace-slack` | 4 min |
| 10 | Deploy `grace-orchestrator` | 2 min |
| 11 | Run the 7 smoke tests | 5 min |
| 12 | Build + upload the Skill, wire MCPs in the Claude project | 5 min |

---

## Step 0 — Shell variables + project

These pin the deploy to the existing `digital-maturity-assessor` project.
**Open one shell and keep it open through the whole deploy.**

```bash
# ──── Pinned to the project you specified ─────────────────────────────
export GCP_PROJECT="digital-maturity-assessor"
export GCP_REGION="us-central1"

# ──── Resource names — usually fine to leave as-is ────────────────────
export AR_REPO="grace-mcp"
export RUNTIME_SA_NAME="grace-mcp-runtime"
export RUNTIME_SA="${RUNTIME_SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
export REGISTRY="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}"
export IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"   # bump on each redeploy
```

Authenticate and select the project:

```bash
gcloud auth login                       # opens browser
gcloud auth application-default login   # one-time, used for the verify step in step 5
gcloud config set project "$GCP_PROJECT"

# Sanity check — should print 'digital-maturity-assessor'
gcloud config get-value project

# Confirm billing is already linked (skip the "link billing" step entirely).
gcloud beta billing projects describe "$GCP_PROJECT" \
  --format='value(billingEnabled, billingAccountName)'
# Expected: True   billingAccounts/XXXXXX-XXXXXX-XXXXXX
```

If the second command shows `billingEnabled=False`, link a billing account
before continuing:

```bash
# Optional — only if billing isn't already enabled.
# gcloud beta billing projects link "$GCP_PROJECT" \
#   --billing-account=XXXXXX-XXXXXX-XXXXXX
```

---

## Step 1 — Enable the required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  sheets.googleapis.com \
  drive.googleapis.com \
  --project="$GCP_PROJECT"
```

This takes ~30 seconds to fully propagate.

---

## Step 2 — Create the Artifact Registry repo

```bash
# Idempotent: if the repo already exists, that's fine — keep going.
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker \
  --location="$GCP_REGION" \
  --description="Grace MCP service images" \
  --project="$GCP_PROJECT" 2>/dev/null || \
  echo "Repo $AR_REPO already exists in $GCP_REGION — continuing."

# Configure docker to authenticate against this registry.
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet
```

---

## Step 3 — Runtime service account

All 4 Cloud Run services run as this single SA.

```bash
# Idempotent: SA may already exist from a previous run.
gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
  --display-name="Grace MCP runtime" \
  --project="$GCP_PROJECT" 2>/dev/null || \
  echo "SA $RUNTIME_SA already exists — continuing."

# add-iam-policy-binding is naturally idempotent; safe to re-run.
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None

echo "Share Drive/Tracker resources with: $RUNTIME_SA"
```

Make sure your own user can act-as the runtime SA when running
`gcloud run deploy` (this is the most common deploy-time permission error):

```bash
ME=$(gcloud config get-value account)
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="user:${ME}" \
  --role="roles/iam.serviceAccountUser" \
  --project="$GCP_PROJECT"
```

---

## Step 4 — Verify the SiteMirrorQuery Apps Script

```bash
export APPS_SCRIPT_URL="https://script.google.com/macros/s/AKfycbyCJ5Fkyw8JySwT5G-aqWTDAtR6nN8n-Nv-PifbnOHJ4_gxkXwjWXl162Pl-Tjf3fE0/exec"

# The -L is required: Apps Script /exec always 302s to a
# script.googleusercontent.com URL that returns the JSON body.
curl -sSL "${APPS_SCRIPT_URL}?action=getURLIndex" | jq '.totalPages, (.sections | length)'
```

You should see `63` printed twice. The runtime client uses
`httpx.AsyncClient(follow_redirects=True)`, so the service handles the
redirect transparently.

The live script is **SiteMirrorQuery v3** — its real response shape differs
from the original design spec:

- `getURLIndex` returns `{sections: [...]}` (not `pages`) with
  `pageName`/`paraStart`/`paraEnd`
- `searchSections` requires `q=` (not `query=`)
- `getNavMap` returns `{entries: [...]}` (not a nested tree)
- `getLinkIndex` requires `page=` (not `name=`)
- `searchSections` auto-expands abbreviations: `SOW` → "Statement of Work",
  `PM` → "Project Manager", `KO` → "Kickoff", `UAT`, `SIT`, `CR`, `QA`,
  `Dev`, `SF`, `CSAT`. The expanded form comes back as `queryNormalized`.

`grace-site-mirror` is already aligned with v3 — both request param names
and response keys. No action needed on your side.

### Optional but recommended: warm the v3 snapshot cache

The v3 script builds a 5,937-paragraph snapshot the first time it's asked
to do real work. To avoid the first user-facing query paying that 20-30s
cost, the script owner should open the Apps Script editor for the
SiteMirrorQuery project once and run the `rebuildSnapshot` function:

1. Open the Apps Script project (the one whose deployment owns
   `AKfycby...Tjf3fE0`).
2. In the editor, choose the function `rebuildSnapshot` from the function
   dropdown.
3. Click **Run**. Authorize if prompted. Wait ~30 seconds for the log to
   show `rebuildSnapshot complete`.

The snapshot is then cached for 6 hours in `CacheService` and ~24 hours on
Drive. The script's own header recommends adding a **daily time-driven
trigger** on `rebuildSnapshot` to keep the cache fresh — the operator can
add this via Apps Script editor → **Triggers** → "Add Trigger" →
`rebuildSnapshot` / Time-driven / Day timer.

### Troubleshooting: `jq: parse error: Invalid numeric literal`

This means **`curl` was not following the Apps Script 302 redirect**, so
`jq` saw the redirect's HTML body instead of the JSON. The fix is the `-L`
flag (already in the command above). If you still see the error, inspect
the full exchange:

```bash
curl -sSL -i "${APPS_SCRIPT_URL}?action=getURLIndex" | head -c 1500; echo
```

A healthy response looks like:

```
HTTP/2 302
location: https://script.googleusercontent.com/macros/echo?...

HTTP/2 200
content-type: application/json; charset=utf-8
...
{"action":"getURLIndex","totalPages":63,"mirrorDocId":"...","sections":[...]}
```

If the second response is **not** `application/json`, you're hitting one
of the real Apps Script problems:

| Body of the 200 response | Cause | Fix |
|--------------------------|-------|-----|
| HTML "Sign in to continue" / redirect to `accounts.google.com/ServiceLogin` | Apps Script deployed with **Who has access: Only myself / org** | Script owner: Apps Script editor → **Deploy → Manage deployments → ✏️** → **Who has access: Anyone** |
| HTML mentioning "Authorization is required" | Script execution identity lost access to the mirror doc | Script owner opens the script editor and runs any function once to re-authorize |
| `HTTP/2 404` or "Sorry, unable to open the file at this time." | Deployment was rotated → new `/exec` URL | Get the new `/exec` URL from the script owner; update `APPS_SCRIPT_URL` |
| `{"totalPages": 0, "sections": []}` | Mirror doc is empty (not yet populated by the upstream sync) | Script owner runs whatever job populates the mirror Google Doc, then `rebuildSnapshot()` |

If you can't fix the script right now, set a placeholder so the rest of
the deploy can proceed — `grace-site-mirror` will return `upstream_error`
on every call, and the orchestrator's per-tier failure isolation will mark
Tier 1 as `error:` while still returning Tiers 2 and 3:

```bash
# ONLY if the real URL isn't ready yet:
export APPS_SCRIPT_URL="https://script.google.com/macros/s/PLACEHOLDER/exec"
```

Later, swap in the real URL with no downtime:

```bash
printf '%s' "https://script.google.com/macros/s/REAL.../exec" | \
  gcloud secrets versions add grace-apps-script-url \
    --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-site-mirror \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

---

## Step 5 — Share Workspace resources with the runtime SA

Drive / Sheets ACLs are **Workspace-managed**, not GCP-managed. Do this in
the Google Workspace UI as a Workspace admin (or via the Drive UI for each
resource):

| Resource | Access | Email to share with |
|----------|--------|----------------------|
| Drive Map sheet (`19VQxsUb7pnnxTWP0vQzLLjIZWKU3k382lOEVYSnyiKE`) | **Viewer** | `$RUNTIME_SA` |
| Onboarding Tracker (`197CSSit_xi872N8oF3_uhV-LYxvRQwA42rfkknLCgEc`) | **Editor** | `$RUNTIME_SA` |
| ZennSource shared Drive (`0AGq-3ZBpQU5MUk9PVA`) | **Viewer** (drive-level member) | `$RUNTIME_SA` |

Verify after sharing (your own ADC creds are fine for this check):

```bash
gcloud auth application-default print-access-token \
  | xargs -I {} curl -sS -H "Authorization: Bearer {}" \
    "https://www.googleapis.com/drive/v3/files/19VQxsUb7pnnxTWP0vQzLLjIZWKU3k382lOEVYSnyiKE?fields=id,name&supportsAllDrives=true"
```

Expect a JSON body with the file's `id` and `name`. 403/404 means the
share hasn't propagated yet — wait ~60 s and retry.

---

## Step 6 — Slack bot + authoritative-sender IDs

1. Create a Slack app at https://api.slack.com/apps?new_app=1 ("From
   scratch").
   - Name: `Grace PMO Bot`
   - Workspace: Zennify
2. **OAuth & Permissions → Bot Token Scopes:** add `channels:history`,
   `channels:read`, `users:read`.
3. **Install to workspace** and copy the `xoxb-…` Bot User OAuth Token.
4. Invite the bot to `#zennify_pmo`:

   ```
   /invite @grace-pmo-bot
   ```

5. Look up the **6 authoritative senders' Slack user IDs**. In the Slack
   client: profile → ••• → "Copy member ID":

   | Name | User ID |
   |------|---------|
   | Kallen | U… |
   | Mike Theiler | U… |
   | Bryan Babb | U… |
   | Stephanie Brooks | U… |
   | Michael Rouleau | U… |
   | Tom Hedgecoth | U… |

6. Stash the values for step 7:

   ```bash
   export SLACK_BOT_TOKEN="xoxb-XXXXXXXXXXXXX-XXXXXXXXXXXXX-XXXXXXXXXXXXXXXX"
   export AUTH_SLACK_IDS="U03ABC,U04DEF,U05GHI,U06JKL,U07MNO,U08PQR"
   ```

---

## Step 7 — Create + populate the 4 secrets

```bash
# Generate a strong bearer token (one shared across the 4 services + Skill).
export BEARER_TOKEN="$(openssl rand -hex 32)"

# Create the secret resources (idempotent — `|| true` so re-runs are safe).
for s in grace-mcp-bearer-token grace-slack-bot-token \
         grace-apps-script-url grace-authoritative-slack-user-ids; do
  gcloud secrets create "$s" --replication-policy=automatic \
    --project="$GCP_PROJECT" 2>/dev/null || true
done

# Add a version (the actual value) for each.
printf '%s' "$BEARER_TOKEN" | gcloud secrets versions add \
  grace-mcp-bearer-token --data-file=- --project="$GCP_PROJECT"

printf '%s' "$SLACK_BOT_TOKEN" | gcloud secrets versions add \
  grace-slack-bot-token --data-file=- --project="$GCP_PROJECT"

printf '%s' "$APPS_SCRIPT_URL" | gcloud secrets versions add \
  grace-apps-script-url --data-file=- --project="$GCP_PROJECT"

printf '%s' "$AUTH_SLACK_IDS" | gcloud secrets versions add \
  grace-authoritative-slack-user-ids --data-file=- --project="$GCP_PROJECT"

# Per-secret accessor bindings for the runtime SA (good hygiene; the
# project-level binding from step 3 already covers it).
for s in grace-mcp-bearer-token grace-slack-bot-token \
         grace-apps-script-url grace-authoritative-slack-user-ids; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$GCP_PROJECT" >/dev/null
done

# Confirm.
for s in grace-mcp-bearer-token grace-slack-bot-token \
         grace-apps-script-url grace-authoritative-slack-user-ids; do
  echo "=== $s ==="
  gcloud secrets versions list "$s" --project="$GCP_PROJECT" --limit=1
done
```

> **Important:** `printf '%s'` avoids the trailing newline `echo -n` may
> emit on some shells; the bearer-token check rejects mismatches strictly.

---

## Step 8 — Build + push the 4 Docker images

Run from the **repo root** (`grace-pmo-mcp/`):

```bash
cd /path/to/grace-pmo-mcp

for svc in site-mirror sheets slack orchestrator; do
  echo "==== Building grace-${svc}:${IMAGE_TAG} ===="
  docker build \
    -f "services/${svc}/Dockerfile" \
    -t "${REGISTRY}/grace-${svc}:${IMAGE_TAG}" \
    -t "${REGISTRY}/grace-${svc}:latest" \
    .
  docker push "${REGISTRY}/grace-${svc}:${IMAGE_TAG}"
  docker push "${REGISTRY}/grace-${svc}:latest"
done
```

> Each Dockerfile reads `pyproject.toml`, `libs/shared/`, and its own
> `services/<svc>/`. The build context is the repo root.

> On Apple Silicon, prepend `DOCKER_DEFAULT_PLATFORM=linux/amd64` so the
> images run on Cloud Run.

---

## Step 9 — Deploy the 3 leaf services

The orchestrator needs the 3 leaf URLs as env vars, so deploy in two waves.
Each service is public-ingress; auth is enforced at the app layer via the
shared bearer token.

```bash
# ---------- grace-site-mirror ----------
gcloud run deploy grace-site-mirror \
  --image "${REGISTRY}/grace-site-mirror:${IMAGE_TAG}" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --ingress all \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080 \
  --set-env-vars "GCP_PROJECT=${GCP_PROJECT},LOG_LEVEL=INFO" \
  --set-secrets "MCP_BEARER_TOKEN=grace-mcp-bearer-token:latest,APPS_SCRIPT_URL=grace-apps-script-url:latest"

# ---------- grace-sheets ----------
gcloud run deploy grace-sheets \
  --image "${REGISTRY}/grace-sheets:${IMAGE_TAG}" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --ingress all \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080 \
  --set-env-vars "GCP_PROJECT=${GCP_PROJECT},LOG_LEVEL=INFO" \
  --set-secrets "MCP_BEARER_TOKEN=grace-mcp-bearer-token:latest"

# ---------- grace-slack ----------
gcloud run deploy grace-slack \
  --image "${REGISTRY}/grace-slack:${IMAGE_TAG}" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --ingress all \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080 \
  --set-env-vars "GCP_PROJECT=${GCP_PROJECT},LOG_LEVEL=INFO" \
  --set-secrets "MCP_BEARER_TOKEN=grace-mcp-bearer-token:latest,SLACK_BOT_TOKEN=grace-slack-bot-token:latest,AUTHORITATIVE_SLACK_USER_IDS=grace-authoritative-slack-user-ids:latest"
```

Capture the three URLs:

```bash
export SITE_MIRROR_URL=$(gcloud run services describe grace-site-mirror \
  --region "$GCP_REGION" --project "$GCP_PROJECT" --format='value(status.url)')
export SHEETS_URL=$(gcloud run services describe grace-sheets \
  --region "$GCP_REGION" --project "$GCP_PROJECT" --format='value(status.url)')
export SLACK_URL=$(gcloud run services describe grace-slack \
  --region "$GCP_REGION" --project "$GCP_PROJECT" --format='value(status.url)')

echo "site-mirror: $SITE_MIRROR_URL"
echo "sheets:      $SHEETS_URL"
echo "slack:       $SLACK_URL"
```

---

## Step 10 — Deploy `grace-orchestrator`

```bash
gcloud run deploy grace-orchestrator \
  --image "${REGISTRY}/grace-orchestrator:${IMAGE_TAG}" \
  --region "$GCP_REGION" \
  --project "$GCP_PROJECT" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --ingress all \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080 \
  --set-env-vars "GCP_PROJECT=${GCP_PROJECT},LOG_LEVEL=INFO,SITE_MIRROR_URL=${SITE_MIRROR_URL},SHEETS_URL=${SHEETS_URL},SLACK_URL=${SLACK_URL}" \
  --set-secrets "MCP_BEARER_TOKEN=grace-mcp-bearer-token:latest"

export ORCHESTRATOR_URL=$(gcloud run services describe grace-orchestrator \
  --region "$GCP_REGION" --project "$GCP_PROJECT" --format='value(status.url)')

echo "orchestrator: $ORCHESTRATOR_URL"
```

> If you later redeploy a leaf in a different region, update the
> orchestrator with `gcloud run services update grace-orchestrator
> --update-env-vars=...` and bump `ROTATION_NONCE` to force a new revision.

---

## Step 11 — Smoke tests (7 checks)

These mirror the E2E suite from the solution design (section 11.1).

**E2E-1 — All 4 services healthy:**

```bash
for URL in "$SITE_MIRROR_URL" "$SHEETS_URL" "$SLACK_URL" "$ORCHESTRATOR_URL"; do
  echo "=== $URL ==="
  curl -sS "$URL/healthz" -w "\nHTTP %{http_code}\n"
done
```

Each must return `{"status":"ok","service":"<name>"}` with HTTP 200.

**E2E-2 — Bearer auth gate:**

```bash
# Without bearer -> 401
curl -sS -o /dev/null -w "without bearer: %{http_code}\n" "$ORCHESTRATOR_URL/mcp/"

# With the right bearer -> 200 (or 405/406 from MCP discovery, NOT 401)
curl -sS -o /dev/null -w "with bearer:    %{http_code}\n" \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"x","method":"tools/list"}' \
  "$ORCHESTRATOR_URL/mcp/"
```

A small helper for the remaining checks:

```bash
mcp_call () {
  local url=$1 tool=$2 args=$3
  curl -sS -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "Accept: application/json, text/event-stream" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":\"smoke\",\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":$args}}" \
    "$url/mcp/"
}

# Helper to parse MCP responses that come back as Server-Sent Events.
mcp_parse () {
  tr -d '\r' | awk '/^data: /{sub(/^data: /, ""); print}' | jq -c .
}
```

**E2E-3 — Tier 1 canonical URLs (no internal-URL leakage):**

```bash
RESP=$(mcp_call "$SITE_MIRROR_URL" site_mirror_search '{"query":"kickoff","limit":3}' | mcp_parse)
echo "$RESP" | jq '.result.structuredContent | {status, n: (.results|length), query_normalized}'

# Every siteUrl is canonical:
echo "$RESP" \
  | jq -r '.result.structuredContent.results[].siteUrl' \
  | grep -qE '^https://sites\.google\.com/zennify\.com/delivery/' \
  && echo "siteUrl PASS" || echo "siteUrl FAIL"

# Internal URLs never leak (mirror doc ID or Apps Script prefix):
echo "$RESP" \
  | grep -qE '(1KIudQjWefyoQfbdKMCVahIn3DOn-YNeo0KoZfdrB990|script\.google\.com/macros/s/)' \
  && echo "LEAK DETECTED — investigate url_canon" || echo "leak PASS"
```

Expected: `siteUrl PASS` and `leak PASS`. Note `query_normalized` —
the v3 script expands `KO` → "Kickoff", `SOW` → "Statement of Work", etc.,
so a query for `SOW` will round-trip as `"Statement of Work"`.

**E2E-4 — Tier 2 ZS_ priority:**

```bash
mcp_call "$SHEETS_URL" drive_map_search '{"query":"delivery checklist","limit":5}' \
  | mcp_parse \
  | jq '.result.structuredContent.results[0] | {name, score}'
# Expect: name starts with "ZS_", score > 100.
```

**E2E-5 — `drive_doc_read` returns content:**

```bash
mcp_call "$SHEETS_URL" drive_doc_read \
  '{"file_id":"1AsE2UFl0HGouxxAwRIEsPuc2KxLY7Xw4EtKOeUPVLDQ","max_chars":2000}' \
  | mcp_parse \
  | jq '.result.structuredContent | {status, char_count, mime_type}'
# Expect: status=ok, char_count>0.
```

**E2E-6 — Slack authoritative-only default:**

```bash
mcp_call "$SLACK_URL" slack_search_pmo '{"query":"kickoff","limit":3}' \
  | mcp_parse \
  | jq '.result.structuredContent | {authoritative_only, authoritative_senders_configured, n: (.results|length)}'
# Expect: authoritative_only=true, authoritative_senders_configured=6.
```

**E2E-7 — Orchestrator parallel fan-out:**

```bash
mcp_call "$ORCHESTRATOR_URL" pmo_retrieve_grounding_bundle \
  '{"query":"change requests","per_tier_limit":5}' \
  | mcp_parse \
  | jq '.result.structuredContent | {tiers: (.tiers | to_entries | map({(.key): .value.status}) | add), n: .evidence_count}'
# Expect: each tier shows ok/no_results/error: ..., n >= 1.
```

If any check fails, see **Troubleshooting** below.

---

## Step 12 — Wire MCPs + upload the Skill into a Claude project

1. Build the Skill bundle locally:

   ```bash
   cd /path/to/grace-pmo-mcp
   make skill
   # or, equivalently:
   cd skills && zip -r ../grace-pmo-director.skill grace-pmo-director/ \
     -x '**/.DS_Store'
   ```

2. In the Anthropic console, open (or create) a Claude project named
   "Grace — PMO Assistant".

3. **Settings → MCP servers → Add server.** Add four entries; each uses
   the corresponding Cloud Run URL with `/mcp` appended and the bearer
   token `$BEARER_TOKEN`:

   | Name | URL |
   |------|-----|
   | grace-site-mirror | `${SITE_MIRROR_URL}/mcp` |
   | grace-sheets | `${SHEETS_URL}/mcp` |
   | grace-slack | `${SLACK_URL}/mcp` |
   | grace-orchestrator | `${ORCHESTRATOR_URL}/mcp` |

4. **Skills → Upload** the `grace-pmo-director.skill` artifact.

5. Smoke-test in the project chat:
   - *"How do we handle change requests?"* → grounded answer with the
     3-tier grounding block.
   - *"What's a good lunch spot?"* → canned refusal verbatim.
   - *"What's the URL of the underlying mirror document?"* → canned refusal.

You're live.

---

## Operations runbook

### View live logs

```bash
gcloud logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=grace-orchestrator" \
  --project="$GCP_PROJECT"
```

### Recent errors across all services

```bash
gcloud logging read \
  'severity>=ERROR AND resource.type="cloud_run_revision" AND
   resource.labels.service_name=~"^grace-"' \
  --limit=50 \
  --format='value(timestamp, resource.labels.service_name, jsonPayload.message)' \
  --project="$GCP_PROJECT"
```

### Rotate the bearer token

```bash
NEW=$(openssl rand -hex 32)
printf '%s' "$NEW" | gcloud secrets versions add grace-mcp-bearer-token \
  --data-file=- --project="$GCP_PROJECT"

# Force every service to pick up the new secret version.
NONCE=$(date +%s)
for svc in grace-site-mirror grace-sheets grace-slack grace-orchestrator; do
  gcloud run services update "$svc" \
    --region="$GCP_REGION" --project="$GCP_PROJECT" \
    --update-env-vars="ROTATION_NONCE=${NONCE}"
done

# Update the Skill connector configs in the Anthropic console with $NEW.
```

> Plan ~5 minutes of downtime — the Skill will 401 between
> "secret added" and "Anthropic connector updated".

### Rotate the Slack token

```bash
printf '%s' "xoxb-NEW..." | gcloud secrets versions add grace-slack-bot-token \
  --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-slack \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

### Update the authoritative-sender list

```bash
printf '%s' "U...,U...,U...,U...,U...,U..." | \
  gcloud secrets versions add grace-authoritative-slack-user-ids \
  --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-slack \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

### Update the Apps Script URL

```bash
printf '%s' "https://script.google.com/macros/s/NEW.../exec" | \
  gcloud secrets versions add grace-apps-script-url \
  --data-file=- --project="$GCP_PROJECT"
gcloud run services update grace-site-mirror \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --update-env-vars="ROTATION_NONCE=$(date +%s)"
```

### Redeploy a single service (new code)

```bash
svc=sheets   # site-mirror | sheets | slack | orchestrator
TAG=$(date +%Y%m%d-%H%M%S)
docker build -f "services/${svc}/Dockerfile" \
  -t "${REGISTRY}/grace-${svc}:${TAG}" .
docker push "${REGISTRY}/grace-${svc}:${TAG}"
gcloud run deploy "grace-${svc}" \
  --image "${REGISTRY}/grace-${svc}:${TAG}" \
  --region "$GCP_REGION" --project "$GCP_PROJECT"
```

### Roll back to a previous revision

```bash
gcloud run revisions list --service grace-orchestrator \
  --region "$GCP_REGION" --project "$GCP_PROJECT"

gcloud run services update-traffic grace-orchestrator \
  --to-revisions=grace-orchestrator-00012-abc=100 \
  --region "$GCP_REGION" --project "$GCP_PROJECT"
```

### Teardown

```bash
for svc in grace-site-mirror grace-sheets grace-slack grace-orchestrator; do
  gcloud run services delete "$svc" \
    --region "$GCP_REGION" --project "$GCP_PROJECT" --quiet
done

for s in grace-mcp-bearer-token grace-slack-bot-token \
         grace-apps-script-url grace-authoritative-slack-user-ids; do
  gcloud secrets delete "$s" --project="$GCP_PROJECT" --quiet
done

gcloud artifacts repositories delete "$AR_REPO" \
  --location "$GCP_REGION" --project "$GCP_PROJECT" --quiet

gcloud iam service-accounts delete "$RUNTIME_SA" \
  --project "$GCP_PROJECT" --quiet
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `/healthz` 200 but `/mcp/` 401 with correct token | Skill connector has stale bearer | Update the bearer in the Anthropic console |
| `grace-sheets` returns `upstream_error: permission denied` | Runtime SA missing Editor on Tracker / Viewer on Drive Map | Re-do step 5 |
| `grace-slack` returns `no_results` + `warning: AUTHORITATIVE_SLACK_USER_IDS env var not set` | Secret value empty or service not redeployed with the new version | Re-add the secret + `ROTATION_NONCE` update |
| `grace-site-mirror` returns `upstream_error: request failed` | Apps Script URL wrong or rate-limited | Re-check step 4 |
| Cloud Run service stuck "Provisioning" | Image tag not in Artifact Registry | Re-run `docker push` from step 8 |
| `gcloud run deploy` fails with `PERMISSION_DENIED` on secret | Runtime SA missing `secretmanager.secretAccessor` | Re-do step 3 |
| `gcloud run deploy` fails with `iam.serviceAccountUser` denied | Your gcloud principal can't act as `$RUNTIME_SA` | Re-run the `add-iam-policy-binding` at the end of step 3 |
| Orchestrator returns `error: UpstreamError` for one tier | Tier URL env var missing | `gcloud run services describe grace-orchestrator` and inspect `SITE_MIRROR_URL` / `SHEETS_URL` / `SLACK_URL`; redeploy with `--update-env-vars` if needed |
| Image runs on M1/M2 Mac but crashes on Cloud Run | ARM image pushed | Re-build with `DOCKER_DEFAULT_PLATFORM=linux/amd64` |
| MCP smoke calls return `text/event-stream` and `jq` fails | SSE response, not JSON | Pipe through `mcp_parse` from step 11 |
| Internal URL leaks into any response | Bug — file a P0 | `url_canon.py` is supposed to scrub; check `grace_shared.url_canon` and the Site Mirror tools |
| `gcloud beta billing projects describe` shows `billingEnabled=False` | Project lost its billing link | Re-link a billing account before continuing |

---

## Cost envelope

| Component | Typical monthly cost |
|-----------|----------------------|
| Cloud Run × 4 (min=0, ~10K req/mo) | $0 – $5 |
| Cloud Logging + Monitoring | < $5 |
| Secret Manager (4 secrets) | < $1 |
| Artifact Registry (4 images) | < $1 |
| **Total** | **~$5 – $15 / month** |

To eliminate cold starts (~5–8 s on a cold service), bump `--min-instances`
to `1` on each `gcloud run deploy` — adds ~$30/mo per service (~$120/mo
across all 4).

---

## Acceptance checklist

A deployment is **acceptable** when all of these hold:

- [ ] All 4 services return 200 on `/healthz`.
- [ ] All 4 services return 401 on `/mcp/` without a bearer; 2xx with the correct bearer.
- [ ] `site_mirror_search("kickoff")` returns only `sites.google.com/zennify.com/...` URLs; never the mirror doc ID or the Apps Script URL.
- [ ] `drive_map_search("delivery checklist")` top result starts with `ZS_` and has score > 100.
- [ ] `drive_doc_read(<ZS_doc_id>)` returns non-empty `text`.
- [ ] `slack_search_pmo("kickoff")` defaults to `authoritative_only=true`, reports `authoritative_senders_configured: 6`, and every result has `is_authoritative: true`.
- [ ] `pmo_retrieve_grounding_bundle("...")` returns all 3 tiers' statuses; a single tier failing returns the other two's results.
- [ ] Skill in Claude project: off-topic question → canned refusal verbatim.
- [ ] Skill: in-scope question → grounded answer with the 3-tier grounding block.
- [ ] Skill: "Make it specific to Zennify" → fresh MCP calls (verifiable in Cloud Logging).
- [ ] Skill: no response contains the mirror doc ID or Apps Script URL.
- [ ] Skill: no response contains "typically", "generally", "as I mentioned earlier", or any other forbidden inference marker.

---

## Appendix A — One-shot redeploy script

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${GCP_PROJECT?}"; : "${GCP_REGION?}"; : "${REGISTRY?}"; : "${RUNTIME_SA?}"

TAG=$(date +%Y%m%d-%H%M%S)

for svc in site-mirror sheets slack orchestrator; do
  echo "==== build+push grace-${svc}:${TAG} ===="
  docker build -f "services/${svc}/Dockerfile" \
    -t "${REGISTRY}/grace-${svc}:${TAG}" \
    -t "${REGISTRY}/grace-${svc}:latest" .
  docker push "${REGISTRY}/grace-${svc}:${TAG}"
  docker push "${REGISTRY}/grace-${svc}:latest"
done

for svc in site-mirror sheets slack orchestrator; do
  gcloud run services update "grace-${svc}" \
    --image "${REGISTRY}/grace-${svc}:${TAG}" \
    --region "$GCP_REGION" --project "$GCP_PROJECT"
done

# Smoke-test
for svc in site-mirror sheets slack orchestrator; do
  url=$(gcloud run services describe "grace-${svc}" \
    --region "$GCP_REGION" --project "$GCP_PROJECT" \
    --format='value(status.url)')
  echo "$svc -> $(curl -sS -o /dev/null -w '%{http_code}' "$url/healthz")"
done
```

---

## Appendix B — MCP JSON-RPC quick reference

Every tool can be invoked from the shell with one curl call:

```bash
curl -sS \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {
          "name": "<TOOL_NAME>",
          "arguments": { <args> }
        }
      }' \
  "$URL/mcp/"
```

Tool list across the 4 services (16 total) — see
`skills/grace-pmo-director/references/mcp_tool_map.md`.

Discover tools at runtime:

```bash
curl -sS \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list"}' \
  "$URL/mcp/" | jq '.result.tools[].name'
```
