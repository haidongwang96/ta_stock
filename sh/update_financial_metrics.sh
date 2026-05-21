#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="/home/haidong/code/stock/ta_stock"
PYTHON_BIN="/home/haidong/anaconda3/envs/stock/bin/python"
POOL_FILE="${1:-pool/stock_pool_all.txt}"

cd "$PROJECT_ROOT"

"$PYTHON_BIN" scripts/update_financial_metrics.py --pool "$POOL_FILE" "${@:2}"
