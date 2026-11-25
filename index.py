"""FastAPI API for the MarketIQ dashboard on Vercel."""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "processed_data.csv"
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


@lru_cache(maxsize=1)
def _load_market_data() -> dict[str, Any]:
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"Required dataset not found: {DATA_FILE}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sectors: dict[str, str] = {}
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "Ticker" not in reader.fieldnames:
            raise ValueError("processed_data.csv is missing the Ticker column")
        for raw in reader:
            ticker = (raw.get("Ticker") or "").strip()
            if not ticker:
                continue
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
                "Avg_Sentiment": _number(raw.get("Avg_Sentiment")),
                "Combined_Signal": raw.get("Combined_Signal", "HOLD") or "HOLD",
                "Signal_Reason": raw.get("Signal_Reason", "") or "",
                "RSI_14": _number(raw.get("RSI_14")),
                "MACD_Line": _number(raw.get("MACD_Line")),
                "News_Count": int(_number(raw.get("News_Count"))),
            }
            grouped[ticker].append(record)
            sectors[ticker] = record["Sector"]
    for records in grouped.values():
        records.sort(key=lambda item: item["Date"])
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
        "avg_sentiment": round(sum(row["Avg_Sentiment"] for row in latest) / len(latest), 4) if latest else 0,
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
            "avg_sentiment": round(sum(r["Avg_Sentiment"] for r in rows) / len(rows), 4),
            "buy": sum(r["Combined_Signal"] == "BUY" for r in rows),
            "sell": sum(r["Combined_Signal"] == "SELL" for r in rows),
        })
    return {"items": sorted(result, key=lambda item: item["sector"])}
