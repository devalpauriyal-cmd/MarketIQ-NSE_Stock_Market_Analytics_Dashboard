from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]


def test_notebook_has_valid_schema_and_compilable_code_cells():
    notebook = nbformat.read(ROOT / "notebooks" / "market_iq.ipynb", as_version=4)
    nbformat.validate(notebook)
    for number, cell in enumerate(notebook.cells):
        if cell.cell_type == "code":
            compile(cell.source, f"cell-{number}", "exec")
            assert cell.outputs == []
