#!/usr/bin/env bash
# Resume/complete the Base full-history hook census.
# Checkpointed: safe to Ctrl-C / crash / rerun — resumes exactly.
#
#   ./scripts/base-census.sh          # runs to completion (~1-2h)
#
# On success: out/base-onchain.json → then run
#   CHAIN=base python3 src/verify_status.py
set -euo pipefail
cd "$(dirname "$0")/.."
export CHAIN=base
export HG_STEP=2000            # small windows dodge server-side getLogs timeouts
export HG_CHECKPOINT="${HG_CHECKPOINT:-$PWD/out/base_ckpt}"
exec python3 -u src/discover.py
