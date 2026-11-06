"""Build a complete static bulletin before publishing it. No Streamlit imports."""
from __future__ import annotations

import csv
import io
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from forecast_service.ensemble import sigma_clip, STATISTICS_METHOD, STATISTICS_METADATA

from src.runup_models import MODEL_CITATIONS, MODEL_ORDER, RunupInputs, compute_runup, models

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def iso(dt):
    return dt.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def load_configuration(root=ROOT):
    locations = json.loads((root / 'config/locations.json').read_text())
    impacts = json.loads((root / 'config/impact_thresholds.json').read_text())
    if set(locations['locations']) != set(impacts['locations']):
        raise ValueError('Le località e le soglie devono avere gli stessi identificativi.')
    if not 96 <= locations['forecast_hours'] <= locations['download_hours'] <= 240:
        raise ValueError('Copertura temporale non valida.')
    level = locations['water_level']
    if level['mode'] not in ('constant_msl', 'copernicus_ssh'):
        raise ValueError('Modalità del livello marino non supportata.')
    if level['mode'] == 'constant_msl' and not math.isfinite(level['offset_m']):
        raise ValueError('Offset del livello marino non valido.')
    for slug, loc in locations['locations'].items():
        if not loc.get('name') or not loc.get('area'):
            raise ValueError(f'Nome e tratto di costa sono obbligatori: {slug}')
        for field in ('map_point','wave_point','sealevel_point'):
            if field in loc:
                point=loc[field]
                if not all(math.isfinite(point[key]) for key in ('latitude','longitude')) or not -90<=point['latitude']<=90 or not -180<=point['longitude']<=180:
                    raise ValueError(f'Coordinate non valide in {field}: {slug}')
        if not loc['slopes'] or any(not math.isfinite(s) or not 0 < s < 1 for s in loc['slopes']):
            raise ValueError(f'Pendenze non valide: {slug}')
        if len(set(loc['slopes'])) != len(loc['slopes']):
            raise ValueError(f'Pendenze duplicate: {slug}')
        if not math.isfinite(loc['roughness_m']) or loc['roughness_m'] < 0:
            raise ValueError(f'Rugosità non valida: {slug}')
        if not math.isfinite(loc.get('datum_offset_m', 0)):
            raise ValueError(f'Correzione delle quote non valida: {slug}')
        if loc.get('mean_reference_m') is not None and not math.isfinite(loc['mean_reference_m']):
            raise ValueError(f'Riferimento medio non valido: {slug}')
        from forecast_service.sealevel_reference import validate_location_reference
        validate_location_reference(loc,dataset_id=level.get('dataset_id'))
        from forecast_service.exposure import validate_exposure
        validate_exposure(loc.get('wave_exposure'))
        point = loc['wave_point']
        if not 30 <= point['latitude'] <= 46.5 or not -18.2 <= point['longitude'] <= 37:
            raise ValueError(f'Punto fuori dal Mediterraneo: {slug}')
        thresholds = impacts['locations'][slug]['thresholds']
        ids=[t['id'] for t in thresholds]
        if len(set(ids)) != len(ids):
            raise ValueError(f'Identificativi soglia duplicati: {slug}')
        heights = [t['elevation_m'] for t in thresholds]
        if not heights or any(not math.isfinite(h) for h in heights) or heights != sorted(set(heights)):
            raise ValueError(f'Soglie non valide: {slug}')
        if any(t['season'] not in ('summer', 'all_year') for t in thresholds):
            raise ValueError(f'Stagionalità non valida: {slug}')
    for loc in locations['locations'].values():
        season = loc.get('summer_season', impacts['summer_season'])
        dates = [season['start_month_day'], season['end_month_day']]
        if any(dates) and not all(dates):
            raise ValueError('Definire sia inizio sia fine della stagione estiva.')
        for date in filter(None, dates):
            datetime.strptime('2000-' + date, '%Y-%m-%d')
    return locations, impacts


def seasonal_activity(threshold, instant, season):
    """None means seasonal applicability is unknown, never silently active/inactive."""
    if threshold['season'] == 'all_year':
        return True
    start, end = season['start_month_day'], season['end_month_day']
    if not start or not end:
        return None
    from zoneinfo import ZoneInfo
    day = parse_time(instant).astimezone(ZoneInfo('Europe/Rome')).strftime('%m-%d')
    return start <= day <= end if start <= end else day >= start or day <= end


def quantile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize_records(waves, location, thresholds, season, eta):
    """Use the existing model wrapper unchanged; preserve every valid model/slope."""
    hourly, detail = [], []
    for wave in waves:
        eta_value = wave.get('water_level_m', eta)
        if not math.isfinite(eta_value):
            raise ValueError('Livello marino mancante: il TWL non può essere calcolato.')
        values = []
        detail_start = len(detail)
        if wave['hs_m'] > 0 and wave['tp_s'] > 0:
            for slope in location['slopes']:
                results = compute_runup(RunupInputs(wave['hs_m'], wave['tp_s'], slope, eta_value, location['roughness_m']))
                for name, runup in results.items():
                    if not math.isfinite(float(runup)):
                        continue
                    twl = float(runup) + eta_value
                    if not math.isfinite(twl):
                        continue
                    values.append(twl)
                    detail.append({'time': wave['time'], 'slope': slope, 'model': name,
                                   'hs_m': wave['hs_m'], 'tp_s': wave['tp_s'], 'direction_deg': wave['direction_deg'],
                                   'water_level_m': eta_value, 'runup_m': float(runup), 'twl_m': twl,
                                   'ssh_m': wave.get('ssh_m'), 'mean_reference_m': wave.get('mean_reference_m')})
        included, filter_mean, filter_sigma = sigma_clip(values)
        for record, keep in zip(detail[detail_start:], included):
            record['included_in_summary'] = keep
        raw_count = len(values)
        values = [value for value, keep in zip(values, included) if keep]
        row = dict(wave, water_level_m=eta_value, n_estimates=len(values),
                   n_estimates_raw=raw_count, n_outliers=raw_count-len(values),
                   statistics_method=STATISTICS_METHOD,
                   filter_mean_m=filter_mean, filter_sigma_m=filter_sigma,
                   twl_min_m=None, twl_mean_m=None, twl_max_m=None,
                   twl_p05_m=None, twl_p25_m=None, twl_p75_m=None, twl_p95_m=None)
        if values:
            row.update(twl_min_m=min(values), twl_mean_m=sum(values)/len(values), twl_max_m=max(values),
                       **{f'twl_p{int(q*100):02d}_m': quantile(values, q) for q in [.05, .25, .75, .95]})
        row['thresholds'] = [{
            'id': threshold['id'],
            'active': seasonal_activity(threshold, wave['time'], season),
            'fraction': sum(v > threshold['elevation_m'] for v in values) / len(values) if values else None,
        } for threshold in thresholds]
        hourly.append(row)
    if not detail:
        raise ValueError('Nessun modello ha restituito risultati validi.')
    return hourly, detail


def wave_cycle_reference(dataset, start):
    """Only explicit, plausible cycle metadata; never infer from download time."""
    import numpy as np
    import pandas as pd
    candidates=[]
    if 'forecast_reference_time' in dataset.coords:
        values=np.unique(np.asarray(dataset.coords['forecast_reference_time'].values).reshape(-1))
        if len(values)==1:
            candidates.append((values[0],'coordinate:forecast_reference_time'))
    for key in ('forecast_reference_time','forecast_reference_datetime'):
        value=dataset.attrs.get(key)
        if isinstance(value,str) and ('T' in value or ' ' in value):
            candidates.append((value,'attribute:'+key))
    for value,source in candidates:
        try:
            reference=parse_time(pd.Timestamp(value).isoformat())
            if start-timedelta(days=10)<=reference<=start:
                return {'forecast_reference_time':iso(reference),'forecast_reference_time_source':source}
        except (ValueError,TypeError,OverflowError):
            continue
    # bulletin_date on the rolling archive can describe its first file (2023),
    # rather than the current forecast cycle, and is intentionally not used.
    return {}


def fetch_copernicus(location, dataset_id, start, hours):
    import copernicusmarine
    import numpy as np
    import pandas as pd

    username = os.environ.get('COPERNICUSMARINE_USERNAME')
    password = os.environ.get('COPERNICUSMARINE_PASSWORD')
    if not username or not password:
        raise ValueError('Configurare i due secrets COPERNICUSMARINE_USERNAME e COPERNICUSMARINE_PASSWORD.')
    point = location['wave_point']
    ds = copernicusmarine.open_dataset(
        dataset_id=dataset_id, variables=['VHM0', 'VTPK', 'VMDR'],
        minimum_longitude=point['longitude'], maximum_longitude=point['longitude'],
        minimum_latitude=point['latitude'], maximum_latitude=point['latitude'],
        start_datetime=iso(start), end_datetime=iso(start + timedelta(hours=hours)),
        coordinates_selection_method='nearest',
        username=username, password=password,
    )
    try:
        columns = {}
        for key, variable in [('hs_m', 'VHM0'), ('tp_s', 'VTPK'), ('direction_deg', 'VMDR')]:
            array = ds[variable]
            for dim in list(array.dims):
                if dim != 'time':
                    if array.sizes[dim] != 1:
                        raise ValueError('La selezione Copernicus non è un punto singolo.')
                    array = array.isel({dim: 0})
            columns[key] = np.asarray(array.values, dtype=float).reshape(-1)
        times = [parse_time(t.isoformat()) for t in pd.to_datetime(ds['time'].values, utc=True)]
        records = [dict(time=iso(time), **{k: float(v[i]) for k, v in columns.items()})
                   for i, time in enumerate(times) if start <= time < start + timedelta(hours=hours)]
        expected = {iso(start + timedelta(hours=i)) for i in range(hours)}
        if len(records) != hours or {r['time'] for r in records} != expected:
            raise ValueError(f'Copertura Copernicus incompleta: richieste {hours} ore contigue.')
        if any(not all(math.isfinite(r[k]) for k in columns) for r in records):
            raise ValueError('Valori mancanti al punto offshore: controllare la cella marina.')
        for row in records:
            row['direction_deg'] %= 360
        metadata = {'dataset_id': dataset_id, 'variables': ['VHM0', 'VTPK', 'VMDR'],
                    'downloaded_at': iso(datetime.now(UTC)), 'requested_point': point,
                    'selected_point': {key: float(ds[key].values.reshape(-1)[0])
                                       for key in ('latitude', 'longitude') if key in ds.coords}}
        metadata.update(wave_cycle_reference(ds,start))
        if 'forecast_reference_time' not in metadata:
            from forecast_service.wave_cycle import verified_native_cycle
            metadata.update(verified_native_cycle(dataset_id, records, metadata['selected_point']))
        return sorted(records, key=lambda r: r['time']), metadata
    finally:
        ds.close()


def demonstration_waves(location, start, hours):
    phase = 0.8 if location['name'] == 'Venezia' else 0
    waves = []
    for hour in range(hours):
        pulse = math.exp(-((hour - 39) / 15) ** 2)
        hs = .55 + 1.2*pulse + .18*(1 + math.sin(hour/8 + phase))
        waves.append({'time': iso(start + timedelta(hours=hour)), 'hs_m': hs,
                      'tp_s': 5 + 2*pulse + .4*math.sin(hour/11), 'direction_deg': (135 + 30*math.sin(hour/17 + phase)) % 360})
    return waves, {'dataset_id': None, 'description': 'Onde sintetiche per verificare il portale; non sono previsioni.'}


def build_bulletin(*, root=ROOT, demo=False, now=None, fetcher=None, sealevel_fetcher=None):
    from forecast_service.sealevel import align_sealevel, fetch_sealevel, demonstration_sealevel
    from forecast_service.climate import load_climate, compare_waves
    locations, impacts = load_configuration(root)
    if not demo and models is None:
        raise RuntimeError('py-wave-runup non disponibile: pubblicazione reale interrotta, senza fallback silenzioso.')
    controlled_time = now is not None
    now = parse_time(now) if controlled_time else datetime.now(UTC)
    start = now.replace(minute=0, second=0, microsecond=0)
    bulletin = {'schema_version': 1, 'mode': 'demo' if demo else 'copernicus', 'generated_at': iso(now),
                'processing_started_at': iso(now),
                'ensemble_statistics': dict(STATISTICS_METADATA),
                'wave_model': {'publication_hours_utc':[6,20],
                               'schedule_status':'nominal_expected',
                               'schedule_source':'https://documentation.marine.copernicus.eu/PUM/CMEMS-MED-PUM-006-017.pdf'},
                'display_hours': locations['forecast_hours'], 'timezone': 'Europe/Rome',
                'water_level': locations['water_level'], 'vertical_reference': impacts['vertical_reference'],
                'thresholds_status': impacts['thresholds_status'], 'summer_season': impacts['summer_season'],
                'model_backend': 'py-wave-runup' if models is not None else 'Stockdon fallback',
                'citations': MODEL_CITATIONS, 'model_order': MODEL_ORDER,
                'source': {'product_id': 'MEDSEA_ANALYSISFORECAST_WAV_006_017', 'doi': '10.48670/mds-00373',
                           'attribution': 'Generated using E.U. Copernicus Marine Service Information.'},
                'locations': {}}
    csvs = {}
    for slug, location in locations['locations'].items():
        if demo:
            waves, metadata = demonstration_waves(location, start, locations['download_hours'])
        else:
            if (location.get('sea_level_reference') or {}).get('data_mode')=='demo':
                raise ValueError('Riferimento SSH dimostrativo: pubblicazione reale interrotta.')
            waves, metadata = (fetcher or fetch_copernicus)(location, locations['dataset_id'], start, locations['download_hours'])
        if locations['water_level']['mode'] == 'copernicus_ssh':
            if demo:
                levels, reference, level_meta = demonstration_sealevel(location, waves)
            else:
                levels, reference, level_meta = (sealevel_fetcher or fetch_sealevel)(location, locations['water_level'], start, locations['download_hours'])
            waves = align_sealevel(waves, levels, reference, location.get('datum_offset_m', 0))
        else:
            level_meta = {'mode':'constant_msl', 'offset_m':locations['water_level']['offset_m']}
        climate = load_climate(root, location['climatology_file']) if location.get('climatology_file') else None
        waves, climate_summary = compare_waves(waves, climate)
        thresholds = impacts['locations'][slug]['thresholds']
        season = location.get('summer_season', impacts['summer_season'])
        hourly, detail = summarize_records(waves, location, thresholds, season, locations['water_level'].get('offset_m', 0))
        valid_models = [name for name in MODEL_ORDER if any(row['model'] == name for row in detail)]
        bulletin['locations'][slug] = dict(location, thresholds=thresholds, hourly=hourly, source=metadata,
                                         sea_level_source=level_meta, climatology=climate_summary, summer_season=season,
                                         valid_from=waves[0]['time'], valid_to=iso(parse_time(waves[-1]['time']) + timedelta(hours=1)),
                                         valid_models=valid_models, missing_models=[m for m in MODEL_ORDER if m not in valid_models],
                                         csv=f'data/{slug}.csv')
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=['data_mode', 'vertical_reference', *detail[0].keys()])
        writer.writeheader()
        reference_code = ('synthetic_reference' if demo else
            'mean_sea_level_assumed' if locations['water_level']['mode']!='copernicus_ssh' else
            f"copernicus_mean_{location['sea_level_reference']['year']}_provisional" if location.get('sea_level_reference') else
            'fixed_reference_provisional' if location.get('mean_reference_m') is not None else
            'model_mdt_provisional' if locations['water_level']['mode']=='copernicus_ssh' else 'mean_sea_level_assumed')
        for row in detail:
            writer.writerow(dict(row, data_mode=bulletin['mode'], vertical_reference=reference_code))
        csvs[f'{slug}.csv'] = output.getvalue()
    if not controlled_time:
        bulletin['generated_at'] = iso(datetime.now(UTC))
    # Fail before writing any published data if serialization finds NaN or Infinity.
    json.dumps(bulletin, allow_nan=False)
    return bulletin, csvs


def write_bulletin(bulletin, csvs, output):
    """Caller builds in an unpublished directory; deployment is one complete artifact."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for filename, contents in csvs.items():
        (output / filename).write_text(contents, encoding='utf-8')
    temp = output / 'forecast.json.tmp'
    temp.write_text(json.dumps(bulletin, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temp.replace(output / 'forecast.json')
