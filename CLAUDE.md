# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Chinese A-share stock technical analysis and backtesting toolkit. Supports online data (Tushare API) or offline SQLite database via `--db` flag.

## Common Commands

```bash
# Daily batch scoring (all stocks)
python scripts/daily_stock_scoring.py --pool pool/stock_pool_all.txt --db

# Single stock rolling score analysis
python scripts/single_stock_rolling_score.py --stock 000001.SZ --db

# Year stats (high point, drawdown)
python scripts/stock_year_stats.py --pool pool/stock_pool_small.txt --db

# Low volume reversal scanner
python scripts/low_volume_scanner.py --pool pool/stock_pool_small.txt --db

# VSA scanner
python scripts/vsa_scanner.py --pool pool/stock_pool_small.txt --db

# Run backtest
python scripts/run_backtest.py --db

# Update local database
python database/fetch_data_to_db.py
```

Shell wrappers in `sh/` (e.g., `sh/dailyscoring.sh`) call the above scripts with standard args.

## Architecture

### Data Flow
- **Data source**: Tushare API (`token.txt`) or local SQLite (`stock_data.db`, 647MB)
- `database/query_helper.py` provides a unified query interface compatible with both sources
- All scripts accept `--db` to use local database instead of API calls

### Key Modules
- **`scripts/`** — Main analysis scripts (entry points)
- **`backtesting/`** — Backtest engine: `backtester.py`, `strategy_base.py`, `portfolio.py`, `metrics.py`
- **`strategies/`** — Concrete strategy implementations (`vsa_strategy.py`, `low_volume_reversal_strategy.py`)
- **`analysis/`** — VSA signals (`vsa_signals.py`) and market structure analysis
- **`database/`** — DB manager, query helper, score repository, data fetcher
- **`config/`** — Strategy and backtest configs (`backtest_config.py`, `vsa_config.py`, etc.)
- **`pool/`** — Stock pool files (`.txt`, one ticker per line, e.g. `000001.SZ`)

### Scoring System
`daily_stock_scoring.py` and `advanced_technical_analysis.py` compute multi-dimensional scores using 30+ pandas_ta indicators across: trend, momentum, volatility, volume, and pattern dimensions.

### Backtest Config Defaults (`config/backtest_config.py`)
- Initial capital: 100,000 CNY
- Commission: 0.03% (min 5 CNY)
- Stamp duty: 0.1% (sell only)
- Predefined strategies: `simple_hold_3d/5d/10d`, `stop_loss_conservative/aggressive`

### Output Directories
Results are written to corresponding `*_results/` or `*_reports/` directories in project root.

## Stock Pool Files
- `pool/stock_pool_all.txt` — Full universe (~5000 stocks)
- `pool/stock_pool_small.txt` — Small test pool (use for development)
- `pool/hangye/` — Industry-classified pools

Use `pool/stock_pool_small.txt` during development to keep runs fast.
