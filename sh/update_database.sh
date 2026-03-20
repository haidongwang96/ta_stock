#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="/home/haidong/code/stock/ta_stock"
PYTHON_BIN="/home/haidong/anaconda3/envs/stock/bin/python"
POOL_FILE="pool/stock_pool_all.txt"

cd "$PROJECT_ROOT"

"$PYTHON_BIN" database/fetch_data_to_db.py --update --pool "$POOL_FILE"
"$PYTHON_BIN" scripts/stock_analysis.py --pool "$POOL_FILE"
