# MarketIQ audit

Reviewed on 8 November 2026, starting from commit `12a9725`.

## Scope

The review covered all 26 tracked files: the Streamlit application, analysis notebook, launch fragment, five datasets, eleven research figures, two architecture images, the mid-review report and repository configuration. The original history contains two commits.

MarketIQ is a local pandas analysis workflow with a Streamlit interface. The notebook has an optional Spark-session example; its price calculations use pandas. The architecture images and mid-review report describe a larger Spark/cloud design that is not implemented in this checkout.

## Data findings

| Check | Observed result |
| --- | --- |
| Processed price records | 113,690 rows, 32 columns |
| Stock universe | 42 NSE stocks across nine sectors |
| Price dates | 2015-01-01 to 2025-12-31 |
| Duplicate date/ticker keys | 0 |
| OHLC ordering violations | 0 |
| Processed CSV versus Excel | All rows/columns match within floating-point tolerance |
| Headline snapshot | 210 records, 202 distinct headline texts |
| Headline dates | 2025-10-17 to 2026-04-28 |
| Headline/date/ticker matches to prices | 29 |
| Cached sentiment scores | All 210 match recalculated VADER compound scores |

Previous-close, simple-return and log-return columns each have 42 missing values at the start of stock histories. Volatility has 84 initial missing values. These calculation boundaries are expected.

All five original data files and eleven saved research figures were retained with unchanged SHA-256 hashes. CSV and Excel processed exports are deliberate alternate formats, not accidental duplicate uploads.

## Changes

### Organization and documentation

- Moved the notebook to `notebooks/market_iq.ipynb`.
- Moved the original architecture images and mid-review report into named folders under `docs/`.
- Removed the redundant file named `gitignore`; its patterns were already covered by `.gitignore`.
- Cleared stale notebook outputs and the empty final cell. Standalone figures remain under `graphs/`.
- Replaced the mixed, repeated README with setup instructions, measured dataset counts, workflow notes and current screenshots.
- Added separate notebook/development dependency files, test configuration and a dark Streamlit theme matching the existing chart styling.
- Replaced decorative code separators and unsupported performance claims with short descriptions of the actual operations.

### Working-code fixes

1. **Moving-average label:** the dashboard previously copied the notebook's `MA200` column into `MA_60`. It now computes a separate 60-session average per stock and retains the original 200-session series.
2. **Undefined notebook data:** added a sorted copy of the cleaned frame before the grouped-calculation examples use `df`.
3. **Portable paths:** dashboard data and figure paths now resolve relative to `app.py`, rather than the terminal's current directory.
4. **Cached notebook input:** saved workbooks are now the default. A named flag retains the live-refresh workflow; the optional Spark example also requires an explicit flag.
5. **Matplotlib compatibility:** updated the boxplot keyword from `labels` to `tick_labels` for current Matplotlib. Notebook requirements specify version 3.9 or newer.
6. **Launch script:** the former `03_launch_dashboard.py` contained notebook shell syntax and could not run as Python. Its replacement launches Streamlit and optionally an installed Cloudflare client. It does not kill unrelated processes or disable CORS/XSRF protections.
7. **Missing news:** the sentiment page now handles an unavailable news snapshot without trying to chart missing data. Latest-date sentiment rankings are omitted when no matching headlines exist.
8. **Displayed claims:** replaced fixed “50 tickers,” “10 years” and “125,000+ records” text with measured counts. Removed claims that local grouping or try/except blocks provide distributed execution or fault tolerance.
9. **Data views:** column-count bars now compare real stored/export/dashboard schemas. Return heatmap labels say “mean daily return”; moving-average crossover labels specify their 7/30-session windows.

Data normalization and indicator calculations now live in `marketiq/analysis.py`, where they can be tested without launching the interface. Indicator rules, source data and existing exported values were otherwise preserved.

## Verification

The isolated environment used Python 3.13, pandas 3.1.1, NumPy 2.5.4, Streamlit 1.67.0, Plotly 7.1.0, Matplotlib 3.11.2, openpyxl 3.1.5 and yfinance 1.8.0.

The automated suite passed **13 tests**.

- Calculation tests cover independent stock histories and the 60/200-session regression.
- Streamlit checks exercise all eight pages using the supplied cache, from a different working directory. They also check the missing-news fallback.
- Notebook checks validate its JSON schema and compile every code cell.
- All notebook calculation cells completed with saved workbooks and Yahoo downloads blocked. They produced 113,690 processed rows, 32 columns and eleven figures in a separate output folder.
- Regenerated values match the supplied CSV within the documented numeric tolerances. One `Intraday_Range_Pct` value for WIPRO.NS on 2019-05-30 rounds to 1.563 instead of 1.562 after the raw Excel round trip. The validator allows one final decimal unit for that field and reports the number of differences; it does not alter the stored CSV.
- Headless Chromium captures show the working watchlist and stock-analysis views.
- Credential-pattern checks found no matches in current eligible files or the 28 historical Git blobs. These are heuristic checks, not a guarantee that every possible secret format is detected.

Live Yahoo refresh, FinBERT model download, a Spark runtime and a public Cloudflare tunnel were not exercised.

## Remaining limits

- The selected stocks do not represent the full market, and the data ends in 2025.
- The news snapshot is small and has no article URLs or acquisition log. A missing match is represented as zero, which should not be interpreted as observed neutral news.
- BUY/HOLD/SELL and outlier-event labels are heuristics. There is no strategy backtest, trained price predictor, portfolio optimizer or order execution.
- The existing RSI implementation retains its neutral fallback when average losses are zero. This cleanup does not redefine the signal methodology.
- The notebook's beta table excludes stocks with mean daily returns between -0.1% and +0.1%. Its chart therefore covers a subset, and beta is not exported into the processed CSV.
- Sector growth is based on compounded average log returns, not a tested portfolio with trading costs.
- Historical images and the mid-review report remain intact. Their Spark/cloud and full-universe beta claims should not be quoted as current implementation evidence.
- No project-wide license was present or added.
