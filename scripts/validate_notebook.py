"""Run the analysis against saved workbooks in a separate output directory."""
import contextlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compare_exports(actual, expected):
    import numpy as np
    import pandas as pd

    # The raw Excel snapshot rounds one source value enough to move a
    # three-decimal intraday percentage by one unit in its last decimal.
    column = "Intraday_Range_Pct"
    pd.testing.assert_frame_equal(actual.drop(columns=[column]), expected.drop(columns=[column]),
                                  check_dtype=False, check_exact=False, rtol=1e-8, atol=1e-5)
    np.testing.assert_allclose(actual[column], expected[column], rtol=0, atol=0.0010000001, equal_nan=True)
    return int(((actual[column] - expected[column]).abs() > 1e-5).sum())


def main():
    artifacts = ROOT / ".local-artifacts"
    artifacts.mkdir(exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(artifacts / "matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    import yfinance as yf

    output = Path(tempfile.mkdtemp(prefix="notebook-check-", dir=artifacts)).resolve()
    assert output.is_relative_to(artifacts.resolve())
    (output / "data").mkdir()
    (output / "app.py").touch()
    for name in ["stocks_raw.xlsx", "nifty_raw.xlsx"]:
        shutil.copy2(ROOT / "data" / name, output / "data" / name)
    notebook = json.loads((ROOT / "notebooks" / "market_iq.ipynb").read_text(encoding="utf-8"))
    original_download = yf.download
    original_show = plt.show
    original_cwd = Path.cwd()

    def no_download(*args, **kwargs):
        raise AssertionError("The cached notebook attempted a Yahoo Finance download")

    yf.download = no_download
    plt.show = lambda *args, **kwargs: plt.close("all")
    scope = {"__name__": "__main__"}
    started = time.monotonic()
    try:
        os.chdir(output)
        with (artifacts / "notebook-validation.log").open("w", encoding="utf-8") as log:
            for number, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] != "code":
                    continue
                print(f"Running cell {number}", flush=True)
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    exec(compile("".join(cell["source"]), f"cell-{number}", "exec"), scope)
        expected = pd.read_csv(ROOT / "data" / "processed_data.csv", parse_dates=["Date"])
        actual = pd.read_csv(output / "data" / "processed_data.csv", parse_dates=["Date"])
        rounding_differences = compare_exports(actual, expected)
        result = {"rows": len(actual), "columns": len(actual.columns),
                  "figures": len(list((output / "graphs").glob("*.png"))),
                  "beta_rows": len(scope["beta_pd"]), "matches_saved_csv_with_rounding_tolerance": True,
                  "intraday_range_rounding_differences": rounding_differences,
                  "seconds": round(time.monotonic() - started, 1)}
        (artifacts / "notebook-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        print(f"Validation output: {output}")
    finally:
        yf.download = original_download
        plt.show = original_show
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
