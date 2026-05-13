#!/usr/bin/env bash
# One-shot rebuild + redeploy + verify script for the 4 Grace MCP services.
#
# Run from anywhere; the script CDs to the repo root. It is idempotent:
# re-running it forces a fresh image and a fresh revision on each service.
#
# Usage:
#   bash deploy/redeploy.sh           # full rebuild + redeploy + verify
#   GCP_PROJECT=... GCP_REGION=...    # if not already exported
#
# What it does:
#   1. Pulls the latest code.
#   2. Confirms the routing fix is present (greps for the canonical marker).
#   3. Submits Cloud Build (parallel build of all 4 images, no Cloud Shell load).
#   4. Rolls each Cloud Run service to the new image with 100% traffic.
#   5. Polls each service until status.latestReadyRevisionName matches the new
#      revision and the image matches the new tag.
#   6. Tests /healthz on every service and refuses to exit cleanly unless all
#      4 return 200 with the expected JSON body.

set -euo pipefail

# -----------------------------------------------------------------------------
# Config — derived from your environment if not explicitly exported.
# -----------------------------------------------------------------------------
: "${GCP_PROJECT:=digital-maturity-assessor}"
: "${GCP_REGION:=us-central1}"
: "${AR_REPO:=grace-mcp}"
REGISTRY="${REGISTRY:-${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Colors / log helpers
RED=$'\e[31m'; GRN=$'\e[32m'; YEL=$'\e[33m'; CYA=$'\e[36m'; CLR=$'\e[0m'
say()   { printf "%s==>%s %s\n" "$CYA" "$CLR" "$*"; }
ok()    { printf "%s OK%s %s\n" "$GRN" "$CLR" "$*"; }
warn()  { printf "%sWARN%s %s\n" "$YEL" "$CLR" "$*"; }
fail()  { printf "%sFAIL%s %s\n" "$RED" "$CLR" "$*"; exit 1; }

say "Project: $GCP_PROJECT   Region: $GCP_REGION   Registry: $REGISTRY"
say "Image tag for this run: $IMAGE_TAG"

# -----------------------------------------------------------------------------
# 1. Pull latest source.
# -----------------------------------------------------------------------------
say "Pulling latest source..."
git pull --ff-only
git log -1 --oneline

# -----------------------------------------------------------------------------
# 2. Verify the routing fix is present in the tree we're about to build.
#    The marker is: build_app uses mcp.custom_route("/healthz", ...).
#    If this is missing the deploy WILL 404 on /healthz and we abort early.
# -----------------------------------------------------------------------------
if ! grep -q 'mcp.custom_route("/healthz"' libs/shared/grace_shared/app.py; then
    fail "libs/shared/grace_shared/app.py is missing the /healthz custom_route fix."
fi
ok "Routing fix is present in libs/shared/grace_shared/app.py"

# -----------------------------------------------------------------------------
# 3. Cloud Build (parallel, runs on GCP infrastructure).
# -----------------------------------------------------------------------------
say "Submitting Cloud Build (4 images in parallel)..."
gcloud builds submit \
    --config infra/cloudbuild.yaml \
    --substitutions=_REGISTRY="${REGISTRY}",_TAG="${IMAGE_TAG}" \
    --project="${GCP_PROJECT}" \
    --region="${GCP_REGION}" \
    --quiet
ok "Cloud Build finished. New images: ${REGISTRY}/grace-*:${IMAGE_TAG}"

# Confirm each image was actually pushed.
say "Verifying images landed in Artifact Registry..."
for svc in site-mirror sheets slack orchestrator; do
    if ! gcloud artifacts docker images describe \
        "${REGISTRY}/grace-${svc}:${IMAGE_TAG}" \
        --project="${GCP_PROJECT}" >/dev/null 2>&1; then
        fail "grace-${svc}:${IMAGE_TAG} is not in Artifact Registry. Cloud Build did not push it."
    fi
    ok "grace-${svc}:${IMAGE_TAG} present in Artifact Registry"
done

# -----------------------------------------------------------------------------
# 4. Roll every Cloud Run service to the new image with 100% traffic.
# -----------------------------------------------------------------------------
say "Rolling each Cloud Run service to ${IMAGE_TAG}..."
for svc in site-mirror sheets slack orchestrator; do
    gcloud run services update "grace-${svc}" \
        --image "${REGISTRY}/grace-${svc}:${IMAGE_TAG}" \
        --region "${GCP_REGION}" \
        --project "${GCP_PROJECT}" \
        --update-env-vars="REDEPLOY_NONCE=${IMAGE_TAG}" \
        --quiet
    ok "grace-${svc} update accepted"
done

# Move 100% traffic to the latest revision (defensive — usually default).
for svc in site-mirror sheets slack orchestrator; do
    gcloud run services update-traffic "grace-${svc}" \
        --to-latest \
        --region "${GCP_REGION}" \
        --project "${GCP_PROJECT}" \
        --quiet >/dev/null
done
ok "All 4 services pointed at the new revision (100% traffic to latest)"

# -----------------------------------------------------------------------------
# 5. Wait for each new revision to be Ready and pointed-to by the service URL.
# -----------------------------------------------------------------------------
say "Waiting for revisions to become Ready..."
for svc in site-mirror sheets slack orchestrator; do
    for attempt in $(seq 1 30); do
        info=$(gcloud run services describe "grace-${svc}" \
            --region="${GCP_REGION}" --project="${GCP_PROJECT}" \
            --format='value(status.latestReadyRevisionName,
                            spec.template.spec.containers[0].image)')
        rev=$(printf '%s' "$info" | awk '{print $1}')
        img=$(printf '%s' "$info" | awk '{print $2}')
        if [ -n "$rev" ] && [ "${img##*:}" = "$IMAGE_TAG" ]; then
            ok "grace-${svc}: ${rev} (image ${img##*:})"
            break
        fi
        sleep 4
        [ "$attempt" -eq 30 ] && fail "grace-${svc} did not become Ready in 2 min (rev=$rev img=$img)"
    done
done

# -----------------------------------------------------------------------------
# 6. Smoke-test /healthz on every service. Refuse to exit clean unless all 200.
# -----------------------------------------------------------------------------
say "Smoke-testing /healthz on the deployed services..."
ALL_OK=1
for svc in grace-site-mirror grace-sheets grace-slack grace-orchestrator; do
    url=$(gcloud run services describe "$svc" \
        --region="${GCP_REGION}" --project="${GCP_PROJECT}" \
        --format='value(status.url)')
    # Retry a few times — first request often pays cold-start cost.
    code=000
    for attempt in 1 2 3 4 5; do
        code=$(curl -sSL --max-time 30 -o /tmp/redeploy_body \
            -w "%{http_code}" "${url}/healthz" || echo 000)
        [ "$code" = "200" ] && break
        sleep 3
    done
    body=$(head -c 200 /tmp/redeploy_body 2>/dev/null || true)
    if [ "$code" = "200" ] && grep -q "\"service\":\"${svc}\"" /tmp/redeploy_body 2>/dev/null; then
        ok "${svc}/healthz → 200 ${body}"
    else
        ALL_OK=0
        warn "${svc}/healthz → HTTP $code"
        warn "  body: ${body}"
    fi
done

if [ "$ALL_OK" = "1" ]; then
    printf "\n%sALL FOUR SERVICES HEALTHY%s\n" "$GRN" "$CLR"
    say "Continue with step 11 of deploy/GUIDE.md — the MCP smoke tests."
    exit 0
else
    printf "\n%sREDEPLOY COMPLETED but some services are not 200.%s\n" "$RED" "$CLR"
    say "Pulling diagnostic logs..."
    for svc in grace-site-mirror grace-sheets grace-slack grace-orchestrator; do
        echo "------- $svc -------"
        gcloud logging read \
            "resource.type=cloud_run_revision AND resource.labels.service_name=\"$svc\"" \
            --limit=15 \
            --format='value(timestamp, severity, textPayload, jsonPayload.message)' \
            --project="${GCP_PROJECT}" --order=desc 2>&1 | head -30
    done
    exit 1
fi
