# Repository Guidelines

## Project Structure & Module Organization
Core entry points live in `scripts/`; each file is a CLI tool built around `argparse`. Shared logic is split by concern: `analysis/` for signal and market-structure logic, `strategies/` for reusable strategy classes, `backtesting/` for the backtest engine, `database/` for SQLite and Tushare access, and `config/` for strategy/backtest settings. Stock universes live in `pool/` and `pool/hangye/`. Long-form usage notes are in `readme/`. Generated outputs are written to root-level folders such as `analysis_results/`, `daily_scoring_results/`, `low_volume_reports/`, and `backtest_results/`.

## Build, Test, and Development Commands
This repo does not ship a `requirements.txt`; install the libraries referenced by the code and docs, for example:
```bash
pip install pandas numpy pandas_ta tushare matplotlib
```
Common workflows:
```bash
python database/fetch_data_to_db.py --update
python scripts/daily_stock_scoring.py --pool pool/stock_pool_small.txt --db
python scripts/single_stock_rolling_score.py --stock 000001.SZ --db
python scripts/run_backtest.py --signals examples/signals.csv --plot
```
Use the small pool during development to keep runs fast. Shell helpers in `sh/` wrap common commands.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions/files/variables, `PascalCase` for classes, and concise docstrings or comments only where logic is not obvious. Keep new CLI options aligned with the current `argparse` pattern and preserve the `--db` switch when adding data-access features. Prefer focused modules over growing already-large scripts.

## Testing Guidelines
There is no dedicated automated test suite in-tree. Validate changes by running the smallest relevant CLI workflow and checking generated artifacts. Examples: use `pool/stock_pool_small.txt` for scanners and `examples/signals.csv` for backtests. If you change output formats, inspect the corresponding report or chart directory before submitting.

## Commit & Pull Request Guidelines
Recent commits use short, lower-case, imperative summaries such as `update args -- use-local-db`, `stock year changes`, and `add pools`. Keep commits narrow and descriptive. PRs should state the user-visible change, list the commands you ran, note any config or pool files touched, and include screenshots when plots or report layouts change.

## Security & Configuration Tips
Keep `token.txt` local; never commit API tokens, database files, or generated reports. `.gitignore` already excludes `stock_data.db`, most `*.txt`, `*.csv`, and `*.png` outputs while preserving tracked pool lists.
