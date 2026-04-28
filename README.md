# MarketIQ — Streamlit Dashboard

## Run locally (Windows)

From this folder:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (typically `http://localhost:8501`).

## Data files used

- `data/processed_data.csv` (required)
- `data/news_raw.xlsx` (optional; if missing, the app will try to fetch Yahoo headlines)
- `data/stocks_raw.xlsx` (optional; used for the pipeline inspector)

## Where to find “planning next moves”

Open the **`🧭  Next Moves`** page in the sidebar. It shows:

- A prioritized watchlist based on the latest `Combined_Signal`, indicator scores, sentiment, and volatility
- Risk alerts (high volatility) and sentiment leaders (bullish/bearish)

# MarketIQ

MarketIQ is a stock-market analysis project built around Yahoo Finance data for 42 NSE stocks and the Nifty 50 index. The notebook and dashboard now include PySpark-aware pipeline stages while remaining easy to run on Windows with a reproducible data export workflow.

## What is included

- [Market_IQ.ipynb](Market_IQ.ipynb) for the full analysis pipeline
- [app.py](app.py) for the Streamlit dashboard
- [03_launch_dashboard.py](03_launch_dashboard.py) for launch instructions in a Colab-style environment
- [data/](data) for the canonical raw and processed exports used by the dashboard
- [graphs/](graphs) for notebook-generated figures

## Main analyses

- Data ingestion and validation from Yahoo Finance
- OHLC checks, null checks, and row coverage analysis
- Daily returns, log returns, cumulative returns, and yearly performance
- Moving averages, volatility, momentum, beta, and correlation analysis
- VADER-based sentiment scoring from Yahoo Finance news headlines
- Sector-level and ticker-level summaries in the dashboard

## Date range

The extracted stock data covers 2015-01-01 through 2025-12-31.

## Run locally

1. Install the dependencies in `requirements.txt`.
2. Start the dashboard with `streamlit run app.py`.
3. Open the local URL shown in the terminal.

## Notes

- Outliers are flagged, not dropped.
- The dashboard uses cached or fetched Yahoo Finance news when a news workbook is not present.
- The duplicate top-level Excel exports were removed; the canonical copies live in `data/`.
