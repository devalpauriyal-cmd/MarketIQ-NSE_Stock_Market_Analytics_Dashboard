import numpy as np
import pandas as pd

from marketiq.analysis import normalize_processed_frame, _add_signal_features


def price_rows():
    dates = pd.date_range("2025-01-01", periods=70)
    frames = []
    for ticker, offset in [("FIRST.NS", 0), ("SECOND.NS", 1000)]:
        close = np.arange(1, 71, dtype=float) + offset
        frames.append(pd.DataFrame({
            "Date": dates, "Ticker": ticker, "Close": close,
            "High": close + 1, "Low": close - 1, "Volume": 100,
            "MA7": close, "MA30": close - 1, "MA200": 9000.0,
        }))
    return pd.concat(frames).sample(frac=1, random_state=1)


def test_sixty_session_average_is_not_a_renamed_two_hundred_session_average():
    actual = normalize_processed_frame(price_rows())
    latest = actual.groupby("Ticker").tail(1).set_index("Ticker")
    assert latest.loc["FIRST.NS", "MA_60"] == 40.5
    assert latest.loc["SECOND.NS", "MA_60"] == 1040.5
    assert (actual["MA200"] == 9000).all()


def test_precomputed_sixty_session_average_is_retained():
    frame = price_rows()
    frame["MA_60"] = 123.5
    assert (normalize_processed_frame(frame)["MA_60"] == 123.5).all()


def test_indicator_history_does_not_cross_between_stocks():
    frame = normalize_processed_frame(price_rows())
    actual = _add_signal_features(frame)
    first = actual.groupby("Ticker").head(1)
    assert (first["MACD_Line"] == 0).all()
    assert (first["MACD_Hist"] == 0).all()
    assert actual["Signal_Score"].between(-5, 5).all()
    assert set(actual["Combined_Signal"]) <= {"BUY", "HOLD", "SELL"}
