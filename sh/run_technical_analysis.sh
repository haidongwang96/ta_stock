#!/bin/bash
# Batch run technical analysis scripts
# Read stock codes from stock_pool_small.txt and run technical_analysis.py and plot_kline.py

# Set working directory to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Input file
INPUT_FILE="stock_pool_small.txt"

# Check if input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "ERROR: File not found: $INPUT_FILE"
    exit 1
fi

# Statistics
TOTAL=0
SUCCESS=0
FAILED=0

echo "=========================================="
echo "Starting batch technical analysis"
echo "Input file: $INPUT_FILE"
echo "Working directory: $PROJECT_DIR"
echo "=========================================="
echo ""

# Read file line by line
while IFS= read -r line; do
    # Trim whitespace
    line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    # Skip empty lines
    if [ -z "$line" ]; then
        continue
    fi

    # Skip comment lines (lines starting with #)
    if [[ "$line" =~ ^# ]]; then
        continue
    fi

    # Extract first column (stock code), remove content after #
    stock_code=$(echo "$line" | awk '{print $1}' | cut -d'#' -f1)

    # Skip if stock code is empty
    if [ -z "$stock_code" ]; then
        continue
    fi

    TOTAL=$((TOTAL + 1))

    echo "=========================================="
    echo "[$TOTAL] Processing stock: $stock_code"
    echo "=========================================="

    # Run technical_analysis.py
    echo "Step 1: Running technical analysis..."
    if python3 technical_analysis.py --code "$stock_code" --days 120; then
        echo "[OK] Technical analysis completed"

        # Find generated CSV file
        csv_file=$(ls -t technical_analysis_results/technical_analysis_${stock_code}.csv 2>/dev/null | head -n 1)

        if [ -n "$csv_file" ]; then
            echo "Step 2: Plotting K-line chart..."
            # Run plot_kline.py
            if python3 plot_kline.py --input "$csv_file" --code "$stock_code"; then
                echo "[OK] K-line chart completed"
                SUCCESS=$((SUCCESS + 1))
            else
                echo "[FAILED] K-line chart failed"
                FAILED=$((FAILED + 1))
            fi
        else
            echo "[FAILED] Technical analysis output file not found"
            FAILED=$((FAILED + 1))
        fi
    else
        echo "[FAILED] Technical analysis failed"
        FAILED=$((FAILED + 1))
    fi

    echo ""

done < "$INPUT_FILE"

# Output statistics
echo "=========================================="
echo "Batch processing completed"
echo "=========================================="
echo "Total: $TOTAL"
echo "Success: $SUCCESS"
echo "Failed: $FAILED"
echo "=========================================="

# Return non-zero exit code if there are failures
if [ $FAILED -gt 0 ]; then
    exit 1
fi
