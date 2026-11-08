"""Data normalization and indicator summaries used by the dashboard."""

import numpy as np
import pandas as pd


def normalize_processed_frame(frame):
    frame = frame.copy()

    # Keep notebook and dashboard column names aligned without failing on older exports.
    if "MA7" in frame.columns and "MA_7" not in frame.columns:
        frame["MA_7"] = frame["MA7"]
    if "MA30" in frame.columns and "MA_30" not in frame.columns:
        frame["MA_30"] = frame["MA30"]
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
        pieces.append("the indicators do not provide a consistent direction")

    return "; ".join(pieces)
