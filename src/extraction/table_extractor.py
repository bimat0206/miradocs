"""Table extraction from parsed document output."""
import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.intake.file_manager import get_tables_dir

logger = logging.getLogger(__name__)


def extract_tables(parse_result: dict[str, Any], doc_id: str) -> list[dict]:
    """Extract tables from parse result, save as CSV and markdown."""
    tables = parse_result.get("tables", [])
    output_dir = get_tables_dir(doc_id)
    if not tables:
        logger.info(f"No tables found for {doc_id}")
        (output_dir / "tables_index.json").write_text("[]", encoding="utf-8")
        return []

    extracted = []

    for i, table in enumerate(tables):
        table_id = table.get("table_id", f"table_{i:03d}")
        page = table.get("page", 0)
        data = table.get("data", {})

        # Try to extract grid from Docling table data
        grid = _extract_grid(data)
        if not grid:
            # Store raw data as-is
            extracted.append({
                "table_id": table_id,
                "page": page,
                "rows": 0,
                "cols": 0,
                "file_csv": None,
                "file_md": None,
                "status": "no_grid",
            })
            continue

        rows, cols = len(grid), max(len(r) for r in grid) if grid else 0

        # Save CSV
        csv_path = output_dir / f"{table_id}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(grid)

        # Save Markdown
        md_path = output_dir / f"{table_id}.md"
        md_path.write_text(_grid_to_markdown(grid), encoding="utf-8")

        extracted.append({
            "table_id": table_id,
            "page": page,
            "rows": rows,
            "cols": cols,
            "file_csv": str(csv_path),
            "file_md": str(md_path),
            "status": "extracted",
        })

    # Save table index
    index_path = output_dir / "tables_index.json"
    index_path.write_text(json.dumps(extracted, indent=2), encoding="utf-8")
    logger.info(f"Extracted {len(extracted)} tables for {doc_id}")
    return extracted


def _extract_grid(data: Any) -> list[list[str]]:
    """Extract a 2D grid from Docling table data structure."""
    if not data:
        return []

    # Docling table_data format: has "grid" or "table_cells"
    if isinstance(data, dict):
        # Direct grid format
        if "grid" in data:
            return data["grid"]
        # Cell-based format
        if "table_cells" in data:
            return _cells_to_grid(data["table_cells"], data.get("num_rows", 0), data.get("num_cols", 0))
    # If data is already a list of lists
    if isinstance(data, list) and data and isinstance(data[0], list):
        return data

    return []


def _cells_to_grid(cells: list, num_rows: int, num_cols: int) -> list[list[str]]:
    """Convert Docling cell list to 2D grid."""
    if not num_rows:
        num_rows = max(
            (cell.get("end_row_offset_idx", cell.get("row", cell.get("row_index", 0)) + 1)
             for cell in cells if isinstance(cell, dict)),
            default=0,
        )
    if not num_cols:
        num_cols = max(
            (cell.get("end_col_offset_idx", cell.get("col", cell.get("col_index", 0)) + 1)
             for cell in cells if isinstance(cell, dict)),
            default=0,
        )
    if not num_rows or not num_cols:
        return []
    grid = [[""] * num_cols for _ in range(num_rows)]
    for cell in cells:
        if isinstance(cell, dict):
            row = cell.get("row", cell.get("row_index", cell.get("start_row_offset_idx", 0)))
            col = cell.get("col", cell.get("col_index", cell.get("start_col_offset_idx", 0)))
            text = cell.get("text", cell.get("content", ""))
            if 0 <= row < num_rows and 0 <= col < num_cols:
                grid[row][col] = str(text)
    return grid


def _grid_to_markdown(grid: list[list[str]]) -> str:
    """Convert 2D grid to markdown table."""
    if not grid:
        return ""
    lines = []
    # Header
    lines.append("| " + " | ".join(str(c) for c in grid[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in grid[0]) + " |")
    # Body
    for row in grid[1:]:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)
