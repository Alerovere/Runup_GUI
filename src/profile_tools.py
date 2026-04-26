from io import StringIO
from typing import Optional

import pandas as pd


def read_profile(uploaded_file) -> Optional[pd.DataFrame]:
    if uploaded_file is None:
        return None

    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        raw = uploaded_file.getvalue().decode("utf-8")
        df = pd.read_csv(StringIO(raw), sep=r"\s+", header=None)

    lowered = {c.lower().strip(): c for c in df.columns}
    if "x" in lowered and "y" in lowered:
        out = df[[lowered["x"], lowered["y"]]].copy()
        out.columns = ["x", "y"]
    elif df.shape[1] >= 2:
        out = df.iloc[:, :2].copy()
        out.columns = ["x", "y"]
    else:
        raise ValueError("Profile file must contain at least two columns for x and y.")

    out["x"] = pd.to_numeric(out["x"], errors="coerce")
    out["y"] = pd.to_numeric(out["y"], errors="coerce")
    out = out.dropna().sort_values("x").reset_index(drop=True)

    if len(out) < 2:
        raise ValueError("Profile file must contain at least two valid points.")

    return out