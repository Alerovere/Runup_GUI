"""ERA5 adapter based on wave_climate/download.py, Alessio Rovere (MIT, 2026).

Keep request caching, NetCDF/ZIP handling, nearest sea cell and adaptive chunks.
Only waves are needed here. Mean period is never renamed to peak period.
See LICENSE-wave-climate.txt for the upstream license.
"""
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
import zipfile

ERA5_TS = 'reanalysis-era5-single-levels-timeseries'
VARIABLES = ['significant_height_of_combined_wind_waves_and_swell', 'mean_wave_period', 'mean_wave_direction']
SHORT = {'swh':'hs_m', 'mwp':'tm_s', 'mwd':'direction_deg',
         'significant_height_of_combined_wind_waves_and_swell':'hs_m',
         'mean_wave_period':'tm_s', 'mean_wave_direction':'direction_deg'}


class TooLarge(Exception):
    pass


def cds_client():
    import cdsapi
    key = os.environ.get('CDS_KEY')
    if key:
        return cdsapi.Client(url=os.environ.get('CDS_URL','https://cds.climate.copernicus.eu/api'),key=key,quiet=True)
    return cdsapi.Client(quiet=True)  # Also supports the user's standard ~/.cdsapirc.


def open_cds(path):
    import xarray as xr
    if zipfile.is_zipfile(path):
        frames = []
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith('.nc'):
                    with xr.open_dataset(io.BytesIO(archive.read(name))) as ds:
                        frames.append(ds.load())
        if not frames:
            raise ValueError('Archivio CDS senza file NetCDF.')
        return xr.merge(frames,compat='override')
    with xr.open_dataset(path) as ds:
        return ds.load()


def ts_frame(ds):
    import pandas as pd
    df=ds.to_dataframe().reset_index()
    tcol='valid_time' if 'valid_time' in df else 'time'
    keep={v:SHORT[v] for v in ds.data_vars if v in SHORT}
    if 'hs_m' not in keep.values():
        raise ValueError('La risposta CDS non contiene Hs.')
    out=df[[tcol,*keep,*[c for c in ('latitude','longitude') if c in df]]].rename(columns={tcol:'time',**keep})
    out['time']=pd.to_datetime(out['time'],utc=True)
    return out


def cached_fetch(client, dataset, request, cache, retries=3):
    cache=Path(cache); cache.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(json.dumps({'dataset':dataset,**request},sort_keys=True).encode()).hexdigest()[:16]
    path=cache/f'era5_{key}.nc'
    if path.exists():
        return path
    partial=path.with_suffix('.part')
    for attempt in range(retries):
        try:
            client.retrieve(dataset,request,str(partial))
            ds=open_cds(partial)
            try:
                ts_frame(ds)
            finally:
                ds.close()
            partial.replace(path)
            return path
        except Exception as error:
            partial.unlink(missing_ok=True)
            message=str(error).lower()
            if any(word in message for word in ('too large','cost limit','request too big')):
                raise TooLarge() from error
            if attempt==retries-1:
                raise
            time.sleep(30*(attempt+1))


def ts_range(client, lon, lat, start, end, cache, retries=3):
    request={'variable':sorted(VARIABLES),'location':{'longitude':round(lon,4),'latitude':round(lat,4)},
             'date':[f'{start.isoformat()}/{end.isoformat()}'],'data_format':'netcdf'}
    try:
        return [cached_fetch(client,ERA5_TS,request,cache,retries)]
    except TooLarge:
        if (end-start).days<=31:
            raise ValueError('Richiesta CDS troppo grande anche dopo la suddivisione.')
        middle=start+dt.timedelta(days=(end-start).days//2)
        return ts_range(client,lon,lat,start,middle,cache,retries)+ts_range(client,lon,lat,middle+dt.timedelta(days=1),end,cache,retries)


def nearest_sea_cell(client, lon, lat, cache, search_deg=.75):
    # CDS time-series accepts a location. Use the gridded product for the area
    # probe, instead of sending the upstream script's area to the point service.
    request={'product_type':['reanalysis'],'variable':[VARIABLES[0]],'year':['2020'],'month':['01'],
             'day':['01'],'time':[f'{h:02d}:00' for h in range(24)],
             'area':[lat+search_deg,lon-search_deg,lat-search_deg,lon+search_deg],
             'data_format':'netcdf','download_format':'unarchived'}
    ds=open_cds(cached_fetch(client,'reanalysis-era5-single-levels',request,cache))
    try:
        frame=ts_frame(ds)
    finally:
        ds.close()
    cells=frame.groupby(['latitude','longitude'])['hs_m'].apply(lambda v:v.notna().mean()).reset_index()
    cells=cells[cells.hs_m>.9]
    if cells.empty:
        raise ValueError('Nessuna cella marina ERA5 vicina: scegliere un punto più al largo.')
    delta=((cells.longitude-lon+180)%360)-180
    distance=(delta*math.cos(math.radians(lat)))**2+(cells.latitude-lat)**2
    cell=cells.loc[distance.idxmin()]
    return float((cell.longitude+180)%360-180),float(cell.latitude)


def year_chunks(start,end,years=10):
    if end<start or years<1:
        raise ValueError('Periodo ERA5 non valido.')
    chunks=[]
    current=start
    while current<=end:
        stop=min(dt.date(current.year+years-1,12,31),end)
        chunks.append((current,stop))
        current=stop+dt.timedelta(days=1)
    return chunks


def download_series(location, start, end, cache, *, client=None, cell=None):
    import pandas as pd
    if end>dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=6):
        raise ValueError('Usare una data finale almeno sei giorni prima di oggi per ERA5.')
    client=client or cds_client()
    point=location['wave_point']
    lon,lat=cell or nearest_sea_cell(client,point['longitude'],point['latitude'],cache)
    frames=[]
    for a,b in year_chunks(start,end):
        print(f'ERA5 {a} → {b}, cella {lat:.2f} N {lon:.2f} E (cache delle richieste attiva)')
        for path in ts_range(client,lon,lat,a,b,cache):
            ds=open_cds(path)
            try:
                frames.append(ts_frame(ds))
            finally:
                ds.close()
    frame=pd.concat(frames).drop_duplicates('time',keep='last').sort_values('time')
    frame=frame[(frame.time>=pd.Timestamp(start,tz='UTC')) & (frame.time<pd.Timestamp(end+dt.timedelta(days=1),tz='UTC'))]
    # Reject mixed cells: a local reference must represent one known marine cell.
    if any(c in frame and frame[c].nunique(dropna=True)>1 for c in ('latitude','longitude')):
        raise ValueError('Il CDS ha restituito più celle per la serie puntuale.')
    requested_count=(end-start).days*24+24
    valid=frame['hs_m'].notna()
    info={'dataset_id':ERA5_TS,'doi':'10.24381/1cf1ad76','cell_lon':lon,'cell_lat':lat,
          'requested_start':str(start),'requested_end':str(end),'requested_hours':requested_count,
          'returned_records':len(frame),'valid_hs_records':int(valid.sum()),
          'missing_hs_records':requested_count-int(valid.sum()),
          'period_type':'mean_wave_period_not_peak','downloaded_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    if not valid.any():
        raise ValueError('La cella ERA5 non contiene altezze d’onda valide.')
    return frame,info
