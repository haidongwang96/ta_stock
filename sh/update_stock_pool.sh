#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="/home/haidong/code/stock/ta_stock"
PYTHON_BIN="/home/haidong/anaconda3/envs/stock/bin/python"
TMP_POOL_FILE="stock_pool_all.txt"
TARGET_POOL_FILE="pool/stock_pool_all.txt"

cd "$PROJECT_ROOT"

"$PYTHON_BIN" scripts/generate_stock_pool.py
mv "$TMP_POOL_FILE" "$TARGET_POOL_FILE"
"$PYTHON_BIN" split_stock_pool.py

