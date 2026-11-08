from pathlib import Path

import pytest
import yfinance as yf
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "Pipeline Overview", "Stage Inspector", "Stock Analysis", "Sentiment Analysis",
    "Next Moves", "Market Insights", "Sector Intelligence", "Research Graphs",
]


@pytest.fixture(scope="module")
def dashboard():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


@pytest.mark.parametrize("page", PAGES)
def test_dashboard_pages_with_cached_data(dashboard, page, monkeypatch, tmp_path):
    fetches = []
    def unexpected_fetch(*args, **kwargs):
        fetches.append(args)
        raise AssertionError("The included data must not need live Yahoo requests")

    monkeypatch.setattr(yf, "Ticker", unexpected_fetch)
    monkeypatch.chdir(tmp_path)
    assert not dashboard.exception
    option = next(item for item in dashboard.sidebar.radio[0].options if page in item)
    dashboard.sidebar.radio[0].set_value(option).run()
    assert not dashboard.exception
    assert dashboard.title
    assert not fetches


def test_missing_news_does_not_break_the_sentiment_page(dashboard, monkeypatch):
    import os
    import streamlit as st

    exists = os.path.exists
    monkeypatch.setattr(os.path, "exists", lambda path: False if str(path).endswith("news_raw.xlsx") else exists(path))
    monkeypatch.setattr(yf, "Ticker", lambda *args: (_ for _ in ()).throw(OSError("offline")))
    st.cache_data.clear()
    option = next(item for item in dashboard.sidebar.radio[0].options if "Sentiment Analysis" in item)
    dashboard.sidebar.radio[0].set_value(option).run()
    assert not dashboard.exception
    assert any("No headline data" in message.value for message in dashboard.info)
