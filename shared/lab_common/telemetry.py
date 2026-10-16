"""Notebook-friendly trace rendering."""
from __future__ import annotations

import pandas as pd


def trace_frame(trace: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(trace, columns=["step", "event", "payload"])

