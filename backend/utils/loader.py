from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


class DataLoadError(Exception):
    """Raised when a required data artifact cannot be loaded or validated."""


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_data_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def load_csv(path: str, required_columns: Iterable[str] | None = None) -> pd.DataFrame:
    csv_path = resolve_data_path(path)
    if not csv_path.exists():
        raise DataLoadError(f"Required data file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    if required_columns:
        missing = [column for column in required_columns if column not in df.columns]
        if missing:
            raise DataLoadError(
                f"Missing required columns in {csv_path.name}: {', '.join(missing)}"
            )

    if df.empty:
        raise DataLoadError(f"Data file is empty: {csv_path}")

    return df
