from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import pandas as pd


@dataclass
class CanonicalResult:
    canonical_json: bytes
    schema_summary_json: bytes
    row_counts: Dict[str, int]
    column_counts: Dict[str, int]
    schema_hash: str


def _minimize_df(df: pd.DataFrame, max_rows: int = 5000, max_cols: int = 80) -> pd.DataFrame:
    # Basic minimization (generic): drop fully-empty rows/cols, cap sizes
    df = df.copy()
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.shape[0] > max_rows:
        df = df.head(max_rows)
    if df.shape[1] > max_cols:
        df = df.iloc[:, :max_cols]
    # Normalize column names
    df.columns = [str(c).strip()[:120] for c in df.columns]
    return df


def excel_to_canonical(excel_bytes: bytes) -> CanonicalResult:
    # Read all sheets
    xls = pd.ExcelFile(excel_bytes)
    canonical: Dict[str, Any] = {"sheets": {}}
    row_counts: Dict[str, int] = {}
    col_counts: Dict[str, int] = {}

    for sheet in xls.sheet_names:
        try:
            df = xls.parse(sheet_name=sheet)
        except Exception:
            # Skip unreadable sheets
            continue
        df = _minimize_df(df)
        row_counts[sheet] = int(df.shape[0])
        col_counts[sheet] = int(df.shape[1])

        # Convert to records; this is still sensitive, but stored encrypted in COS and TTL-limited.
        canonical["sheets"][sheet] = {
            "columns": list(df.columns),
            "rows": df.fillna("").astype(str).to_dict(orient="records"),
        }

    schema_summary = {
        "sheet_count": len(canonical["sheets"]),
        "row_counts": row_counts,
        "column_counts": col_counts,
        "notes": [
            "This is a minimized canonical representation for short-term use.",
            "Raw file should be deleted after canonicalization.",
        ],
    }

    canonical_json = json.dumps(canonical, ensure_ascii=False).encode("utf-8")
    schema_json = json.dumps(schema_summary, ensure_ascii=False).encode("utf-8")

    import hashlib
    schema_hash = hashlib.sha256(schema_json).hexdigest()
    return CanonicalResult(
        canonical_json=canonical_json,
        schema_summary_json=schema_json,
        row_counts=row_counts,
        column_counts=col_counts,
        schema_hash=schema_hash,
    )
