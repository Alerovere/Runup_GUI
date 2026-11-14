"""Reproducible slope sensitivity samples, prepared once from measured transects.

These weights describe a chosen representation of beach variability, not the
probability of a forecast, an empirical model, or an inundation event.
"""
import hashlib
import json
import math
from statistics import NormalDist

import numpy as np


METHODS = ('measured', 'linear_range', 'truncated_normal')


def _digest(values):
    return hashlib.sha256(json.dumps(values, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _source(values):
    values = list(values)
    if not values or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 < v < 1 for v in values):
        raise ValueError('Servono pendenze misurate finite, comprese fra 0 e 1.')
    return sorted(float(v) for v in values)


def sample_slopes(source, *, method='measured', count=200, seed=42, unit_id='whole'):
    """Fit underlying normal μ/σ (population std), truncate, then sample by CDF.

    Keep repeated measured observations when fitting the distribution. A single
    transect or zero variance produces one fixed slope, never invented spread.
    """
    values = _source(source)
    if method not in METHODS or isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 2000:
        raise ValueError('Metodo di campionamento o numero di campioni non valido (2–2000).')
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32 or not isinstance(unit_id, str) or not unit_id:
        raise ValueError('Seme casuale o identificativo del settore non valido.')
    lo, hi = values[0], values[-1]
    mean, std = float(np.mean(values)), float(np.std(values, ddof=0))
    if method == 'measured' or lo == hi:
        samples = sorted(set(values))
    elif method == 'linear_range':
        samples = np.linspace(lo, hi, count).tolist()
    else:
        distribution = NormalDist(mean, std)
        lower, upper = distribution.cdf(lo), distribution.cdf(hi)
        # Stable sector-specific stream: unrelated sector order cannot change it.
        salt = int.from_bytes(hashlib.sha256(unit_id.encode()).digest()[:8], 'little')
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, salt])))
        probabilities = rng.uniform(lower, upper, count)
        samples = sorted(set(distribution.inv_cdf(float(p)) for p in probabilities))
        if any(not lo <= value <= hi for value in samples):
            raise ValueError('Campioni fuori dai limiti misurati: controllare la precisione delle pendenze.')
    metadata = dict(sampling_version=1, rng='PCG64', method=method, requested_count=count, effective_count=len(samples), seed=seed, unit_id=unit_id,
        source_count=len(values), source_min=lo, source_max=hi, source_mean=mean, source_std=std,
        std_ddof=0, degenerate=lo == hi, source_sha256=_digest(values), samples_sha256=_digest(samples),
        interpretation='Sensibilità alla variabilità delle pendenze; non probabilità di allagamento o affidabilità dei modelli.')
    return samples, metadata


def validate_sampling(samples, metadata, source, *, unit_id):
    """Reject stale or edited samples after changing transect assignments."""
    values = _source(source)
    checked = _source(samples)
    if not isinstance(metadata, dict):
        raise ValueError('Metadati del campionamento delle pendenze mancanti.')
    count, seed = metadata.get('requested_count'), metadata.get('seed')
    valid_options = (metadata.get('sampling_version')==1 and metadata.get('rng')=='PCG64' and
        metadata.get('method') in METHODS and isinstance(count,int) and not isinstance(count,bool) and 2<=count<=2000 and
        isinstance(seed,int) and not isinstance(seed,bool) and 0<=seed<2**32)
    stats = dict(source_min=values[0],source_max=values[-1],source_mean=float(np.mean(values)),source_std=float(np.std(values,ddof=0)))
    valid_stats = all(isinstance(metadata.get(key),(int,float)) and math.isfinite(metadata[key]) and
        math.isclose(metadata[key],value,rel_tol=1e-12,abs_tol=1e-15) for key,value in stats.items())
    valid = (valid_options and valid_stats and metadata.get('unit_id')==unit_id and metadata.get('std_ddof')==0 and
        metadata.get('source_sha256')==_digest(values) and metadata.get('source_count')==len(values) and
        metadata.get('samples_sha256')==_digest(checked) and metadata.get('effective_count')==len(checked) and
        list(samples)==checked and len(set(checked))==len(checked) and values[0]<=checked[0]<=checked[-1]<=values[-1] and
        metadata.get('degenerate')==(values[0]==values[-1]))
    if valid:
        if metadata['method']=='measured' or values[0]==values[-1]:
            valid = checked==sorted(set(values))
        elif metadata['method']=='linear_range':
            valid = len(checked)==count and np.allclose(checked,np.linspace(values[0],values[-1],count),rtol=1e-12,atol=1e-15)
        else:
            valid = 1<=len(checked)<=count
    # Do not regenerate Monte Carlo during validation: the saved realization is
    # authoritative even when Colab and production use different Python versions.
    if not valid:
        raise ValueError('Campioni delle pendenze non coerenti: rieseguire il campionamento dopo le modifiche ai transetti.')
