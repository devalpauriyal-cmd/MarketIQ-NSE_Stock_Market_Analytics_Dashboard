"""FastAPI API for the MarketIQ dashboard on Vercel."""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "processed_data.csv"
NEWS_FILE = ROOT / "data" / "news_raw.xlsx"
app = FastAPI(title="MarketIQ API", version="1.0.0", docs_url="/api/docs", redoc_url=None)

ALIASES = {
    "MA_7": ("MA_7", "MA7"),
    "MA_30": ("MA_30", "MA30"),
    "MA_60": ("MA_60", "MA60"),
    "Volume_MA_7": ("Volume_MA_7", "Volume_MA7"),
}
FIELDS = (
    "Date", "Ticker", "Sector", "Close", "Volume", "Daily_Return_Pct",
    "MA_7", "MA_30", "MA_60", "Volatility_14d", "Avg_Sentiment",
    "Combined_Signal", "Signal_Reason", "RSI_14", "MACD_Line", "News_Count",
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _value(row: dict[str, str], key: str) -> str:
    for candidate in ALIASES.get(key, (key,)):
        if candidate in row and row[candidate] not in (None, ""):
            return row[candidate]
    return ""


def _load_sentiment() -> dict[tuple[str, str], tuple[float, int]]:
    """Read the small cached headline workbook without pulling pandas into the function."""
    if not NEWS_FILE.is_file():
        return {}
    totals: dict[tuple[str, str], list[float]] = defaultdict(list)
    try:
        workbook = load_workbook(NEWS_FILE, read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else "" for value in next(rows)]
        positions = {name: index for index, name in enumerate(headers)}
        required = {"Date", "Ticker", "Sentiment_Score"}
        if not required.issubset(positions):
            workbook.close()
            return {}
        for row in rows:
            raw_date = row[positions["Date"]]
            raw_ticker = row[positions["Ticker"]]
            if raw_date is None or raw_ticker is None:
                continue
            date_key = raw_date.strftime("%Y-%m-%d") if hasattr(raw_date, "strftime") else str(raw_date)[:10]
            ticker_key = str(raw_ticker).strip()
            score = _number(row[positions["Sentiment_Score"]])
            totals[(date_key, ticker_key)].append(score)
        workbook.close()
    except Exception:
        return {}
    return {key: (sum(values) / len(values), len(values)) for key, values in totals.items() if values}


def _ema(values: list[float], span: int) -> list[float]:
    alpha = 2.0 / (span + 1.0)
    result: list[float] = []
    current = values[0] if values else 0.0
    for index, value in enumerate(values):
        current = value if index == 0 else alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def _enrich_records(records: list[dict[str, Any]]) -> None:
    """Rebuild the dashboard's rolling indicators and composite rule-based signal."""
    closes = [row["Close"] for row in records]
    volumes = [row["Volume"] for row in records]
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    macd = [a - b for a, b in zip(ema12, ema26)]
    macd_signal = _ema(macd, 9)
    avg_gain = avg_loss = 0.0
    for i, row in enumerate(records):
        def rolling(values: list[float], window: int) -> float:
            sample = values[max(0, i - window + 1):i + 1]
            return sum(sample) / len(sample) if sample else 0.0
        row["MA_7"] = rolling(closes, 7)
        row["MA_30"] = rolling(closes, 30)
        row["MA_60"] = rolling(closes, 60)
        volume_ma = rolling(volumes, 7)
        row["MACD_Line"] = macd[i]
        row["MACD_Hist"] = macd[i] - macd_signal[i]
        if i == 0:
            change = 0.0
        else:
            change = closes[i] - closes[i - 1]
        gain, loss = max(change, 0.0), max(-change, 0.0)
        if i > 0:
            avg_gain = (avg_gain * 13.0 + gain) / 14.0
            avg_loss = (avg_loss * 13.0 + loss) / 14.0
        rs = avg_gain / avg_loss if avg_loss > 0 else None
        row["RSI_14"] = 100.0 - (100.0 / (1.0 + rs)) if rs is not None else 50.0
        trend = 1 if row["MA_7"] > row["MA_30"] else (-1 if row["MA_7"] < row["MA_30"] else 0)
        macd_score = 1 if row["MACD_Hist"] > 0 else (-1 if row["MACD_Hist"] < 0 else 0)
        rsi_score = 1 if row["RSI_14"] <= 35 else (-1 if row["RSI_14"] >= 65 else 0)
        volume_ratio = row["Volume"] / volume_ma if volume_ma > 0 else 1.0
        volume_score = 1 if volume_ratio >= 1.25 and trend > 0 else (-1 if volume_ratio >= 1.25 and trend < 0 else 0)
        sentiment = row["Avg_Sentiment"]
        sentiment_score = 1 if sentiment >= 0.10 else (-1 if sentiment <= -0.10 else 0)
        score = trend + macd_score + rsi_score + volume_score + sentiment_score
        row["Combined_Signal"] = "BUY" if score >= 2 else ("SELL" if score <= -2 else "HOLD")
        row["Signal_Reason"] = (
            f"Trend {'positive' if trend > 0 else 'negative' if trend < 0 else 'neutral'}; "
            f"MACD {'positive' if macd_score > 0 else 'negative' if macd_score < 0 else 'neutral'}; "
            f"RSI {row['RSI_14']:.1f}; sentiment {sentiment:.2f}"
        )

@lru_cache(maxsize=1)
def _load_market_data() -> dict[str, Any]:
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"Required dataset not found: {DATA_FILE}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sectors: dict[str, str] = {}
    sentiment_lookup = _load_sentiment()
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "Ticker" not in reader.fieldnames:
            raise ValueError("processed_data.csv is missing the Ticker column")
        for raw in reader:
            ticker = (raw.get("Ticker") or "").strip()
            if not ticker:
                continue
            date_value = raw.get("Date", "")
            matched_sentiment = sentiment_lookup.get((str(date_value)[:10], ticker))
            record: dict[str, Any] = {
                "Date": raw.get("Date", ""),
                "Ticker": ticker,
                "Sector": raw.get("Sector", "Unknown") or "Unknown",
                "Close": _number(raw.get("Close")),
                "Volume": _number(raw.get("Volume")),
                "Daily_Return_Pct": _number(raw.get("Daily_Return_Pct")),
                "MA_7": _number(_value(raw, "MA_7")),
                "MA_30": _number(_value(raw, "MA_30")),
                "MA_60": _number(_value(raw, "MA_60")),
                "Volatility_14d": _number(raw.get("Volatility_14d")),
                "Avg_Sentiment": _number(raw.get("Avg_Sentiment")) if raw.get("Avg_Sentiment") not in (None, "") else (matched_sentiment[0] if matched_sentiment else 0.0),
                "Combined_Signal": raw.get("Combined_Signal", "HOLD") or "HOLD",
                "Signal_Reason": raw.get("Signal_Reason", "") or "",
                "RSI_14": _number(raw.get("RSI_14")),
                "MACD_Line": _number(raw.get("MACD_Line")),
                "News_Count": int(_number(raw.get("News_Count"))) if raw.get("News_Count") not in (None, "") else (matched_sentiment[1] if matched_sentiment else 0),
            }
            grouped[ticker].append(record)
            sectors[ticker] = record["Sector"]
    for records in grouped.values():
        records.sort(key=lambda item: item["Date"])
        _enrich_records(records)
    if not grouped:
        raise ValueError("processed_data.csv contains no usable ticker rows")
    return {"stocks": dict(grouped), "sectors": sectors}


def _latest_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [records[-1] for records in data["stocks"].values() if records]


@app.get("/api/health")
def health():
    try:
        data = _load_market_data()
        return {"status": "ok", "tickers": len(data["stocks"]), "rows": sum(map(len, data["stocks"].values()))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/summary")
def summary():
    try:
        data = _load_market_data()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    latest = _latest_rows(data)
    returns = [row["Daily_Return_Pct"] for row in latest]
    return {
        "tickers": len(latest),
        "sectors": len({row["Sector"] for row in latest}),
        "latest_date": max((row["Date"] for row in latest), default=""),
        "avg_daily_return": round(sum(returns) / len(returns), 4) if returns else 0,
        "buy": sum(row["Combined_Signal"] in ("BUY", "STRONG_BUY") for row in latest),
        "hold": sum(row["Combined_Signal"] == "HOLD" for row in latest),
        "sell": sum(row["Combined_Signal"] in ("SELL", "STRONG_SELL") for row in latest),
        "avg_sentiment": round(sum(row["Avg_Sentiment"] for row in latest) / len(latest), 4) if any(row["News_Count"] for row in latest) else None,
    }


@app.get("/api/stocks")
def stocks(q: str = Query(default="", max_length=30), sector: str = Query(default="", max_length=80)):
    try:
        data = _load_market_data()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    rows = _latest_rows(data)
    query = q.strip().lower()
    if query:
        rows = [row for row in rows if query in row["Ticker"].lower()]
    if sector:
        rows = [row for row in rows if row["Sector"] == sector]
    rows.sort(key=lambda row: row["Ticker"])
    return {"items": rows}


@app.get("/api/history/{ticker}")
def history(ticker: str, limit: int = Query(default=260, ge=20, le=1500)):
    try:
        data = _load_market_data()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    key = ticker.upper()
    records = data["stocks"].get(key)
    if records is None:
        raise HTTPException(status_code=404, detail=f"Ticker not found: {key}")
    return {"ticker": key, "items": records[-limit:]}


@app.get("/api/sectors")
def sectors():
    try:
        data = _load_market_data()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _latest_rows(data):
        grouped[row["Sector"]].append(row)
    result = []
    for name, rows in grouped.items():
        result.append({
            "sector": name,
            "tickers": len(rows),
            "avg_return": round(sum(r["Daily_Return_Pct"] for r in rows) / len(rows), 4),
            "avg_volatility": round(sum(r["Volatility_14d"] for r in rows) / len(rows), 4),
            "avg_sentiment": round(sum(r["Avg_Sentiment"] for r in rows) / len(rows), 4) if any(r["News_Count"] for r in rows) else None,
            "buy": sum(r["Combined_Signal"] == "BUY" for r in rows),
            "sell": sum(r["Combined_Signal"] == "SELL" for r in rows),
        })
    return {"items": sorted(result, key=lambda item: item["sector"])}
