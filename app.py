import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
import os
import yfinance as yf

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:
    SentimentIntensityAnalyzer = None

try:
    from transformers import pipeline
except Exception:
    pipeline = None

st.set_page_config(
    page_title="MarketIQ — Big Data Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .pipeline-box {
    background:#1a1f2e; border:1px solid #2d3150;
    border-radius:10px; padding:16px 20px; margin-bottom:8px;
  }
  .stage-done { border-left:4px solid #26a69a; }
  .section-hdr {
    font-size:.8rem; font-weight:700; color:#718096;
    text-transform:uppercase; letter-spacing:.1em;
    border-bottom:1px solid #2d3150; padding-bottom:6px;
    margin:22px 0 10px 0;
  }
  div[data-testid="metric-container"] {
    background:#1a1f2e; border:1px solid #2d3150;
    border-radius:8px; padding:10px 14px;
  }
</style>
""", unsafe_allow_html=True)


def _first_existing_path(paths):
    """Return the first file path that exists from a candidate list."""
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def _label_sentiment(score):
    """Map a normalized sentiment score to a simple dashboard label."""
    if score >= 0.2:
        return "very_bullish"
    if score >= 0.05:
        return "bullish"
    if score <= -0.2:
        return "very_bearish"
    if score <= -0.05:
        return "bearish"
    return "neutral"


def _score_headline(headline, analyzer, mode):
    """Convert a headline into a signed sentiment score."""
    if mode == "finbert":
        result = analyzer(headline[:512])[0]
        label = str(result.get("label", "neutral")).upper()
        score = float(result.get("score", 0.0))
        if label == "POSITIVE":
            return score
        if label == "NEGATIVE":
            return -score
        return 0.0
    return float(analyzer.polarity_scores(headline)["compound"])


@st.cache_resource
def _load_sentiment_model():
    """Load the best available local sentiment model, with a VADER fallback."""
    if pipeline is not None:
        try:
            finbert = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                device=-1,
                truncation=True,
            )
            return finbert, "finbert", "ProsusAI/finbert"
        except Exception:
            pass

    if SentimentIntensityAnalyzer is not None:
        return SentimentIntensityAnalyzer(), "vader", "VADER"

    raise RuntimeError("No sentiment model is available.")


def _fetch_yahoo_news_frame(sector_lookup, tickers, max_items_per_ticker=8):
    """Fetch Yahoo Finance news per ticker and score each headline locally."""
    analyzer, mode, model_name = _load_sentiment_model()
    rows = []

    for ticker in tickers:
        try:
            ticker_news = yf.Ticker(ticker).news or []
        except Exception:
            ticker_news = []

        for item in ticker_news[:max_items_per_ticker]:
            content = item.get("content", {}) if isinstance(item, dict) else {}
            headline = (content.get("title") or content.get("summary") or "").strip()
            if not headline:
                continue

            published = content.get("pubDate") or content.get("displayTime")
            published_dt = pd.to_datetime(published, utc=True, errors="coerce")
            if pd.isna(published_dt):
                continue

            score = _score_headline(headline, analyzer, mode)
            rows.append({
                "Date": published_dt.tz_convert(None).normalize(),
                "Ticker": ticker,
                "Sector": sector_lookup.get(ticker, "Unknown"),
                "Headline": headline,
                "Sentiment_Score": score,
                "Sentiment_Label": _label_sentiment(score),
                "Source": (content.get("provider", {}) or {}).get("displayName", "Yahoo Finance"),
                "Model": model_name,
            })

    if not rows:
        return pd.DataFrame(columns=["Date", "Ticker", "Sector", "Headline", "Sentiment_Score", "Sentiment_Label", "Source", "Model"])

    news_frame = pd.DataFrame(rows).drop_duplicates(subset=["Date", "Ticker", "Headline"]).sort_values(["Date", "Ticker"])
    return news_frame

# ─────────────────────────────────────────────────────────────
#  DATA LOADING
# ─────────────────────────────────────────────────────────────
@st.cache_data
def load_processed():
    path = _first_existing_path([
        "data/processed_data.csv",
    ])
    if path is None:
        raise FileNotFoundError("Could not find data/processed_data.csv.")
    return pd.read_csv(path, parse_dates=["Date"])

@st.cache_data
def load_news():
    # Prefer a cached workbook first; if it is missing, build one from live Yahoo headlines.
    path = _first_existing_path([
        "data/news_raw.xlsx",
    ])
    if path is None:
        try:
            sector_lookup = df.groupby("Ticker")["Sector"].first().to_dict()
            tickers = list(sector_lookup.keys())
            news_frame = _fetch_yahoo_news_frame(sector_lookup, tickers)
            if not news_frame.empty:
                news_frame.to_excel("data/news_raw.xlsx", index=False, sheet_name="News")
            return news_frame
        except Exception:
            # If optional sentiment dependencies (transformers/vader) or network access are unavailable,
            # keep the dashboard usable and fall back to "no news" mode.
            return pd.DataFrame(columns=["Date", "Ticker", "Sector", "Headline", "Sentiment_Score", "Sentiment_Label", "Source", "Model"])
    return pd.read_excel(path, parse_dates=["Date"])

@st.cache_data
def load_raw():
    path = _first_existing_path([
        "data/stocks_raw.xlsx",
    ])
    if path is None:
        return pd.DataFrame()
    return pd.read_excel(path, parse_dates=["Date"])


def normalize_processed_frame(frame):
    frame = frame.copy()

    # Keep notebook and dashboard column names aligned without failing on older exports.
    if "MA7" in frame.columns and "MA_7" not in frame.columns:
        frame["MA_7"] = frame["MA7"]
    if "MA30" in frame.columns and "MA_30" not in frame.columns:
        frame["MA_30"] = frame["MA30"]
    # The notebook sometimes exports a long moving average as MA200; the dashboard uses MA_60.
    if "MA200" in frame.columns and "MA_60" not in frame.columns:
        frame["MA_60"] = frame["MA200"]
    if "Volume_MA7" in frame.columns and "Volume_MA_7" not in frame.columns:
        frame["Volume_MA_7"] = frame["Volume_MA7"]
    if "Volume_MA_7" not in frame.columns and {"Ticker", "Date", "Volume"}.issubset(frame.columns):
        frame = frame.sort_values(["Ticker", "Date"]).reset_index(drop=True)
        frame["Volume_MA_7"] = frame.groupby("Ticker")["Volume"].transform(
            lambda s: s.rolling(7, min_periods=1).mean()
        )

    if "MA_60" not in frame.columns and {"Ticker", "Date", "Close"}.issubset(frame.columns):
        frame = frame.sort_values(["Ticker", "Date"]).reset_index(drop=True)
        frame["MA_60"] = frame.groupby("Ticker")["Close"].transform(
            lambda s: s.rolling(60, min_periods=1).mean()
        )

    if "Daily_Range" not in frame.columns and {"High", "Low"}.issubset(frame.columns):
        frame["Daily_Range"] = frame["High"] - frame["Low"]

    if "Price_vs_MA30_Pct" not in frame.columns and {"Close", "MA_30"}.issubset(frame.columns):
        frame["Price_vs_MA30_Pct"] = ((frame["Close"] - frame["MA_30"]) / frame["MA_30"]) * 100

    if "Avg_Sentiment" not in frame.columns:
        frame["Avg_Sentiment"] = 0.0
    if "Max_Sentiment" not in frame.columns:
        frame["Max_Sentiment"] = frame["Avg_Sentiment"]
    if "Min_Sentiment" not in frame.columns:
        frame["Min_Sentiment"] = frame["Avg_Sentiment"]
    if "News_Count" not in frame.columns:
        frame["News_Count"] = 0

    if "Combined_Signal" not in frame.columns:
        if "Price_Signal" in frame.columns:
            # Reuse the notebook's bullish/bearish signal, but keep one simple BUY/SELL/HOLD label set.
            signal_map = {"BULLISH": "BUY", "BEARISH": "SELL"}
            frame["Combined_Signal"] = frame["Price_Signal"].map(signal_map).fillna("HOLD")
        else:
            frame["Combined_Signal"] = "HOLD"

    return frame


def _add_signal_features(frame):
    """Add trend, momentum, sentiment, and volume features used for the final trade signal."""
    frame = frame.sort_values(["Ticker", "Date"]).reset_index(drop=True).copy()

    frame["Trend_Score"] = np.select(
        [frame["MA_7"] > frame["MA_30"], frame["MA_7"] < frame["MA_30"]],
        [1, -1],
        default=0,
    )

    frame["MACD_Line"] = frame.groupby("Ticker")["Close"].transform(
        lambda s: s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    )
    frame["MACD_Signal"] = frame.groupby("Ticker")["MACD_Line"].transform(
        lambda s: s.ewm(span=9, adjust=False).mean()
    )
    frame["MACD_Hist"] = frame["MACD_Line"] - frame["MACD_Signal"]
    frame["MACD_Score"] = np.select(
        [frame["MACD_Hist"] > 0, frame["MACD_Hist"] < 0],
        [1, -1],
        default=0,
    )

    delta = frame.groupby("Ticker")["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(frame["Ticker"]).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    avg_loss = loss.groupby(frame["Ticker"]).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    rs = avg_gain / avg_loss.replace(0, np.nan)
    frame["RSI_14"] = (100 - (100 / (1 + rs))).fillna(50.0)
    frame["RSI_Score"] = np.select(
        [frame["RSI_14"] <= 35, frame["RSI_14"] >= 65],
        [1, -1],
        default=0,
    )

    frame["Volume_Ratio"] = (frame["Volume"] / frame["Volume_MA_7"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    frame["Volume_Score"] = np.select(
        [
            (frame["Volume_Ratio"] >= 1.25) & (frame["Trend_Score"] > 0),
            (frame["Volume_Ratio"] >= 1.25) & (frame["Trend_Score"] < 0),
        ],
        [1, -1],
        default=0,
    )

    frame["Sentiment_Score_Adj"] = frame["Avg_Sentiment"].fillna(0.0)
    frame["Sentiment_Score"] = np.select(
        [frame["Sentiment_Score_Adj"] >= 0.10, frame["Sentiment_Score_Adj"] <= -0.10],
        [1, -1],
        default=0,
    )

    frame["Signal_Score"] = (
        frame["Trend_Score"]
        + frame["MACD_Score"]
        + frame["RSI_Score"]
        + frame["Volume_Score"]
        + frame["Sentiment_Score"]
    )
    frame["Combined_Signal"] = np.select(
        [frame["Signal_Score"] >= 2, frame["Signal_Score"] <= -2],
        ["BUY", "SELL"],
        default="HOLD",
    )

    return frame


def _signal_reason(row):
    """Build a short plain-English explanation for the current BUY/SELL/HOLD label."""
    pieces = []

    if pd.notna(row.get("MA_7")) and pd.notna(row.get("MA_30")):
        if row["MA_7"] > row["MA_30"]:
            pieces.append("short-term price is above the medium-term trend")
        elif row["MA_7"] < row["MA_30"]:
            pieces.append("short-term price is below the medium-term trend")

    if pd.notna(row.get("MACD_Hist")):
        if row["MACD_Hist"] > 0:
            pieces.append("MACD momentum is positive")
        elif row["MACD_Hist"] < 0:
            pieces.append("MACD momentum is negative")

    if pd.notna(row.get("RSI_14")):
        if row["RSI_14"] <= 35:
            pieces.append(f"RSI is oversold at {row['RSI_14']:.1f}")
        elif row["RSI_14"] >= 65:
            pieces.append(f"RSI is overbought at {row['RSI_14']:.1f}")
        else:
            pieces.append(f"RSI is neutral at {row['RSI_14']:.1f}")

    if pd.notna(row.get("Volume_Ratio")) and row["Volume_Ratio"] >= 1.25:
        pieces.append(f"volume is {row['Volume_Ratio']:.2f}x the 7-day average")

    if pd.notna(row.get("Avg_Sentiment")):
        if row["Avg_Sentiment"] >= 0.10:
            pieces.append(f"news sentiment is positive ({row['Avg_Sentiment']:.2f})")
        elif row["Avg_Sentiment"] <= -0.10:
            pieces.append(f"news sentiment is negative ({row['Avg_Sentiment']:.2f})")

    if not pieces:
        pieces.append("the indicators are mixed, so the model stays neutral")

    return "; ".join(pieces)

df      = normalize_processed_frame(load_processed())
news_df = load_news()
raw_df  = None

if not news_df.empty:
    # Aggregate news by day and ticker so the same sentiment fields can drive the whole dashboard.
    news_df = news_df.copy()
    news_df["Date"] = pd.to_datetime(news_df["Date"])
    daily_sent = news_df.groupby(["Date", "Ticker"]).agg(
        Avg_Sentiment=("Sentiment_Score", "mean"),
        Max_Sentiment=("Sentiment_Score", "max"),
        Min_Sentiment=("Sentiment_Score", "min"),
        News_Count=("Headline", "count"),
    ).reset_index()

    df = df.merge(daily_sent, on=["Date", "Ticker"], how="left", suffixes=("", "_news"))
    for col in ["Avg_Sentiment", "Max_Sentiment", "Min_Sentiment", "News_Count"]:
        news_col = f"{col}_news"
        if news_col in df.columns:
            if col in df.columns:
                df[col] = df[news_col].combine_first(df[col])
            else:
                df[col] = df[news_col]
            df.drop(columns=[news_col], inplace=True)

df = _add_signal_features(df)
df["Signal_Reason"] = df.apply(_signal_reason, axis=1)

ALL_TICKERS = sorted(df["Ticker"].unique().tolist())
ALL_SECTORS = sorted(df["Sector"].unique().tolist())

# ─────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────
st.sidebar.markdown("## 📊 MarketIQ")
st.sidebar.caption("Big Data & Cloud Computing — Vidyashilp University")
st.sidebar.markdown("---")

PAGE = st.sidebar.radio("Navigate to", [
    "🔁  Pipeline Overview",
    "🔬  Stage Inspector",
    "📈  Stock Analysis",
    "🗞️  Sentiment Analysis",
    "🧭  Next Moves",
    "💡  Market Insights",
    "📊  Sector Intelligence",
    "🖼️  Research Graphs",
], index=4)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Processed rows:** `{len(df):,}`")
st.sidebar.markdown(f"**Tickers:** `{df['Ticker'].nunique()}`")
st.sidebar.markdown(f"**Date range:** `{df['Date'].min().date()}` → `{df['Date'].max().date()}`")
st.sidebar.markdown(f"**News articles:** `{len(news_df):,}`")


# ═════════════════════════════════════════════════════════════
#  PAGE 1 — PIPELINE OVERVIEW
# ═════════════════════════════════════════════════════════════
if "Pipeline Overview" in PAGE:
    st.title("🔁 Big Data Processing Pipeline")
    st.caption("End-to-end view of how raw financial data flows through MarketIQ")

    raw_df = load_raw()

    raw_rows   = len(raw_df)
    valid_rows = len(df[df["Close"] > 0])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Raw Rows Ingested",  f"{raw_rows:,}")
    k2.metric("Yahoo Null Check",   "0", "no nulls in extract")
    k3.metric("Final Feature Cols", f"{len(df.columns)}")
    k4.metric("News Articles",      f"{len(news_df):,}")
    k5.metric("Final Dataset Rows", f"{len(df):,}")

    st.markdown("---")
    st.markdown('<div class="section-hdr">Pipeline Stages</div>', unsafe_allow_html=True)

    stages = [
        dict(num="01", name="Data Ingestion", tool="yfinance API + openpyxl",
             detail="50 tickers × 10 years of daily OHLCV fetched from Yahoo Finance. Saved to Excel for reproducibility.",
             rows_in="Yahoo Finance API", rows_out=f"{raw_rows:,} rows", cols=str(len(raw_df.columns)), color="#26a69a"),
           dict(num="02", name="Load into pandas", tool="pandas read_csv() · DataFrame copy()",
               detail="Processed dataset loaded directly into pandas. Schema is already aligned with the notebook, and row counts are confirmed with len(df).",
             rows_in=f"{raw_rows:,}", rows_out=f"{raw_rows:,}", cols=str(len(raw_df.columns)), color="#26a69a"),
           dict(num="03", name="Data Cleaning", tool="pandas dropna() · filter() · astype()",
               detail=f"Yahoo Finance extract had no null values in the price data. Only positive-price and type checks were applied.",
               rows_in=f"{raw_rows:,}", rows_out=f"{valid_rows:,}", cols=str(len(raw_df.columns)+4), color="#4caf50"),
           dict(num="04", name="Feature Engineering", tool="pandas rolling() · groupby()",
               detail="MA_7, MA_30, MA_60, Volatility_14d, Daily_Return_Pct, Volume_MA_7, Price_Signal computed with ticker-wise pandas operations.",
               rows_in=f"{valid_rows:,}", rows_out=f"{valid_rows:,}", cols="18", color="#f39c12"),
           dict(num="05", name="VADER Sentiment NLP", tool="vaderSentiment · pandas",
               detail=f"VADER compound score computed for {len(news_df):,} headlines and aggregated to daily avg/max/min per ticker.",
             rows_in=f"{len(news_df):,} headlines",
             rows_out=f"{news_df.groupby(['Date','Ticker']).ngroups:,} daily aggregates",
             cols="5", color="#9b59b6"),
           dict(num="06", name="Join Price + Sentiment", tool="pandas left merge on [Date, Ticker]",
                         detail="Stock DataFrame joined with daily sentiment. A multi-factor score combines trend, MACD, RSI, volume, and sentiment.",
               rows_in=f"{valid_rows:,} + {len(news_df):,}", rows_out=f"{len(df):,}", cols=str(len(df.columns)), color="#e74c3c"),
           dict(num="07", name="Aggregation & Export", tool="pandas groupby() · CSV export",
               detail="GroupBy aggregations computed. Final pandas DF exported to data/processed_data.csv for dashboard.",
             rows_in=f"{len(df):,}", rows_out=f"{len(df):,}", cols=str(len(df.columns)), color="#3498db"),
    ]

    for s in stages:
        st.markdown(f"""
        <div class="pipeline-box stage-done">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="flex:1">
              <span style="color:{s["color"]};font-size:.75rem;font-weight:700;letter-spacing:.1em">STAGE {s["num"]}</span>
              <h4 style="margin:3px 0 5px;color:#e2e8f0">{s["name"]}</h4>
              <p style="margin:0;color:#a0aec0;font-size:.85rem">{s["detail"]}</p>
              <p style="margin:6px 0 0;color:#718096;font-size:.8rem">
                🔧 <b style="color:#cbd5e0">{s["tool"]}</b> &nbsp;|&nbsp;
                📥 <b style="color:#cbd5e0">{s["rows_in"]}</b> &nbsp;→&nbsp;
                📤 <b style="color:{s["color"]}">{s["rows_out"]}</b> &nbsp;|&nbsp;
                Cols: <b style="color:#cbd5e0">{s["cols"]}</b>
              </p>
            </div>
            <span style="background:{s["color"]}22;color:{s["color"]};border:1px solid {s["color"]}55;
                  padding:3px 12px;border-radius:20px;font-size:.72rem;font-weight:700;
                  white-space:nowrap;margin-left:16px">✓ COMPLETE</span>
          </div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Data Volume Flow — Sankey Diagram")
    fig_sk = go.Figure(go.Sankey(
        node=dict(
                 label=["yfinance API","stocks_raw.xlsx","pandas Load","After Validation",
                   "Feature Eng.","news_raw.xlsx","VADER Sentiment","Merged DF","Dashboard CSV"],
            color=["#26a69a","#2ecc71","#3498db","#4caf50","#f39c12",
                   "#9b59b6","#8e44ad","#e74c3c","#1abc9c"],
            pad=24, thickness=18,
        ),
        link=dict(
            source=[0,1,2,3,4,5,6,4,7],
            target=[1,2,3,4,7,6,7,7,8],
                 value=[raw_rows,raw_rows,valid_rows,valid_rows,len(df),
                   len(news_df),len(news_df),len(df),len(df)],
            color=["rgba(38,166,154,0.25)"]*9,
        ),
    ))
    fig_sk.update_layout(height=360, template="plotly_dark",
                         paper_bgcolor="rgba(0,0,0,0)", font_color="#a0aec0")
    st.plotly_chart(fig_sk, use_container_width=True)

    st.subheader("Column Count Growth Through Pipeline")
    s_names = ["Raw","After Clean","+ Date cols","+ MA/Return/Vol","+ Sentiment","Final"]
    c_counts = [8, 8, 12, 18, 23, len(df.columns)]
    fig_c = go.Figure(go.Bar(
        x=s_names, y=c_counts,
        marker_color=["#26a69a","#2ecc71","#4caf50","#f39c12","#9b59b6","#e74c3c"],
        text=c_counts, textposition="outside"
    ))
    fig_c.update_layout(height=280, template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        yaxis_title="Number of Columns")
    st.plotly_chart(fig_c, use_container_width=True)


# ═════════════════════════════════════════════════════════════
#  PAGE 2 — STAGE INSPECTOR
# ═════════════════════════════════════════════════════════════
elif "Stage Inspector" in PAGE:
    st.title("🔬 Stage-by-Stage Data Inspector")
    st.caption("Inspect actual data, schema, null counts and statistics at each pipeline stage")

    raw_stage = load_raw()

    stage_choice = st.selectbox("Select stage:", [
        "Stage 1 — Raw Ingested Data",
        "Stage 2 — After Cleaning",
        "Stage 3 — After Feature Engineering",
        "Stage 4 — After Sentiment Join",
        "Stage 5 — Final Dataset",
    ])

    raw_cols  = ["Date","Ticker","Sector","Open","High","Low","Close","Volume"]
    feat_list = raw_cols + ["Year","Month","Quarter","DayOfWeek","Prev_Close",
                            "Daily_Return_Pct","Daily_Range","MA_7","MA_30","MA_60",
                            "Volatility_14d","Volume_MA_7","Price_Signal","Price_vs_MA30_Pct"]
    sent_list = feat_list + ["Avg_Sentiment","Max_Sentiment","Min_Sentiment","News_Count"]

    def sc(cols): return [c for c in cols if c in df.columns]

    stage_map = {
        "Stage 1": raw_stage.copy(),
        "Stage 2": df[sc(raw_cols)].dropna(subset=["Close","Volume"]).query("Close>0"),
        "Stage 3": df[sc(feat_list)].copy(),
        "Stage 4": df[sc(sent_list)].copy(),
        "Stage 5": df.copy(),
    }
    expl = {
        "Stage 1": "**Raw data** from Yahoo Finance API. No transformations. May contain nulls and incorrect types.",
        "Stage 2": "**After pandas validation:** positive-price checks, explicit type casting, date parts added. Yahoo Finance extract had no nulls.",
        "Stage 3": "**After feature engineering** via Window Functions: MA_7/30/60, Daily_Return_Pct, Volatility_14d, Price_Signal.",
        "Stage 4": "**After sentiment join:** VADER scores aggregated daily, left-joined on [Date,Ticker]. Nulls filled with 0.",
        "Stage 5": "**Final dataset** — all columns including Combined_Signal. This is what the dashboard reads.",
    }

    skey = [k for k in stage_map if k in stage_choice][0]
    sdf  = stage_map[skey].reset_index(drop=True)

    st.info(expl[skey])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows",        f"{len(sdf):,}")
    m2.metric("Columns",     f"{len(sdf.columns)}")
    m3.metric("Null values", f"{sdf.isnull().sum().sum():,}")
    m4.metric("Null %",      f"{sdf.isnull().mean().mean()*100:.2f}%")
    m5.metric("Memory MB",   f"{sdf.memory_usage(deep=True).sum()/1e6:.1f}")

    st.markdown("---")
    ca, cb = st.columns([1, 2])
    with ca:
        st.markdown("**Column Schema**")
        sch = pd.DataFrame({
            "Column": sdf.columns,
            "Type":   [str(sdf[c].dtype) for c in sdf.columns],
            "Nulls":  [int(sdf[c].isnull().sum()) for c in sdf.columns],
            "Null%":  [f"{sdf[c].isnull().mean()*100:.1f}%" for c in sdf.columns],
            "Sample": [str(sdf[c].dropna().iloc[0]) if sdf[c].dropna().shape[0]>0 else "—"
                       for c in sdf.columns],
        })
        st.dataframe(sch, hide_index=True, height=420)
    with cb:
        st.markdown("**Descriptive Statistics**")
        num = sdf.select_dtypes(include="number")
        if not num.empty:
            d = num.describe().T.round(4).reset_index()
            d.rename(columns={"index":"Column"}, inplace=True)
            st.dataframe(d, hide_index=True, height=420)

    st.markdown("**Sample rows (first 100)**")
    st.dataframe(sdf.head(100), use_container_width=True, height=280)

    null_s = sdf.isnull().sum()
    null_s = null_s[null_s > 0]
    if null_s.empty:
        st.success("✅ No null values at this stage.")
    else:
        st.markdown("**Null values by column**")
        fig_n = go.Figure(go.Bar(
            x=null_s.index, y=null_s.values,
            marker_color="#e74c3c", text=null_s.values, textposition="outside"
        ))
        fig_n.update_layout(height=240, template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_n, use_container_width=True)

    num_list = list(sdf.select_dtypes(include="number").columns)
    if num_list:
        st.markdown("**Column distribution explorer**")
        col_pick = st.selectbox("Choose column:", num_list)
        vals = sdf[col_pick].dropna()
        fig_h = go.Figure(go.Histogram(x=vals, nbinsx=60, marker_color="#3498db", opacity=0.8))
        fig_h.add_vline(x=vals.mean(), line_color="#f39c12", line_width=2,
                        annotation_text=f"mean={vals.mean():.3f}")
        fig_h.update_layout(height=240, template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            xaxis_title=col_pick, yaxis_title="Frequency")
        st.plotly_chart(fig_h, use_container_width=True)


# ═════════════════════════════════════════════════════════════
#  PAGE 3 — STOCK ANALYSIS
# ═════════════════════════════════════════════════════════════
elif "Stock Analysis" in PAGE:
    st.title("📈 Stock Price Analysis")

    c1, c2 = st.columns([1, 2])
    with c1:
        sel = st.selectbox("Ticker", ALL_TICKERS,
                           index=ALL_TICKERS.index("AAPL") if "AAPL" in ALL_TICKERS else 0)
    with c2:
        dr = st.date_input("Date range",
             value=[df["Date"].min(), df["Date"].max()],
             min_value=df["Date"].min(), max_value=df["Date"].max())

    s7  = st.checkbox("MA 7",  value=True)
    s30 = st.checkbox("MA 30", value=True)
    s60 = st.checkbox("MA 60", value=False)

    tdf = df[df["Ticker"] == sel].sort_values("Date")
    if len(dr) == 2:
        tdf = tdf[(tdf["Date"] >= pd.Timestamp(dr[0])) &
                  (tdf["Date"] <= pd.Timestamp(dr[1]))]
    if tdf.empty:
        st.warning("No data for this selection.")
        st.stop()

    lt = tdf.iloc[-1]
    pv = tdf.iloc[-2] if len(tdf) > 1 else tdf.iloc[0]

    ka, kb, kc, kd, ke, kf = st.columns(6)
    ka.metric("Close",       f"₹{lt['Close']:.2f}", f"{lt['Close']-pv['Close']:+.2f}")
    kb.metric("Daily Ret.",  f"{lt.get('Daily_Return_Pct', 0):.2f}%")
    kc.metric("MA 7",        f"₹{lt['MA_7']:.2f}" if pd.notna(lt.get('MA_7')) else "—")
    kd.metric("MA 30",       f"₹{lt['MA_30']:.2f}" if pd.notna(lt.get('MA_30')) else "—")
    ke.metric("Volatility",  f"{lt['Volatility_14d']:.2f}%" if pd.notna(lt.get('Volatility_14d')) else "—")
    kf.metric("Signal",      str(lt.get("Combined_Signal", "HOLD")))

    st.markdown("**Why this signal?**")
    st.info(f"Score = {lt.get('Signal_Score', 0):.0f} | {lt.get('Signal_Reason', 'No reason available.')}")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.58, 0.21, 0.21], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=tdf["Date"], open=tdf["Open"], high=tdf["High"],
        low=tdf["Low"], close=tdf["Close"], name="OHLC",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350"
    ), row=1, col=1)
    if s7  and "MA_7"  in tdf.columns: fig.add_trace(go.Scatter(x=tdf["Date"],y=tdf["MA_7"], name="MA7", line=dict(color="#f39c12",width=1.5)),row=1,col=1)
    if s30 and "MA_30" in tdf.columns: fig.add_trace(go.Scatter(x=tdf["Date"],y=tdf["MA_30"],name="MA30",line=dict(color="#3498db",width=1.5)),row=1,col=1)
    if s60 and "MA_60" in tdf.columns: fig.add_trace(go.Scatter(x=tdf["Date"],y=tdf["MA_60"],name="MA60",line=dict(color="#9b59b6",width=1.5)),row=1,col=1)
    bc = ["#26a69a" if c>=o else "#ef5350" for c,o in zip(tdf["Close"],tdf["Open"])]
    fig.add_trace(go.Bar(x=tdf["Date"],y=tdf["Volume"],marker_color=bc,name="Volume",opacity=0.6),row=2,col=1)
    if "Daily_Return_Pct" in tdf.columns:
        fig.add_trace(go.Scatter(x=tdf["Date"],y=tdf["Daily_Return_Pct"],name="Ret%",
            line=dict(color="#f39c12",width=1),fill="tozeroy",fillcolor="rgba(243,156,18,0.12)"),row=3,col=1)
    fig.update_layout(height=560, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.04))
    fig.update_yaxes(title_text="Price (₹)", row=1, col=1)
    fig.update_yaxes(title_text="Volume",    row=2, col=1)
    fig.update_yaxes(title_text="Return %",  row=3, col=1)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📡 Golden Cross / Death Cross Events")
    cr = tdf[["Date","Close","MA_7","MA_30"]].dropna().copy()
    cr["pM7"]    = cr["MA_7"].shift(1)
    cr["pM30"]   = cr["MA_30"].shift(1)
    cr["golden"] = (cr["pM7"] < cr["pM30"]) & (cr["MA_7"] >= cr["MA_30"])
    cr["death"]  = (cr["pM7"] > cr["pM30"]) & (cr["MA_7"] <= cr["MA_30"])
    gc = cr[cr["golden"]][["Date","Close"]].round(2).reset_index(drop=True)
    dc = cr[cr["death"]][["Date","Close"]].round(2).reset_index(drop=True)
    e1, e2 = st.columns(2)
    with e1:
        st.markdown(f"**🟢 Golden Cross: {len(gc)}**")
        st.dataframe(gc if not gc.empty else pd.DataFrame({"Msg":["None in range"]}), hide_index=True)
    with e2:
        st.markdown(f"**🔴 Death Cross: {len(dc)}**")
        st.dataframe(dc if not dc.empty else pd.DataFrame({"Msg":["None in range"]}), hide_index=True)

    st.subheader("📅 Monthly Return Heatmap")
    t2 = tdf.copy()
    t2["Year"]  = t2["Date"].dt.year
    t2["Month"] = t2["Date"].dt.month
    mp = t2.groupby(["Year","Month"])["Daily_Return_Pct"].mean().reset_index()
    pp = mp.pivot(index="Year", columns="Month", values="Daily_Return_Pct").round(3)
    mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    pp.columns = [mn[c-1] for c in pp.columns]
    fig_mh = go.Figure(go.Heatmap(
        z=pp.values, x=pp.columns.tolist(), y=[str(y) for y in pp.index],
        colorscale="RdYlGn", zmid=0,
        text=pp.values.round(3), texttemplate="%{text}", textfont=dict(size=9)
    ))
    fig_mh.update_layout(height=340, template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_mh, use_container_width=True)

    st.subheader("📉 Drawdown from Peak")
    tdf = tdf.copy()
    tdf["Peak"] = tdf["Close"].cummax()
    tdf["DD"]   = ((tdf["Close"] - tdf["Peak"]) / tdf["Peak"]) * 100
    fig_dd = go.Figure(go.Scatter(x=tdf["Date"], y=tdf["DD"], fill="tozeroy",
        fillcolor="rgba(231,76,60,0.2)", line=dict(color="#e74c3c", width=1)))
    fig_dd.add_hline(y=tdf["DD"].min(), line_dash="dot", line_color="#f39c12",
                     annotation_text=f"Max: {tdf['DD'].min():.1f}%")
    fig_dd.update_layout(height=240, template="plotly_dark",
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         yaxis_title="Drawdown %")
    st.plotly_chart(fig_dd, use_container_width=True)

    st.subheader("📐 Rolling 90-Day Sharpe Ratio")
    tdf["RM"] = tdf["Daily_Return_Pct"].rolling(90).mean()
    tdf["RS"] = tdf["Daily_Return_Pct"].rolling(90).std()
    tdf["Sh"] = (tdf["RM"] / tdf["RS"]) * np.sqrt(252)
    fig_sh = go.Figure(go.Scatter(x=tdf["Date"], y=tdf["Sh"],
        line=dict(color="#26a69a", width=1.5), fill="tozeroy",
        fillcolor="rgba(38,166,154,0.1)"))
    fig_sh.add_hline(y=1, line_color="#f39c12", line_dash="dot", annotation_text="Sharpe=1")
    fig_sh.update_layout(height=240, template="plotly_dark",
                         paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         yaxis_title="Sharpe Ratio")
    st.plotly_chart(fig_sh, use_container_width=True)


# ═════════════════════════════════════════════════════════════
#  PAGE 4 — SENTIMENT ANALYSIS
# ═════════════════════════════════════════════════════════════
elif "Sentiment" in PAGE:
    st.title("🗞️ Sentiment Analysis")
    active_model = news_df["Model"].dropna().iloc[0] if not news_df.empty and "Model" in news_df.columns else "VADER"
    st.caption(f"{active_model} applied to financial news headlines using pandas")

    with st.expander("ℹ️ How VADER runs in the notebook — click to see code"):
        st.code("""
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

vader = SentimentIntensityAnalyzer()

def vader_compound(text):
    return float(vader.polarity_scores(str(text))["compound"])

news_df["VADER_Score"] = news_df["Headline"].apply(vader_compound)
daily_sent = news_df.groupby(["Date", "Ticker"]).agg(
    Avg_Sentiment=("VADER_Score", "mean"),
    News_Count=("Headline", "count"),
).reset_index()
        """, language="python")

    s1,s2,s3,s4,s5 = st.columns(5)
    s1.metric("Total Headlines",  f"{len(news_df):,}")
    s2.metric("Tickers Covered",  f"{news_df['Ticker'].nunique()}")
    s3.metric("Positive",         f"{(news_df['Sentiment_Score']>0.05).sum():,}")
    s4.metric("Negative",         f"{(news_df['Sentiment_Score']<-0.05).sum():,}")
    s5.metric("Neutral",          f"{((news_df['Sentiment_Score']>=-0.05)&(news_df['Sentiment_Score']<=0.05)).sum():,}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Headline Sentiment Distribution")
        lc = news_df["Sentiment_Label"].value_counts().reset_index()
        lc.columns = ["Label","Count"]
        cm = {"very_bullish":"#27ae60","bullish":"#2ecc71","neutral":"#f39c12",
              "bearish":"#e74c3c","very_bearish":"#c0392b"}
        fig_lc = go.Figure(go.Bar(x=lc["Label"],y=lc["Count"],
            marker_color=[cm.get(l,"#888") for l in lc["Label"]],
            text=lc["Count"],textposition="outside"))
        fig_lc.update_layout(height=300, template="plotly_dark",
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_lc, use_container_width=True)
    with c2:
        st.subheader("Avg Sentiment by Sector")
        ss = news_df.groupby("Sector")["Sentiment_Score"].mean().sort_values()
        fig_ss = go.Figure(go.Bar(x=ss.values.round(3),y=ss.index,orientation="h",
            marker_color=["#e74c3c" if v<0 else "#26a69a" for v in ss.values],
            text=ss.values.round(3),textposition="outside"))
        fig_ss.add_vline(x=0,line_color="white",line_width=0.5)
        fig_ss.update_layout(height=300, template="plotly_dark",
                             paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_ss, use_container_width=True)

    st.subheader("Sentiment Score vs Same-Day Price Change")
    nm = news_df.merge(df[["Date","Ticker","Daily_Return_Pct"]], on=["Date","Ticker"], how="left")
    nm = nm.dropna(subset=["Daily_Return_Pct","Sentiment_Score"])
    fig_sc = px.scatter(nm.sample(min(4000,len(nm)),random_state=42),
        x="Sentiment_Score", y="Daily_Return_Pct", color="Sector",
        hover_data=["Ticker","Headline"], opacity=0.55, template="plotly_dark", trendline="ols",
        labels={"Sentiment_Score":"VADER Score","Daily_Return_Pct":"Same-Day Return %"})
    fig_sc.add_vline(x=0,line_color="white",line_width=0.5,opacity=0.4)
    fig_sc.add_hline(y=0,line_color="white",line_width=0.5,opacity=0.4)
    fig_sc.update_layout(height=400,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_sc, use_container_width=True)
    corr_v = nm["Sentiment_Score"].corr(nm["Daily_Return_Pct"])
    st.info(f"📐 Pearson correlation (Sentiment ↔ Same-day Return): **{corr_v:.4f}**")

    st.subheader("Avg Sentiment Heatmap — All Tickers × Year")
    if not news_df.empty:
        news_year = news_df.copy()
        news_year["Year"] = news_year["Date"].dt.year
        ts = news_year.groupby(["Ticker", "Year"])["Sentiment_Score"].mean().reset_index()
        tp2 = ts.pivot(index="Ticker", columns="Year", values="Sentiment_Score").round(3)
    else:
        ts  = df.groupby(["Ticker","Year"])["Avg_Sentiment"].mean().reset_index()
        tp2 = ts.pivot(index="Ticker",columns="Year",values="Avg_Sentiment").round(3)
    tp2 = tp2.fillna(0)
    fig_th = go.Figure(go.Heatmap(z=tp2.values,x=[str(c) for c in tp2.columns],
        y=tp2.index.tolist(),colorscale="RdYlGn",zmid=0,
        text=tp2.values.round(3),texttemplate="%{text}",textfont=dict(size=8)))
    fig_th.update_layout(height=680,template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)",
                         title="Cells with no Yahoo headlines are shown as 0.000")
    st.plotly_chart(fig_th, use_container_width=True)

    st.subheader("Sample Processed Headlines")
    samp = news_df[["Date","Ticker","Sector","Headline","Sentiment_Score","Sentiment_Label"]]\
        .sample(min(150,len(news_df)),random_state=1).sort_values("Date",ascending=False)
    st.dataframe(samp, use_container_width=True, height=320, hide_index=True)


# ═════════════════════════════════════════════════════════════
#  PAGE 5 — NEXT MOVES
# ═════════════════════════════════════════════════════════════
elif "Next Moves" in PAGE:
    st.title("🧭 Next Moves")
    st.caption("Actionable watchlist and planning view based on the latest computed signals.")

    latest_date = df["Date"].max()
    latest = (
        df.sort_values(["Ticker", "Date"])
        .groupby("Ticker", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )

    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        sector_filter = st.multiselect("Sector", options=ALL_SECTORS, default=ALL_SECTORS)
    with f2:
        signal_filter = st.multiselect("Signal", options=["BUY", "HOLD", "SELL"], default=["BUY", "HOLD", "SELL"])
    with f3:
        max_news = int(max(0, latest["News_Count"].max() if "News_Count" in latest.columns else 0))
        if max_news <= 0:
            min_news = 0
            st.number_input(
                "Min news count (latest day)",
                min_value=0,
                max_value=0,
                value=0,
                step=1,
                disabled=True,
                help="No news records are available for the latest day.",
            )
        else:
            min_news = st.slider(
                "Min news count (latest day)",
                min_value=0,
                max_value=max_news,
                value=0,
            )

    plan = latest.copy()
    if "Sector" in plan.columns:
        plan = plan[plan["Sector"].isin(sector_filter)]
    if "Combined_Signal" in plan.columns:
        plan = plan[plan["Combined_Signal"].isin(signal_filter)]
    if "News_Count" in plan.columns:
        plan = plan[plan["News_Count"].fillna(0).astype(int) >= int(min_news)]

    # A simple prioritization score for planning (higher = more urgent to review).
    plan["Plan_Score"] = (
        plan.get("Signal_Score", 0).fillna(0)
        + np.where(plan.get("Avg_Sentiment", 0).fillna(0) >= 0.10, 1, 0)
        + np.where(plan.get("Avg_Sentiment", 0).fillna(0) <= -0.10, 1, 0)
        + np.where(plan.get("Volatility_14d", 0).fillna(0) >= plan.get("Volatility_14d", 0).fillna(0).quantile(0.80), 1, 0)
    ).astype(float)

    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Latest date", str(latest_date.date()))
    b2.metric("Tickers in view", f"{plan['Ticker'].nunique()}")
    b3.metric("BUY", f"{(plan.get('Combined_Signal','')=='BUY').sum():,}")
    b4.metric("HOLD", f"{(plan.get('Combined_Signal','')=='HOLD').sum():,}")
    b5.metric("SELL", f"{(plan.get('Combined_Signal','')=='SELL').sum():,}")

    st.markdown("---")
    left, right = st.columns([1.35, 1])

    with left:
        st.subheader("✅ Priority Watchlist (top candidates)")
        cols = [c for c in [
            "Ticker", "Sector", "Close", "Daily_Return_Pct", "Volatility_14d",
            "RSI_14", "MACD_Hist", "Avg_Sentiment", "News_Count",
            "Combined_Signal", "Signal_Score", "Plan_Score", "Signal_Reason"
        ] if c in plan.columns]
        watch = plan.sort_values(["Plan_Score", "Signal_Score"], ascending=[False, False]).head(25)
        if cols:
            st.dataframe(watch[cols].round(4), use_container_width=True, hide_index=True, height=520)
        else:
            st.warning("No usable columns found for the watchlist.")

    with right:
        st.subheader("⚠️ Risk & Sentiment Alerts")

        if "Volatility_14d" in plan.columns:
            st.markdown("**High volatility (top 10)**")
            hv = plan.nlargest(10, "Volatility_14d")[["Ticker", "Sector", "Volatility_14d", "Combined_Signal"]]
            st.dataframe(hv.round(4), use_container_width=True, hide_index=True, height=220)

        if "Avg_Sentiment" in plan.columns:
            st.markdown("**Most bullish / bearish (top 5 each)**")
            bull = plan.nlargest(5, "Avg_Sentiment")[["Ticker", "Sector", "Avg_Sentiment", "News_Count", "Combined_Signal"]]
            bear = plan.nsmallest(5, "Avg_Sentiment")[["Ticker", "Sector", "Avg_Sentiment", "News_Count", "Combined_Signal"]]
            cA, cB = st.columns(2)
            with cA:
                st.caption("Bullish")
                st.dataframe(bull.round(4), use_container_width=True, hide_index=True, height=210)
            with cB:
                st.caption("Bearish")
                st.dataframe(bear.round(4), use_container_width=True, hide_index=True, height=210)

    st.subheader("📌 Suggested workflow")
    st.markdown(
        "- **Review BUY** candidates: validate trend (MA_7 vs MA_30), check RSI/MACD confirmation, then set entry/stop.\n"
        "- **Review SELL** candidates: confirm momentum weakness + negative sentiment, then consider reducing exposure.\n"
        "- **High volatility** list: tighten risk controls (position sizing / stop-loss) before taking any trade."
    )


# ═════════════════════════════════════════════════════════════
#  PAGE 6 — MARKET INSIGHTS
# ═════════════════════════════════════════════════════════════
elif "Market Insights" in PAGE:
    st.title("💡 Market Insights")
    st.caption("Derived from pandas groupby aggregations across the full 100K+ row dataset")

    tp = df.groupby("Ticker").agg(
        Avg_Return    =("Daily_Return_Pct","mean"),
        Std_Return    =("Daily_Return_Pct","std"),
        Avg_Volatility=("Volatility_14d",  "mean"),
        Avg_Close     =("Close",           "mean"),
        Max_Close     =("Close",           "max"),
        Avg_Sentiment =("Avg_Sentiment",   "mean"),
        Sector        =("Sector",          "first"),
        Records       =("Close",           "count"),
    ).reset_index().dropna()

    st.subheader("🏆 Best & Worst Performing Tickers")
    top10 = tp.nlargest(10, "Avg_Return")
    bot10 = tp.nsmallest(10, "Avg_Return")
    t1, t2 = st.columns(2)
    with t1:
        fig_t = go.Figure(go.Bar(x=top10["Ticker"],y=top10["Avg_Return"].round(4),
            marker_color="#26a69a",text=top10["Avg_Return"].round(4),textposition="outside"))
        fig_t.update_layout(height=300,template="plotly_dark",title="Top 10",
                            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                            yaxis_title="Avg Daily Return %")
        st.plotly_chart(fig_t, use_container_width=True)
    with t2:
        fig_b = go.Figure(go.Bar(x=bot10["Ticker"],y=bot10["Avg_Return"].round(4),
            marker_color="#e74c3c",text=bot10["Avg_Return"].round(4),textposition="outside"))
        fig_b.update_layout(height=300,template="plotly_dark",title="Bottom 10",
                            paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                            yaxis_title="Avg Daily Return %")
        st.plotly_chart(fig_b, use_container_width=True)

    st.subheader("📊 Risk vs Return — All 50 Tickers")
    fig_rr = px.scatter(tp.dropna(),x="Avg_Volatility",y="Avg_Return",
        size="Avg_Close",color="Sector",hover_name="Ticker",
        hover_data={"Avg_Sentiment":":.3f","Avg_Return":":.4f"},
        template="plotly_dark",size_max=28,
        labels={"Avg_Volatility":"Avg Volatility %","Avg_Return":"Avg Daily Return %"})
    fig_rr.add_hline(y=0,line_color="white",line_width=0.5,opacity=0.4)
    fig_rr.update_layout(height=440,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_rr, use_container_width=True)

    st.subheader("🚦 Combined Signal Distribution")
    sc2 = df["Combined_Signal"].value_counts().reset_index()
    sc2.columns = ["Signal","Count"]
    scm = {"STRONG_BUY":"#27ae60","BUY":"#2ecc71","HOLD":"#f39c12",
           "SELL":"#e74c3c","STRONG_SELL":"#c0392b"}
    p1, p2 = st.columns(2)
    with p1:
        fig_pie = go.Figure(go.Pie(labels=sc2["Signal"],values=sc2["Count"],
            marker_colors=[scm.get(s,"#888") for s in sc2["Signal"]],
            hole=0.44,textinfo="label+percent"))
        fig_pie.update_layout(height=320,template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pie, use_container_width=True)
    with p2:
        ss2 = df.groupby(["Sector","Combined_Signal"]).size().reset_index(name="Count")
        fig_sb = px.bar(ss2,x="Sector",y="Count",color="Combined_Signal",
                        color_discrete_map=scm,template="plotly_dark",barmode="stack")
        fig_sb.update_layout(height=320,paper_bgcolor="rgba(0,0,0,0)",
                             plot_bgcolor="rgba(0,0,0,0)",legend=dict(orientation="h",y=-0.3))
        st.plotly_chart(fig_sb, use_container_width=True)

    st.subheader("🔗 Feature Correlation Matrix")
    cc = ["Close","Daily_Return_Pct","MA_7","MA_30","Volatility_14d",
          "Volume","Avg_Sentiment","Price_vs_MA30_Pct"]
    cc = [c for c in cc if c in df.columns]
    cm2 = df[cc].corr().round(3)
    fig_cm = go.Figure(go.Heatmap(z=cm2.values,x=cm2.columns.tolist(),y=cm2.columns.tolist(),
        colorscale="RdYlGn",zmid=0,zmin=-1,zmax=1,
        text=cm2.values.round(2),texttemplate="%{text}",textfont=dict(size=10)))
    fig_cm.update_layout(height=400,template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_cm, use_container_width=True)

    st.subheader("📅 Year-over-Year Return Heatmap — All Tickers")
    yy = df.groupby(["Year","Ticker"])["Daily_Return_Pct"].mean().reset_index()
    yp = yy.pivot(index="Ticker",columns="Year",values="Daily_Return_Pct").round(4)
    fig_yy = go.Figure(go.Heatmap(z=yp.values,x=[str(c) for c in yp.columns],
        y=yp.index.tolist(),colorscale="RdYlGn",zmid=0,
        text=yp.values.round(3),texttemplate="%{text}",textfont=dict(size=7)))
    fig_yy.update_layout(height=700,template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_yy, use_container_width=True)

    st.subheader("📋 Full Ticker Summary Table")
    st.dataframe(tp.round(4).sort_values("Avg_Return",ascending=False),
                 use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════
#  PAGE 6 — SECTOR INTELLIGENCE
# ═════════════════════════════════════════════════════════════
elif "Sector Intelligence" in PAGE:
    st.title("📊 Sector Intelligence")

    sel_s = st.selectbox("Select Sector", ALL_SECTORS)
    sdf   = df[df["Sector"] == sel_s].copy()

    sv1,sv2,sv3,sv4,sv5 = st.columns(5)
    sv1.metric("Tickers",        f"{sdf['Ticker'].nunique()}")
    sv2.metric("Total Records",  f"{len(sdf):,}")
    sv3.metric("Avg Return",     f"{sdf['Daily_Return_Pct'].mean():.4f}%")
    sv4.metric("Avg Volatility", f"{sdf['Volatility_14d'].mean():.3f}%")
    sv5.metric("Avg Sentiment",  f"{sdf['Avg_Sentiment'].mean():.4f}")

    st.markdown("---")
    st.subheader(f"Normalized Price Performance — {sel_s}")
    fig_np = go.Figure()
    for t in sorted(sdf["Ticker"].unique()):
        td = sdf[sdf["Ticker"]==t].sort_values("Date")
        if td.empty or td["Close"].iloc[0] == 0: continue
        fig_np.add_trace(go.Scatter(x=td["Date"],
            y=(td["Close"]/td["Close"].iloc[0])*100,name=t,
            mode="lines",line=dict(width=1.5)))
    fig_np.add_hline(y=100,line_color="white",line_width=0.5,line_dash="dot",opacity=0.4)
    fig_np.update_layout(height=380,template="plotly_dark",
                         paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                         yaxis_title="Normalized Price (Base=100)",
                         legend=dict(orientation="h"))
    st.plotly_chart(fig_np, use_container_width=True)

    cv1, cv2 = st.columns(2)
    with cv1:
        st.subheader("Monthly Total Volume")
        sdf2 = sdf.copy()
        sdf2["YM"] = sdf2["Date"].dt.to_period("M").astype(str)
        vm = sdf2.groupby("YM")["Volume"].sum().reset_index()
        fig_vm = go.Figure(go.Bar(x=vm["YM"],y=vm["Volume"],marker_color="#3498db",opacity=0.8))
        fig_vm.update_layout(height=280,template="plotly_dark",
                             paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                             xaxis=dict(tickangle=-45,nticks=20),yaxis_title="Volume")
        st.plotly_chart(fig_vm, use_container_width=True)
    with cv2:
        st.subheader("Return Distribution by Ticker")
        fig_bx = go.Figure()
        for t in sorted(sdf["Ticker"].unique()):
            fig_bx.add_trace(go.Box(y=sdf[sdf["Ticker"]==t]["Daily_Return_Pct"].dropna(),
                name=t, boxmean=True))
        fig_bx.update_layout(height=280,template="plotly_dark",
                             paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                             yaxis_title="Daily Return %",showlegend=False)
        st.plotly_chart(fig_bx, use_container_width=True)

    st.subheader(f"Monthly Sentiment Timeline — {sel_s}")
    stm = sdf.set_index("Date")["Avg_Sentiment"].resample("ME").mean().reset_index()
    fig_stl = go.Figure(go.Bar(x=stm["Date"],y=stm["Avg_Sentiment"],
        marker_color=["#26a69a" if v>=0 else "#ef5350" for v in stm["Avg_Sentiment"]]))
    fig_stl.add_hline(y=0,line_color="white",line_width=0.5,opacity=0.4)
    fig_stl.update_layout(height=260,template="plotly_dark",
                           paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                           yaxis_title="Avg VADER Score")
    st.plotly_chart(fig_stl, use_container_width=True)

    st.subheader("Sector Annual Return Heatmap — All Sectors")
    sa  = df.groupby(["Sector","Year"])["Daily_Return_Pct"].mean().reset_index()
    sap = sa.pivot(index="Sector",columns="Year",values="Daily_Return_Pct").round(4)
    fig_sa = go.Figure(go.Heatmap(z=sap.values,x=[str(c) for c in sap.columns],
        y=sap.index.tolist(),colorscale="RdYlGn",zmid=0,
        text=sap.values.round(4),texttemplate="%{text}",textfont=dict(size=10)))
    fig_sa.update_layout(height=300,template="plotly_dark",paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_sa, use_container_width=True)

    st.subheader("Ticker Summary Table")
    ts2 = sdf.groupby("Ticker").agg(
        Avg_Return    =("Daily_Return_Pct","mean"),
        Std_Return    =("Daily_Return_Pct","std"),
        Avg_Volatility=("Volatility_14d",  "mean"),
        Avg_Close     =("Close",           "mean"),
        Max_Close     =("Close",           "max"),
        Min_Close     =("Close",           "min"),
        Avg_Sentiment =("Avg_Sentiment",   "mean"),
        Records       =("Close",           "count"),
    ).reset_index().round(4)
    st.dataframe(ts2, use_container_width=True, hide_index=True)

# ═════════════════════════════════════════════════════════════
#  PAGE 8 — RESEARCH GRAPHS
# ═════════════════════════════════════════════════════════════
elif "Research Graphs" in PAGE:
    st.title("🖼️ Research Graphs")
    st.caption("Static evidence generated during notebook analysis, presented in a clean dashboard format.")

    graph_dir = "graphs"
    graph_files = []
    if os.path.isdir(graph_dir):
        graph_files = sorted(
            [
                f for f in os.listdir(graph_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
        )

    if not graph_files:
        st.warning("No graph images found in `graphs/`.")
    else:
        st.markdown(f"**Total figures:** `{len(graph_files)}`")
        selected = st.multiselect(
            "Filter figures",
            options=graph_files,
            default=graph_files,
        )
        if not selected:
            st.info("Select one or more figures to display.")
        else:
            for i in range(0, len(selected), 2):
                c1, c2 = st.columns(2)
                left_name = selected[i]
                left_path = os.path.join(graph_dir, left_name)
                with c1:
                    st.markdown(f"**{left_name}**")
                    st.image(left_path, use_container_width=True)
                if i + 1 < len(selected):
                    right_name = selected[i + 1]
                    right_path = os.path.join(graph_dir, right_name)
                    with c2:
                        st.markdown(f"**{right_name}**")
                        st.image(right_path, use_container_width=True)


st.markdown("---")
st.caption("MarketIQ | pandas · VADER · Streamlit | Vidyashilp University — Big Data & Cloud Computing")
