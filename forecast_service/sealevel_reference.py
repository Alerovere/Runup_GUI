"""Fixed historical Copernicus SSH reference, prepared once per site/cell/year."""
import calendar
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

DATASET_ID='cmems_mod_med_phy-ssh_anfc_4.2km-2D_PT1H-m'


def _time(value):
    value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def validate_reference(reference, *, location=None, dataset_id=None, selected_point=None):
    if reference is None:
        return
    if reference.get('schema_version')!=1 or reference.get('kind')!='copernicus_historical_mean':
        raise ValueError('Riferimento storico del livello marino non riconosciuto.')
    year=reference['year']
    if isinstance(year,bool) or not isinstance(year,int) or not 1900<=year<=9998:
        raise ValueError('Anno del riferimento marino non valido.')
    expected=8784 if calendar.isleap(year) else 8760
    start=datetime(year,1,1,tzinfo=timezone.utc)
    if reference['n_records']!=expected or _time(reference['start'])!=start or _time(reference['end'])!=datetime(year+1,1,1,tzinfo=timezone.utc)-timedelta(hours=1):
        raise ValueError('Il riferimento deve usare un intero anno orario completo.')
    if not math.isfinite(reference['mean_ssh_m']) or reference.get('variable')!='zos' or not reference.get('dataset_version'):
        raise ValueError('Valore o provenienza del riferimento SSH non validi.')
    if reference.get('data_mode') not in ('study','demo'):
        raise ValueError('Modalità del riferimento marino non valida.')
    if reference.get('local_datum_status')!='not_validated':
        raise ValueError('La media del modello non certifica il riferimento delle quote locali.')
    for field in ('requested_point','selected_point'):
        point=reference[field]
        if not all(math.isfinite(point[key]) for key in ('latitude','longitude')):
            raise ValueError('Coordinate del riferimento marino non valide.')
    if dataset_id is not None and reference['dataset_id']!=dataset_id:
        raise ValueError('Riferimento storico e previsione usano dataset SSH diversi: ricalcolare il riferimento.')
    if location is not None:
        point=location.get('sealevel_point',location['wave_point'])
        if any(abs(point[key]-reference['requested_point'][key])>1e-8 for key in ('latitude','longitude')):
            raise ValueError('Il punto del livello marino è cambiato: ricalcolare il riferimento storico per questa località.')
        if location.get('mean_reference_m') is not None and abs(location['mean_reference_m']-reference['mean_ssh_m'])>1e-9:
            raise ValueError('Media SSH e riferimento salvato nella località non coincidono.')
    if selected_point is not None and any(abs(selected_point[key]-reference['selected_point'][key])>1e-5 for key in ('latitude','longitude')):
        raise ValueError('La cella SSH prevista differisce da quella del riferimento storico: ricalcolare il riferimento.')


def build_reference(records, year, requested_point, selected_point, *, dataset_id=DATASET_ID, dataset_version,
                    data_mode='study'):
    expected=8784 if calendar.isleap(year) else 8760
    samples=sorted((_time(row['time']),float(row['ssh_m'])) for row in records)
    start=datetime(year,1,1,tzinfo=timezone.utc)
    if len(samples)!=expected or any(time!=start+timedelta(hours=i) or not math.isfinite(value) for i,(time,value) in enumerate(samples)):
        raise ValueError('SSH storica incompleta: servono tutte le ore dell’anno, senza duplicati o valori mancanti.')
    monthly={}
    for month in range(1,13):
        values=[value for time,value in samples if time.month==month]
        monthly[str(month)]={'mean_ssh_m':math.fsum(values)/len(values),'n_records':len(values)}
    canonical=json.dumps([[_iso(time),value] for time,value in samples],allow_nan=False,separators=(',',':'))
    reference={'schema_version':1,'kind':'copernicus_historical_mean','year':year,'dataset_id':dataset_id,
               'dataset_version':dataset_version,'variable':'zos','requested_point':dict(requested_point),
               'selected_point':dict(selected_point),'start':_iso(start),'end':_iso(samples[-1][0]),
               'n_records':expected,'mean_ssh_m':math.fsum(value for _,value in samples)/expected,
               'monthly':monthly,'data_mode':data_mode,'local_datum_status':'not_validated',
               'method':'Arithmetic mean of all hourly SSH values in one complete UTC calendar year; fixed for future forecasts.',
               'input_sha256':hashlib.sha256(canonical.encode()).hexdigest()}
    validate_reference(reference)
    return reference


def apply_reference(location, reference):
    result=copy.deepcopy(location)
    result.update(mean_reference_m=reference['mean_ssh_m'],sea_level_reference=copy.deepcopy(reference),
                  vertical_reference_status='provisional_model_mean')
    validate_location_reference(result)
    return result


def validate_location_reference(location, *, dataset_id=None, selected_point=None):
    reference=location.get('sea_level_reference')
    if reference is None:
        return
    if location.get('mean_reference_m') is None:
        raise ValueError('Il riferimento storico richiede la media SSH fissa nella configurazione.')
    validate_reference(reference,location=location,dataset_id=dataset_id,selected_point=selected_point)


def download_reference(location, year, username, password, *, dataset_id=DATASET_ID, dataset_version=None, cache=None):
    """Only called at site setup; no historical download in forecast updates."""
    import copernicusmarine
    import numpy as np
    import pandas as pd
    if year>=datetime.now(timezone.utc).year:
        raise ValueError('Scegliere un anno di calendario già concluso.')
    point=location.get('sealevel_point',location['wave_point'])
    cache=Path(cache) if cache else None
    key=hashlib.sha256(json.dumps([dataset_id,dataset_version,year,point],sort_keys=True).encode()).hexdigest()[:16]
    target=cache/f'ssh_reference_{year}_{key}.json' if cache else None
    if target and target.exists():
        reference=json.loads(target.read_text())
        validate_reference(reference,location=location,dataset_id=dataset_id)
        return reference
    if not username or not password:
        raise ValueError('Il calcolo storico SSH richiede le credenziali Copernicus Marine.')
    if not dataset_version:
        catalogue=copernicusmarine.describe(dataset_id=dataset_id,disable_progress_bar=True)
        dataset=next(d for product in catalogue.products for d in product.datasets if d.dataset_id==dataset_id)
        dataset_version=max(version.label for version in dataset.versions)
    start=datetime(year,1,1,tzinfo=timezone.utc)
    ds=copernicusmarine.open_dataset(dataset_id=dataset_id,dataset_version=dataset_version,variables=['zos'],
        username=username,password=password,start_datetime=_iso(start),
        end_datetime=_iso(datetime(year+1,1,1,tzinfo=timezone.utc)-timedelta(hours=1)),
        minimum_latitude=point['latitude'],maximum_latitude=point['latitude'],
        minimum_longitude=point['longitude'],maximum_longitude=point['longitude'],coordinates_selection_method='nearest')
    try:
        array=ds['zos']
        if array.attrs.get('units','m') not in ('m','metre','meter'):
            raise ValueError('La SSH storica deve essere espressa in metri.')
        for dim in list(array.dims):
            if dim!='time':
                if array.sizes[dim]!=1: raise ValueError('Selezionare una sola cella SSH.')
                array=array.isel({dim:0})
        selected={key:float(np.asarray(ds[key].values).reshape(-1)[0]) for key in ('latitude','longitude')}
        times=pd.to_datetime(ds.time.values,utc=True)
        records=[{'time':time.isoformat(),'ssh_m':float(value)} for time,value in zip(times,np.asarray(array.values).reshape(-1))]
    finally:
        ds.close()
    reference=build_reference(records,year,point,selected,dataset_id=dataset_id,dataset_version=dataset_version)
    if target:
        cache.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(reference,ensure_ascii=False,allow_nan=False,indent=2)+'\n');temporary.replace(target)
    return reference
