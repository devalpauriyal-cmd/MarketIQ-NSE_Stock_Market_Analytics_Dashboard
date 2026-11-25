# MarketIQ

MarketIQ is an educational NSE market analytics project covering historical stock prices, technical indicators, sector comparisons and headline sentiment across a selected stock universe.

## Deploy on Vercel

The Vercel deployment uses a FastAPI backend and a lightweight browser dashboard. The original Streamlit dashboard is preserved as `streamlit_app.py`; it is not the Vercel entry point.

1. Import this repository into Vercel.
2. Select the `deploy/vercel-nextjs-migration` branch for the first preview deployment.
3. Keep the project Root Directory at `./`.
4. Use the Python framework/runtime detection. Do not force the Streamlit/Python preset from the previous failed deployment if it still identifies `streamlit_app.py`.
5. Deploy. The root `index.py` exports the FastAPI `app`; the static dashboard is in `public/`.
6. Verify `/api/health`, `/api/docs`, and the dashboard root URL.

No environment variables or API keys are required for the included historical dataset. The app does not fetch live prices. The existing CSV is included with the Python function; large source workbooks, notebooks, figures and tests are excluded from the function bundle by `vercel.json`.

## Local Vercel development

Use Python 3.11+ and install the runtime dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install "vercel[cli]"
vercel dev
```

For the original Streamlit dashboard:

```bash
python -m pip install -r requirements-streamlit.txt
streamlit run streamlit_app.py
```

## Dataset and methodology

The dashboard reads `data/processed_data.csv` and serves a ticker-level history plus latest-observation summaries. Technical signal labels are descriptive rules, not investment recommendations or a validated trading strategy. The sentiment fields reflect the limited cached headline data described in the project audit.

## Project structure

- `index.py` — FastAPI application and data API for Vercel.
- `public/` — static browser dashboard.
- `streamlit_app.py` — original Streamlit dashboard, retained for local use.
- `marketiq/analysis.py` — shared historical indicator calculations.
- `data/processed_data.csv` — canonical processed dataset.
- `notebooks/`, `graphs/`, `tests/` — original analysis and validation materials.
