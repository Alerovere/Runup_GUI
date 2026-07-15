import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

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
    r: Optional[float] = 0.001  # bed roughness [m], only used by Power et al. (2019)


MODEL_ORDER = [
    "Stockdon et al. (2006)",
    "Vousdoukas et al. (2012)",
    "Holman (1986)",
    "Nielsen (2009)",
    "Ruggiero et al. (2001)",
    "Atkinson et al. (2017)",
    "Senechal et al. (2011)",
    "Passarella et al. (2018)",
    "Beuzen et al. (2019)",
    "Power et al. (2019)",
]

# Full citation text for each model, used to build a references section wherever
# results are shown. Keyed by the same names used in MODEL_ORDER.
MODEL_CITATIONS: Dict[str, str] = {
    "Stockdon et al. (2006)": (
        "Stockdon, H. F., Holman, R. A., Howd, P. A., & Sallenger, A. H. (2006). "
        "Empirical parameterization of setup, swash, and runup. Coastal Engineering, 53(7), 573-588. "
        "https://doi.org/10.1016/j.coastaleng.2005.12.005"
    ),
    "Vousdoukas et al. (2012)": (
        "Vousdoukas, M. I., Wziatek, D., & Almeida, L. P. (2012). "
        "Coastal vulnerability assessment based on video wave run-up observations at a mesotidal, steep-sloped beach. "
        "Ocean Dynamics, 62, 123-137. https://doi.org/10.1007/s10236-011-0480-x"
    ),
    "Holman (1986)": (
        "Holman, R. A. (1986). Extreme value statistics for wave run-up on a natural beach. "
        "Coastal Engineering, 9, 527-544. https://doi.org/10.1016/0378-3839(86)90002-5"
    ),
    "Nielsen (2009)": "Nielsen, P. (2009). Coastal and Estuarine Processes. World Scientific.",
    "Ruggiero et al. (2001)": (
        "Ruggiero, P., Komar, P. D., McDougal, W. G., Marra, J. J., & Beach, R. A. (2001). "
        "Wave runup, extreme water levels and the erosion of properties backing beaches. "
        "Journal of Coastal Research, 17, 407-419."
    ),
    "Atkinson et al. (2017)": (
        "Atkinson, A. L., Power, H. E., Moura, T., Hammond, T., Callaghan, D. P., & Baldock, T. E. (2017). "
        "Assessment of runup predictions by empirical models on non-truncated beaches on the south-east Australian coast. "
        "Coastal Engineering, 119, 15-31. https://doi.org/10.1016/j.coastaleng.2016.10.001"
    ),
    "Senechal et al. (2011)": (
        "Senechal, N., Coco, G., Bryan, K. R., & Holman, R. A. (2011). "
        "Wave runup during extreme storm conditions. Journal of Geophysical Research, 116. "
        "https://doi.org/10.1029/2010JC006819"
    ),
    "Passarella et al. (2018)": (
        "Passarella, M., Goldstein, E. B., De Muro, S., & Coco, G. (2018). "
        "The use of genetic programming to develop a predictor of swash excursion on sandy beaches. "
        "Natural Hazards and Earth System Sciences, 18, 599-611. https://doi.org/10.5194/nhess-18-599-2018"
    ),
    "Beuzen et al. (2019)": (
        "Beuzen, T., Goldstein, E. B., & Splinter, K. D. (2019). "
        "Ensemble models from machine learning: an example of wave runup and coastal dune erosion. "
        "Natural Hazards and Earth System Sciences, 19, 2295-2309. https://doi.org/10.5194/nhess-19-2295-2019"
    ),
    "Power et al. (2019)": (
        "Power, H. E., Gharabaghi, B., Bonakdari, H., Robertson, B., Atkinson, A. L., & Baldock, T. E. (2019). "
        "Prediction of wave runup on beaches using Gene-Expression Programming and empirical relationships. "
        "Coastal Engineering, 144, 47-61. https://doi.org/10.1016/j.coastaleng.2018.10.006"
    ),
}


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
    roughness = [values.r if values.r is not None else 0.001]

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
        "Beuzen et al. (2019)": lambda: _scalar_result(
            models.Beuzen2019(Hs=hs, Tp=tp, beta=beta).R2
        ),
        "Power et al. (2019)": lambda: _scalar_result(
            models.Power2018(Hs=hs, Tp=tp, beta=beta, r=roughness).R2
        ),
    }

    results: Dict[str, float] = {}
    for name in MODEL_ORDER:
        try:
            results[name] = model_map[name]()
        except Exception:
            results[name] = np.nan

    return results
