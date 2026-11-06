"""Statistical screening of model/slope results; scientific model outputs stay raw."""
from math import isfinite
from statistics import fmean, pstdev

STATISTICS_METHOD = 'sigma_clip_3_population_v1'
STATISTICS_METADATA = {
    'method': STATISTICS_METHOD,
    'grouping': 'location_hour',
    'ensemble_unit': 'model_slope',
    'sigma_multiplier': 3,
    'sigma_ddof': 0,
    'passes': 1,
    'bounds_inclusive': True,
    'raw_csv_preserved': True,
}


def sigma_clip(values):
    """One pass, population sigma; values exactly at mean ±3σ are retained."""
    values = list(values)
    if any(not isfinite(value) for value in values):
        raise ValueError('Il filtro richiede risultati finiti.')
    if not values:
        return [], None, None
    mean = fmean(values)
    sigma = pstdev(values, mu=mean)
    included = [True] * len(values) if sigma == 0 else [abs(value-mean) <= 3*sigma for value in values]
    return included, mean, sigma
