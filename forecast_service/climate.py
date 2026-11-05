"""Offline historical reference, reused by the two daily forecast updates."""
from bisect import bisect_right
from pathlib import Path
import csv
import hashlib
import json
import math


def build_climate(csv_path, source, *, time_column='time', hs_column='hs_m'):
    from forecast_service.pipeline import iso, parse_time, quantile
    rows = []
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            value = float(row[hs_column])
            if not math.isfinite(value) or value < 0:
                raise ValueError('La serie storica contiene Hs mancanti o negative: pulire i dati esplicitamente.')
            rows.append((parse_time(row[time_column]), value))
    rows.sort()
    if len(rows) < 2 or len({t for t,_ in rows}) != len(rows):
        raise ValueError('Servono almeno due tempi distinti, senza duplicati.')
    values = sorted(value for _,value in rows)
    annual = {}
    for time, value in rows:
        year = str(time.year)
        if year not in annual or value > annual[year]['hs_m']:
            annual[year] = {'hs_m': value, 'time': iso(time)}
    gaps = [(b[0]-a[0]).total_seconds()/3600 for a,b in zip(rows,rows[1:])]
    step = quantile(gaps, .5)
    # Irregular sampling would bias an observation-count percentile.
    if any(abs(g/step-round(g/step)) > .001 for g in gaps) or step <= 0:
        raise ValueError('Campionamento non regolare: uniformare la serie prima del confronto climatologico.')
    return {'schema_version':1, 'source':source, 'units':'m', 'start':iso(rows[0][0]), 'end':iso(rows[-1][0]),
            'n_records':len(rows), 'time_step_hours':step,
            'coverage_fraction':len(rows)/(int(round((rows[-1][0]-rows[0][0]).total_seconds()/3600/step))+1),
            'hs_sorted_m':values, 'p95_m':quantile(values,.95), 'p99_m':quantile(values,.99),
            'max_hs_m':max(values), 'annual_maxima':annual,
            'input_sha256':hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
            'method':'Empirical CDF, all seasons and directions; annual maxima are observations, not return levels.'}


def load_climate(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Il riferimento climatologico deve essere nella repository.')
    data = json.loads(path.read_text())
    values = data['hs_sorted_m']
    if data['schema_version'] != 1 or data['units'] != 'm' or not values or values != sorted(values) or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Riferimento climatologico non valido.')
    if len(values) != data['n_records']:
        raise ValueError('Conteggio della serie storica non coerente.')
    return data


def compare_waves(waves, climate):
    if not climate:
        return waves, {'status':'not_configured', 'description':'Climatologia non ancora caricata per questa località.'}
    values = climate['hs_sorted_m']
    rows = [dict(wave, hs_percentile=100*bisect_right(values,wave['hs_m'])/len(values)) for wave in waves]
    summary = {key:value for key,value in climate.items() if key != 'hs_sorted_m'}
    summary['status'] = 'available'
    summary['comparison_note'] = 'Confronto indicativo fra previsione Copernicus e serie storica; eventuali bias fra prodotti non sono corretti. Il percentile non è un periodo di ritorno.'
    return rows, summary
