#!/usr/bin/env bash
# ================================================================
# FinOps Compute Optimizer — Deployment Script (Linux/macOS)
# ================================================================
# Usage:
#   ./scripts/deploy.sh                              # Deploy with defaults
#   ./scripts/deploy.sh --account-ids "111,222"      # Multi-account
#   ./scripts/deploy.sh --destroy                    # Tear down stack
#   ./scripts/deploy.sh --synth-only                 # Synth only
# ================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT_IDS=""
DESTROY=false
SYNTH_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --account-ids) ACCOUNT_IDS="$2"; shift 2 ;;
        --destroy) DESTROY=true; shift ;;
        --synth-only) SYNTH_ONLY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "========================================"
echo " FinOps Compute Optimizer — Deploy"
echo "========================================"

# ── Step 1: Check prerequisites ──────────────────────────────────
echo -e "\n[1/5] Checking prerequisites..."

for cmd in python3 cdk aws; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "ERROR: '$cmd' not found. Please install it first."
        exit 1
    fi
done

if ! aws sts get-caller-identity &> /dev/null; then
    echo "ERROR: AWS credentials not configured. Run 'aws configure'."
    exit 1
fi
echo "  AWS credentials: OK"

# ── Step 2: Set up virtual environment ───────────────────────────
echo -e "\n[2/5] Setting up Python virtual environment..."

VENV_PATH="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
    echo "  Created virtual environment at $VENV_PATH"
fi

source "${VENV_PATH}/bin/activate"
pip install -q -r "${PROJECT_ROOT}/requirements.txt"
echo "  Dependencies installed"

# ── Step 3: CDK Bootstrap (if needed) ───────────────────────────
echo -e "\n[3/5] Bootstrapping CDK (if needed)..."

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")

cdk bootstrap "aws://${ACCOUNT_ID}/${REGION}" 2>&1 || true

# ── Step 4: Synthesize ──────────────────────────────────────────
echo -e "\n[4/5] Synthesizing CloudFormation template..."

CDK_ARGS=()
if [ -n "$ACCOUNT_IDS" ]; then
    CDK_ARGS+=(--context "account_ids=${ACCOUNT_IDS}")
fi

cd "$PROJECT_ROOT"
cdk synth "${CDK_ARGS[@]}"

if [ "$SYNTH_ONLY" = true ]; then
    echo -e "\nSynth complete. Template at cdk.out/"
    exit 0
fi

# ── Step 5: Deploy or Destroy ───────────────────────────────────
if [ "$DESTROY" = true ]; then
    echo -e "\n[5/5] Destroying stack..."
    cdk destroy --force "${CDK_ARGS[@]}"
    echo -e "\nStack destroyed."
else
    echo -e "\n[5/5] Deploying stack..."
    cdk deploy --require-approval broadening "${CDK_ARGS[@]}"
    echo -e "\n========================================"
    echo " Deployment complete!"
    echo "========================================"
    echo -e "\nTo invoke manually:"
    echo "  aws lambda invoke --function-name finops-compute-optimizer-report /dev/stdout"
fi
