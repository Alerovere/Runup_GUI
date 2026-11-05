"""Verify the wave run against native Copernicus files, without changing forecasts.

ARCO global attributes can belong to the first file in the rolling archive.
Native forecast files retain bulletin_date (including the 00/12 UTC cycle).
Only report it when every downloaded hour and variable matches that run.
"""
from __future__ import annotations

import logging
import re
from time import monotonic
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlsplit

UTC = timezone.utc
VARIABLES = {'hs_m': 'VHM0', 'tp_s': 'VTPK', 'direction_deg': 'VMDR'}
NATIVE_NAME = re.compile(r'(?P<valid>\d{10})_h-.*-b(?P<day>\d{8})_fc(?P<hour>00|12)-sv[^/]+\.nc$')
NS = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
logger = logging.getLogger(__name__)


def utc_time(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


@lru_cache(maxsize=4)
def original_service(dataset_id):
    import copernicusmarine
    catalogue = copernicusmarine.describe(dataset_id=dataset_id, disable_progress_bar=True)
    versions = [v for p in catalogue.products for d in p.datasets
                if d.dataset_id == dataset_id for v in d.versions]
    if not versions:
        raise ValueError('Dataset originale non disponibile.')
    version = max(versions, key=lambda v: v.label)
    services = [s for part in version.parts for s in part.services if s.service_name == 'original-files']
    if len(services) != 1:
        raise ValueError('Servizio originale non univoco.')
    return services[0].uri.rstrip('/')


def list_native_files(service, records):
    import requests
    url = urlsplit(service)
    bucket, prefix = url.path.strip('/').split('/', 1)
    endpoint = f'{url.scheme}://{url.netloc}/{bucket}'
    months = sorted({utc_time(row['time']).strftime('%Y/%m') for row in records})
    result = []
    for month in months:
        params = {'list-type': '2', 'prefix': f'{prefix}/{month}/', 'max-keys': 1000}
        for page in range(4):
            response = requests.get(endpoint, params=params, timeout=20)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall('s:Contents', NS):
                key = item.findtext('s:Key', namespaces=NS)
                match = NATIVE_NAME.fullmatch(key.rsplit('/', 1)[-1]) if key else None
                if match:
                    result.append({
                        'url': endpoint + '/' + key,
                        'etag': item.findtext('s:ETag', namespaces=NS),
                        'valid': datetime.strptime(match['valid'], '%Y%m%d%H').replace(tzinfo=UTC),
                        'cycle': datetime.strptime(match['day'] + match['hour'], '%Y%m%d%H').replace(tzinfo=UTC),
                    })
            if root.findtext('s:IsTruncated', namespaces=NS) != 'true':
                break
            token = root.findtext('s:NextContinuationToken', namespaces=NS)
            if not token:
                raise ValueError('Elenco originale incompleto.')
            params['continuation-token'] = token
        else:
            raise ValueError('Elenco originale troppo ampio.')
    return result


def select_run(files, records):
    times = {utc_time(row['time']) for row in records}
    if not times:
        raise ValueError('Nessuna ora da verificare.')
    blocks = {t.replace(hour=(t.hour // 12) * 12, minute=0, second=0, microsecond=0) for t in times}
    cycles = sorted({f['cycle'] for f in files if f['cycle'] <= min(times)}, reverse=True)
    for cycle in cycles:
        matching = [f for f in files if f['cycle'] == cycle and f['valid'] in blocks]
        if len(matching) == len(blocks) and {f['valid'] for f in matching} == blocks:
            return cycle, sorted(matching, key=lambda f: f['valid'])
    raise ValueError('Nessuna corsa originale completa per tutte le ore scaricate.')


def read_native_point(entry, point):
    for attempt in range(2):
        try:
            return _read_native_point(entry, point)
        except (TimeoutError, OSError):
            if attempt:
                raise


def _read_native_point(entry, point):
    import aiohttp
    import fsspec
    import xarray as xr
    # HTTP ranges read headers and the point's compressed chunks, not a full MED grid.
    with fsspec.open(entry['url'], 'rb', block_size=1024 * 1024, cache_type='blockcache',
                     headers={'If-Match': entry['etag']},
                     client_kwargs={'trust_env': True, 'timeout': aiohttp.ClientTimeout(total=30)}) as file:
        # If-Match binds every range read to the object listed above.
        with xr.open_dataset(file, engine='h5netcdf') as ds:
            if ds.attrs.get('bulletin_type') != 'forecast':
                raise ValueError('Il file originale non è una previsione.')
            cycle = utc_time(ds.attrs.get('bulletin_date'))
            if cycle != entry['cycle']:
                raise ValueError('Data della corsa discordante tra nome e intestazione.')
            subset = ds[list(VARIABLES.values())].sel(
                latitude=point['latitude'], longitude=point['longitude'], method='nearest').load()
            selected = {key: float(subset[key].values) for key in ('latitude', 'longitude')}
            table = subset.to_dataframe().reset_index()
            records = [dict(time=utc_time(row['time'].isoformat()),
                            **{key: float(row[var]) for key, var in VARIABLES.items()})
                       for _, row in table.iterrows()]
            return cycle, selected, records


def verify_run(files, records, point, reader=read_native_point):
    import math
    cycle, selected_files = select_run(files, records)
    expected = {utc_time(row['time']): row for row in records}
    if len(expected) != len(records):
        raise ValueError('Ore scaricate duplicate.')
    verified = set()
    deadline = monotonic() + 240
    for entry in selected_files:
        if monotonic() > deadline:
            raise TimeoutError('Tempo massimo per verificare la corsa superato.')
        reference, selected, native = reader(entry, point)
        if reference != cycle or any(abs(selected[key] - point[key]) > 1e-5 for key in ('latitude', 'longitude')):
            raise ValueError('Corsa o cella marina discordante.')
        block_end = entry['valid'] + timedelta(hours=12)
        for row in native:
            time = utc_time(row['time'])
            if time not in expected or not entry['valid'] <= time < block_end:
                continue
            if time in verified:
                raise ValueError('Ora originale duplicata.')
            for key in VARIABLES:
                actual, target = row[key], expected[time][key]
                difference = abs((actual - target + 180) % 360 - 180) if key == 'direction_deg' else abs(actual - target)
                # ARCO and NetCDF decode packed floats with slightly different precision.
                if not math.isfinite(actual) or not math.isfinite(target) or difference > 1e-4:
                    raise ValueError('Dati originali diversi dall’archivio scaricato.')
            verified.add(time)
    if verified != set(expected):
        raise ValueError('Copertura originale incompleta.')
    return {
        'forecast_reference_time': cycle.isoformat().replace('+00:00', 'Z'),
        'forecast_reference_time_source': 'native:bulletin_date;all_hours_and_variables_matched',
        'forecast_reference_files': [{'url': f['url'], 'etag': f.get('etag')} for f in selected_files],
        'forecast_reference_verified_hours': len(verified),
    }


def verified_native_cycle(dataset_id, records, point):
    """Missing run metadata must not prevent publishing valid scientific results."""
    try:
        service = original_service(dataset_id)
        return verify_run(list_native_files(service, records), records, point)
    except Exception as exc:
        # No credentials or signed URLs are included in the diagnostic.
        logger.warning('Corsa onde non verificata (%s); dati di previsione conservati.', type(exc).__name__)
        return {'forecast_reference_status': 'unverified'}
