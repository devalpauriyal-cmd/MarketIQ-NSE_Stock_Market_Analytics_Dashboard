# Data files

| File | Rows | Columns | Used by |
| --- | ---: | ---: | --- |
| `stocks_raw.xlsx` | 113,690 | 9 | Notebook input and dashboard inspector |
| `nifty_raw.xlsx` | 2,708 | 2 | Notebook beta calculation |
| `processed_data.csv` | 113,690 | 32 | Dashboard input |
| `processed_data.xlsx` | 113,690 | 32 | Excel export of the processed analysis |
| `news_raw.xlsx` | 210 | 7 | Dashboard headline and sentiment views |

Price dates span 2015-01-01 to 2025-12-31. The processed data has 42 stocks across Auto, Banking, Consumer, Energy, Finance, IT, Infra, Metals and Pharma.

There are no duplicate date/ticker keys or OHLC ordering violations in the processed CSV. Missing previous-close and return values occur on the first observation of each stock: 42 rows per return column. Rolling volatility has 84 missing values near the beginning of the series. These are expected calculation boundaries, not evidence that the raw workbooks contained missing prices.

The news snapshot spans 2025-10-17 to 2026-04-28. All 210 stored scores match VADER compound scores when recalculated from the supplied headlines. Twenty-nine headlines match a stored date/ticker price row. The workbook records publisher names but no article URLs or collection timestamps, so its original acquisition cannot be independently reconstructed from this repository.

The notebook reads the raw workbooks by default. Set `REFRESH_DATA = True` for a fresh yfinance request; returned historical data can change as providers revise their series. The processed CSV and Excel workbook are both retained intentionally. Original data-file contents were preserved during cleanup.
