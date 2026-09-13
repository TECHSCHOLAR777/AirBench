"""Table recovery from OCR page results.

OCR engines return text lines, not tables.  This module turns aligned lines
into typed ``StructuredTable`` values so a scanned three-column inspection
table does not collapse into flat text.  Values stay strings; a column's unit
is carried separately in ``units`` so it can never be silently separated from
the number by a later stage.

The built-in heuristic is deterministic and offline.  A model-based extractor
can be injected behind the same ``TableExtractor`` protocol without changing
the intake layer.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Protocol, Sequence

from contracts import StructuredTable, stable_id

from .ocr_provider import OcrLine, OcrPageResult

_CELL_SPLIT = re.compile(r"\t+|\s{2,}")
_UNIT = re.compile(r"^(?P<name>.+?)\s*[\[(](?P<unit>[^\])]+)[\])]\s*$")


class TableExtractor(Protocol):
    """Recover typed tables from one OCR page result."""

    name: str
    version: str

    def extract(self, result: OcrPageResult, *, source_ref: str = "") -> tuple[StructuredTable, ...]: ...


def _cells(line: OcrLine) -> tuple[str, ...]:
    parts = tuple(cell.strip() for cell in _CELL_SPLIT.split(line.text.strip()))
    return tuple(cell for cell in parts if cell)


def _units_from_header(header: Sequence[str]) -> dict[str, str]:
    units: dict[str, str] = {}
    for column in header:
        match = _UNIT.match(column)
        if match:
            units[column] = match.group("unit").strip()
    return units


class GridLineTableExtractor:
    """Offline whitespace/column heuristic for uniform OCR tables.

    Consecutive lines that split into the same number of columns (at least
    ``min_columns``) form one table.  The first row is treated as the header
    and its ``name (unit)`` cells populate ``units``.
    """

    def __init__(self, *, name: str = "grid_line", version: str = "1.0", min_columns: int = 2, min_rows: int = 2) -> None:
        if not name or not version or min_columns < 2 or min_rows < 1:
            raise ValueError("grid-line table extractor configuration is invalid")
        self.name = name
        self.version = version
        self.min_columns = min_columns
        self.min_rows = min_rows

    def extract(self, result: OcrPageResult, *, source_ref: str = "") -> tuple[StructuredTable, ...]:
        tables: list[StructuredTable] = []
        block: list[tuple[OcrLine, tuple[str, ...]]] = []

        def flush() -> None:
            if len(block) >= self.min_rows + 1 and len(block[0][1]) >= self.min_columns:
                header = block[0][1]
                rows = tuple(cells for _, cells in block[1:])
                width = len(header)
                if all(len(cells) == width for cells in rows):
                    line_confidences = [line.confidence for line, _ in block]
                    confidence = sum(line_confidences) / len(line_confidences)
                    column_index = len(tables)
                    tables.append(StructuredTable(
                        table_id=stable_id("table", result.provider_name, result.page_number, column_index, "|".join(header)),
                        page_number=result.page_number,
                        headers=header,
                        rows=rows,
                        confidence=confidence,
                        extraction_method=f"table_{result.provider_name}",
                        units=_units_from_header(header),
                        source_ref=source_ref,
                        source_span=f"page:{result.page_number}:table:{column_index}",
                    ))
            block.clear()

        for line in result.lines:
            cells = _cells(line)
            if len(cells) >= self.min_columns:
                if block and len(block[0][1]) != len(cells):
                    flush()
                block.append((line, cells))
            else:
                flush()
        flush()
        return tuple(tables)


def extract_tables(
    result: OcrPageResult,
    extractor: TableExtractor | None,
    *,
    source_ref: str = "",
) -> OcrPageResult:
    """Return a result whose ``tables`` are populated by ``extractor``.

    The original result is returned unchanged when no extractor is supplied or
    when the provider already produced typed tables.
    """

    if extractor is None or result.tables:
        return result

    return replace(result, tables=extractor.extract(result, source_ref=source_ref))


__all__ = ["GridLineTableExtractor", "TableExtractor", "extract_tables"]
