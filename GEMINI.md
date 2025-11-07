# GEMINI.md - Project Context

This document provides an overview of the `ta_stock` project, its structure, and how to use it.

## Project Overview

This project is a comprehensive toolkit for stock technical analysis, written in Python. It provides a suite of scripts to fetch stock data, calculate a wide range of technical indicators, generate trading signals based on a detailed scoring system, and save the results in various formats (CSV, text reports, and charts).

The system can operate in two modes:
1.  **Online Mode:** Fetches data directly from the Tushare API.
2.  **Offline Mode:** Uses a local SQLite database (`stock_data.db`) for faster data retrieval and analysis, reducing reliance on API calls.

### Core Features

- **Multiple Analysis Engines:**
    - `advanced_technical_analysis.py`: The main engine for in-depth analysis of single or multiple stocks, featuring a multi-category scoring system (Trend, Momentum, Volatility, Volume, Pattern).
    - `daily_stock_scoring.py`: A high-performance script for daily batch analysis of a large stock pool, using multiprocessing to generate ranked lists and detailed reports.
    - `single_stock_rolling_score.py`: Analyzes the historical technical score of a single stock over a rolling window, useful for tracking its evolution and visualizing trends.
    - `batch_technical_analysis.py`: A simpler batch analysis tool.
    - `technical_analysis.py`: An older, basic script focusing on MFI, OBV, and candlestick patterns.
- **Local Database:** A self-contained database system (`database/`) allows for initializing and updating a local copy of stock data, significantly speeding up repeated analysis.
- **Extensive Indicator Support:** Leverages the `pandas_ta` library to calculate dozens of indicators across various categories.
- **Flexible Execution:** All scripts are command-line driven with clear arguments, and helper shell scripts (`.sh`) are provided for convenience.

### Key Technologies

- **Language:** Python 3
- **Data Analysis:** `pandas`, `numpy`
- **Technical Indicators:** `pandas_ta`
- **Data Source:** `tushare`
- **Database:** `sqlite3` (via Python's built-in library)
- **Visualization:** `matplotlib`

---

## Building and Running

### 1. Dependencies

The project relies on several Python libraries. A `requirements.txt` file should be created.

**TODO:** Create a `requirements.txt` file.

Based on the source code, the main dependencies are:
```
pandas
pandas_ta
tushare
matplotlib
numpy
```

Install them using pip:
`pip install pandas pandas_ta tushare matplotlib numpy`

### 2. Configuration

Before running, you must provide your Tushare API token.

- Create a file named `token.txt` in the project root directory.
- Paste your Tushare token into this file and save it.

### 3. Database Setup (Optional but Recommended)

Using the local database is highly recommended for performance.

**Step 1: Initialize the Database**
This command fetches historical data for the stocks listed in `pool.txt` and populates the `stock_data.db` file.

```bash
# Fetches the last 365 days of data for stocks in pool.txt
python database/fetch_data_to_db.py --init --pool pool.txt --days 365
```

**Step 2: Update the Database**
Run this command periodically (e.g., daily) to fetch the latest data and keep the database up-to-date.

```bash
# Incrementally updates all stocks already in the database
python database/fetch_data_to_db.py --update
```

### 4. Running Analysis

All analysis results are saved into corresponding directories (`advanced_analysis_results/`, `daily_scoring_results/`, etc.).

**Advanced Analysis (Single Stock)**
This is the most common use case for a detailed look at one stock.

```bash
# Using the wrapper script
./run_advanced_analysis.sh -c 688256.SH

# Or directly with Python, using the local database
python advanced_technical_analysis.py --code 688256.SH --use-local-db
```

**Daily Scoring (Batch Analysis)**
Analyzes all stocks in a pool for daily monitoring.

```bash
# Analyzes all stocks in pool.txt using 4 parallel processes and the local DB
python daily_stock_scoring.py --pool pool.txt --workers 4 --use-local-db
```

**Rolling Score Analysis (Single Stock Deep Dive)**
Generates a historical score trend and charts for one stock.

```bash
# Analyze the last 90 days of scores for a stock using the local DB
python single_stock_rolling_score.py --code 688256.SH --num-windows 90 --use-local-db
```

---

## Development Conventions

- **Modular Design:** The project is broken down into several scripts, each with a specific purpose (e.g., `daily_stock_scoring.py` for batch jobs, `single_stock_rolling_score.py` for individual deep dives).
- **Class-Based Structure:** Core logic is encapsulated in classes (e.g., `AdvancedTechnicalAnalyzer`, `StockScoringAnalyzer`).
- **Command-Line Interface:** All scripts use Python's `argparse` module to provide a clear and consistent command-line interface.
- **Logging:** The `logging` module is used to provide informative output about the script's progress and potential errors.
- **Organized Output:** Each script saves its output (CSV, TXT, PNG) to a dedicated directory (e.g., `advanced_analysis_results/`, `daily_scoring_results/`), keeping the root directory clean.
- **Data Source Abstraction:** The analysis scripts can seamlessly switch between the online Tushare API and the local SQLite database via the `--use-local-db` flag.
