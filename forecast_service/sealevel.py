"""Copernicus SSH plus a fixed mean reference; never remove the forecast mean."""
import math
import os
from datetime import timedelta


def align_sealevel(waves, records, mean_reference_m, datum_offset_m=0):
    from bisect import bisect_left
    from forecast_service.pipeline import parse_time
    samples = sorted((parse_time(r['time']).timestamp(), r['ssh_m']) for r in records)
    times = [time for time, _ in samples]
    if not samples or len(set(times)) != len(times):
        raise ValueError('Serie del livello marino vuota o con tempi duplicati.')
    if not all(math.isfinite(value) for _, value in samples) or not math.isfinite(mean_reference_m):
        raise ValueError('Livello marino o riferimento medio non valido.')
    out = []
    for wave in waves:
        time = parse_time(wave['time']).timestamp()
        i = bisect_left(times, time)
        if i < len(times) and times[i] == time:
            ssh = samples[i][1]
        else:
            if i == 0 or i == len(times) or times[i]-times[i-1] > 3601:
                raise ValueError('Livello marino non allineabile: copertura incompleta o intervallo mancante.')
            a, b = samples[i-1], samples[i]
            ssh = a[1] + (b[1]-a[1])*(time-a[0])/(b[0]-a[0])
        out.append(dict(wave, ssh_m=ssh, mean_reference_m=mean_reference_m,
                        water_level_m=ssh-mean_reference_m+datum_offset_m))
    return out


def fetch_sealevel(location, settings, start, hours):
    import copernicusmarine
    import numpy as np
    import pandas as pd
    from forecast_service.pipeline import iso, parse_time
    point = location.get('sealevel_point', location['wave_point'])
    common = dict(username=os.environ['COPERNICUSMARINE_USERNAME'], password=os.environ['COPERNICUSMARINE_PASSWORD'],
                  minimum_longitude=point['longitude'], maximum_longitude=point['longitude'],
                  minimum_latitude=point['latitude'], maximum_latitude=point['latitude'],
                  coordinates_selection_method='nearest')
    ds = copernicusmarine.open_dataset(dataset_id=settings['dataset_id'], variables=['zos'],
        start_datetime=iso(start-timedelta(hours=1)), end_datetime=iso(start+timedelta(hours=hours+1)), **common)
    try:
        array = ds['zos']
        for dim in list(array.dims):
            if dim != 'time':
                if array.sizes[dim] != 1:
                    raise ValueError('La selezione del livello marino deve essere un punto.')
                array = array.isel({dim:0})
        if array.attrs.get('units', 'm') not in ('m', 'metre', 'meter'):
            raise ValueError('Il livello marino deve essere espresso in metri.')
        times = [iso(parse_time(t.isoformat())) for t in pd.to_datetime(ds['time'].values, utc=True)]
        records = [{'time': t, 'ssh_m': float(z)} for t,z in zip(times, np.asarray(array.values).reshape(-1))]
        selected = {key: float(np.asarray(ds[key].values).reshape(-1)[0]) for key in ('latitude','longitude')}
    finally:
        ds.close()
    if location.get('mean_reference_m') is not None:
        mean = float(location['mean_reference_m'])
        reference = 'fixed_local_reference'
    else:
        # The static MDT is sampled in the exact cell selected for SSH.
        static_common = dict(common, minimum_latitude=selected['latitude'], maximum_latitude=selected['latitude'],
                             minimum_longitude=selected['longitude'], maximum_longitude=selected['longitude'])
        static = copernicusmarine.open_dataset(dataset_id=settings['static_dataset_id'], variables=['mdt'], **static_common)
        try:
            if static['mdt'].attrs.get('units','m') not in ('m','meter','metre'):
                raise ValueError('La superficie media deve essere espressa in metri.')
            values = np.asarray(static['mdt'].values).reshape(-1)
            if len(values) != 1 or not np.isfinite(values[0]):
                raise ValueError('Superficie media Copernicus non disponibile nella cella selezionata.')
            if any(abs(float(np.asarray(static[key].values).reshape(-1)[0])-selected[key]) > 1e-5 for key in selected):
                raise ValueError('SSH e superficie media non appartengono alla stessa cella.')
            mean = float(values[0])
            reference = settings['static_dataset_id'] + '::mdt'
        finally:
            static.close()
    return records, mean, {'dataset_id': settings['dataset_id'], 'variable': 'zos', 'selected_point': selected,
                           'mean_reference_m': mean, 'reference_source': reference,
                           'datum_offset_m': location.get('datum_offset_m', 0.0),
                           'formula': 'zos - fixed_mean_reference + datum_offset',
                           'reference_status': location.get('vertical_reference_status', 'provisional')}


def demonstration_sealevel(location, waves):
    from forecast_service.pipeline import parse_time
    start = parse_time(waves[0]['time'])
    amplitude = .32 if location['name'] == 'Venezia' else .14
    reference = .15
    records = []
    for wave in waves:
        hour = (parse_time(wave['time'])-start).total_seconds()/3600
        tide = amplitude*math.sin(2*math.pi*hour/12.42)
        pulse = .16*math.exp(-((hour-38)/17)**2)
        records.append({'time': wave['time'], 'ssh_m': reference+tide+pulse})
    return records, reference, {'dataset_id': None, 'description': 'Livello marino sintetico; non è una previsione.',
                                'reference_source': 'synthetic', 'reference_status': 'provisional',
                                'mean_reference_m': reference, 'datum_offset_m': location.get('datum_offset_m',0)}
