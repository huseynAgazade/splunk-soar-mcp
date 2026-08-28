"""Rendering helpers.

Tool results are read by a language model, so they are formatted as compact
aligned text rather than raw JSON: a 25-row table of containers costs a small
fraction of the tokens the equivalent JSON does, and stays readable. Every
listing tool still takes ``as_json=True`` for when the full record is wanted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .redaction import is_sensitive_key
from .redaction import redact as _redact

MAX_CELL = 60
REDACTED_CELL = "«redacted»"


def to_json(value: Any, *, redact: bool = True) -> str:
    """Serialise for the caller.

    Redacts by default: this is the one place every tool's raw output passes
    through, which makes it the right place to guarantee credentials do not
    leave the process. Pass ``redact=False`` only for data that provably
    contains none, and be sure of it.
    """
    if redact:
        value = _redact(value)
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def _cell(value: Any, limit: int = MAX_CELL) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text or "-"


def table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    empty: str = "(no results)",
    total: int | None = None,
) -> str:
    """Render rows as a fixed-width table with a trailing count."""
    if not rows:
        return empty

    cells = [
        [REDACTED_CELL if is_sensitive_key(col) else _cell(row.get(col)) for col in columns]
        for row in rows
    ]
    widths = [
        max(len(col), *(len(cells[r][i]) for r in range(len(cells))))
        for i, col in enumerate(columns)
    ]

    lines = [
        "  ".join(col.ljust(widths[i]) for i, col in enumerate(columns)),
        "  ".join("-" * widths[i] for i in range(len(columns))),
    ]
    lines.extend("  ".join(row[i].ljust(widths[i]) for i in range(len(columns))) for row in cells)

    shown = len(rows)
    if total is not None and total > shown:
        lines.append(f"\n{shown} of {total} shown — raise page_size or pass page=1 for more.")
    else:
        lines.append(f"\n{shown} row(s)")
    return "\n".join(lines)


def details(record: Mapping[str, Any], keys: Iterable[str], *, width: int = 22) -> str:
    """Render selected keys of one object as an aligned key/value block."""
    lines = []
    for key in keys:
        if key not in record:
            continue
        if is_sensitive_key(key):
            lines.append(f"{key.ljust(width)}  {REDACTED_CELL}")
            continue
        value = record[key]
        if isinstance(value, (dict, list)):
            value = to_json(value)
            if len(value) > 400:
                value = value[:400] + "…"
            lines.append(f"{key.ljust(width)}  {value}")
        else:
            lines.append(f"{key.ljust(width)}  {_cell(value, limit=200)}")
    return "\n".join(lines) if lines else "(empty)"


def listing(
    payload: Mapping[str, Any],
    columns: Sequence[str],
    *,
    as_json: bool = False,
    empty: str = "(no results)",
) -> str:
    """Render a SOAR collection response — the ``{count, data: [...]}`` shape."""
    rows = payload.get("data") or []
    if as_json:
        return to_json(rows)
    return table(rows, columns, empty=empty, total=payload.get("count"))
