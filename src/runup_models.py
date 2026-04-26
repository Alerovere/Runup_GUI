import math
from dataclasses import dataclass
from typing import Any, Callable, Dict

import numpy as np

try:
    from py_wave_runup import models
except ImportError:
    models = None


@dataclass
class RunupInputs:
    hs: float
    tp: float
    slope: float
    swl: float


MODEL_ORDER = [
    "Stockdon et al. (2006)",
    "Vousdoukas et al. (2012)",
    "Holman (1986)",
    "Nielsen (2009)",
    "Ruggiero et al. (2001)",
    "Atkinson et al. (2017)",
    "Senechal et al. (2011)",
    "Passarella et al. (2018)",
]


def validate_inputs(values: RunupInputs) -> None:
    if values.hs <= 0:
        raise ValueError("Significant wave height must be greater than 0 m.")
    if values.tp <= 0:
        raise ValueError("Wave period must be greater than 0 s.")
    if values.slope <= 0:
        raise ValueError("Beach slope must be greater than 0.")
    if values.slope >= 1:
        raise ValueError(
            "Beach slope must be entered as a decimal, for example 0.05 for 5%."
        )


def _scalar_result(value: Any) -> float:
    arr = np.asarray(value, dtype=float)
    if arr.size == 0:
        raise ValueError("Model returned no value.")
    return float(arr.reshape(-1)[0])


def fallback_runup(values: RunupInputs) -> Dict[str, float]:
    g = 9.81
    l0 = g * values.tp**2 / (2 * math.pi)
    stockdon_r2 = 1.1 * (
        0.35 * values.slope * math.sqrt(values.hs * l0)
        + 0.5 * math.sqrt(values.hs * l0 * (0.563 * values.slope**2 + 0.004))
    )
    return {"Stockdon et al. (2006)": stockdon_r2}


def compute_runup(values: RunupInputs) -> Dict[str, float]:
    validate_inputs(values)

    if models is None:
        return fallback_runup(values)

    hs = [values.hs]
    tp = [values.tp]
    beta = [values.slope]

    model_map: Dict[str, Callable[[], float]] = {
        "Stockdon et al. (2006)": lambda: _scalar_result(
            models.Stockdon2006(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Vousdoukas et al. (2012)": lambda: _scalar_result(
            models.Vousdoukas2012(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Holman (1986)": lambda: _scalar_result(
            models.Holman1986(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Nielsen (2009)": lambda: _scalar_result(
            models.Nielsen2009(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Ruggiero et al. (2001)": lambda: _scalar_result(
            models.Ruggiero2001(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Atkinson et al. (2017)": lambda: _scalar_result(
            models.Atkinson2017(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Senechal et al. (2011)": lambda: _scalar_result(
            models.Senechal2011(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Passarella et al. (2018)": lambda: _scalar_result(
            models.Passarella2018(Hs=hs, Tp=tp, beta=beta).swash
        ),
    }

    results: Dict[str, float] = {}
    for name in MODEL_ORDER:
        try:
            results[name] = model_map[name]()
        except Exception:
            results[name] = np.nan

    return results