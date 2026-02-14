#!/usr/bin/env bash
#
# Sets up Google Cloud Workload Identity Federation for GitHub Actions.
# This enables keyless authentication (no JSON keys) between GitHub and GCP.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GitHub CLI installed (gh) for setting secrets automatically
#
# Usage:
#   ./scripts/setup-gcp-wif.sh <GCP_PROJECT_ID> <GITHUB_REPO>
#
# Example:
#   ./scripts/setup-gcp-wif.sh my-gcp-project bbrams/invoice-extract-v5

set -euo pipefail

# ── Args ─────────────────────────────────────────────────
PROJECT_ID="${1:?Usage: $0 <GCP_PROJECT_ID> <GITHUB_REPO>}"
GITHUB_REPO="${2:?Usage: $0 <GCP_PROJECT_ID> <GITHUB_REPO>}"

SA_NAME="github-actions-deployer"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
POOL_NAME="github-actions-pool"
PROVIDER_NAME="github-actions-provider"

echo "==> Project:     ${PROJECT_ID}"
echo "==> GitHub repo: ${GITHUB_REPO}"
echo ""

# ── 1. Enable required APIs ─────────────────────────────
echo "==> Enabling APIs..."
gcloud services enable \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  vision.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  --project="${PROJECT_ID}"

# ── 2. Create Service Account ───────────────────────────
echo "==> Creating service account: ${SA_NAME}"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="GitHub Actions Deployer" \
    --project="${PROJECT_ID}"
fi

# Grant roles needed for Cloud Functions deployment
for ROLE in roles/cloudfunctions.developer roles/iam.serviceAccountUser roles/storage.admin roles/run.invoker; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet
done
echo "    Roles granted."

# ── 3. Create Workload Identity Pool ────────────────────
echo "==> Creating Workload Identity Pool: ${POOL_NAME}"
if ! gcloud iam workload-identity-pools describe "${POOL_NAME}" \
    --location=global --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam workload-identity-pools create "${POOL_NAME}" \
    --location=global \
    --display-name="GitHub Actions Pool" \
    --project="${PROJECT_ID}"
fi

# ── 4. Create OIDC Provider (GitHub) ────────────────────
echo "==> Creating OIDC provider: ${PROVIDER_NAME}"
if ! gcloud iam workload-identity-pools providers describe "${PROVIDER_NAME}" \
    --workload-identity-pool="${POOL_NAME}" \
    --location=global --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_NAME}" \
    --workload-identity-pool="${POOL_NAME}" \
    --location=global \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    --project="${PROJECT_ID}"
fi

# ── 5. Allow GitHub repo to impersonate the SA ──────────
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/providers/${PROVIDER_NAME}"

echo "==> Binding service account to Workload Identity Pool..."
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${GITHUB_REPO}"

# ── 6. Set GitHub secrets ───────────────────────────────
echo ""
echo "==> Setting GitHub secrets on ${GITHUB_REPO}..."
if command -v gh &>/dev/null; then
  gh secret set WIF_PROVIDER        --body "${WIF_PROVIDER}"          --repo "${GITHUB_REPO}"
  gh secret set WIF_SERVICE_ACCOUNT  --body "${SA_EMAIL}"              --repo "${GITHUB_REPO}"
  echo "    Secrets set via gh CLI."
else
  echo "    gh CLI not found. Set these secrets manually in GitHub:"
  echo ""
  echo "    WIF_PROVIDER        = ${WIF_PROVIDER}"
  echo "    WIF_SERVICE_ACCOUNT = ${SA_EMAIL}"
fi

# ── 7. Optional: set GCP_REGION as a GitHub variable ────
echo ""
echo "==> (Optional) Set the deployment region as a GitHub variable:"
echo "    gh variable set GCP_REGION --body 'us-central1' --repo ${GITHUB_REPO}"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Push to main branch -> GitHub Actions will test and deploy automatically"
echo "  2. The function URL will be printed at the end of the deploy job"
echo "  3. Test with: curl -X POST <FUNCTION_URL> -F file=@invoice.pdf"
