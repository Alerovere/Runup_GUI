"""Directional annual-maxima Gumbel fits, prepared offline during site setup.

Directions are wave provenance, clockwise from true North. Statistical sectors
form a half-open partition and are distinct from beach exposure sectors.
"""
import calendar
import hashlib
import math
from pathlib import Path


def sector_index(direction, width_deg):
    if not isinstance(width_deg, (int, float)) or width_deg not in (30, 45, 60, 90, 120, 180, 360):
        raise ValueError('Ampiezza dei settori ammessa: 30, 45, 60, 90, 120, 180 o 360 gradi.')
    if direction is None or not math.isfinite(direction):
        return None
    return int(((direction + width_deg/2) % 360)//width_deg)


def gumbel_return_period(height, loc, scale):
    """Annual-sector exceedance recurrence, not hourly or conditional frequency."""
    if not all(math.isfinite(v) for v in (height, loc, scale)) or scale <= 0:
        raise ValueError('Parametri Gumbel non validi.')
    z=(height-loc)/scale
    if z < -700:
        return 1.0
    if z > 700:
        return None
    exceedance=-math.expm1(-math.exp(-z))
    value=1/exceedance
    return value if math.isfinite(value) else None


def fit_gumbel(annual_maxima, *, min_years=30, bootstrap_replicates=400, seed=20261105):
    import numpy as np
    from scipy.stats import gumbel_r
    if not isinstance(min_years, int) or min_years < 20:
        raise ValueError('Per questa versione usare almeno 20 anni; il valore predefinito è 30.')
    if not isinstance(bootstrap_replicates, int) or bootstrap_replicates < 100:
        raise ValueError('Servono almeno 100 repliche bootstrap.')
    values=np.asarray([row['hs_m'] for row in annual_maxima],dtype=float)
    n=len(values)
    if len({row['year'] for row in annual_maxima})!=n or not np.isfinite(values).all() or (values<0).any():
        raise ValueError('Massimi annuali non validi o anni duplicati.')
    if n < min_years:
        return {'status':'insufficient_years','n_years':n,'reason':f'Servono almeno {min_years} anni completi; ne sono disponibili {n}.'}
    if np.ptp(values)<=1e-12:
        return {'status':'constant_maxima','n_years':n,'reason':'Massimi annuali costanti: non è stimabile una scala Gumbel positiva.'}
    loc,scale=map(float,gumbel_r.fit(values))
    if not math.isfinite(loc) or not math.isfinite(scale) or scale<=0:
        raise ValueError('Il fit Gumbel non produce parametri finiti e scala positiva.')
    periods=np.unique(np.r_[np.geomspace(1.01,100,80), [float(n)] if n<=100 else []])
    central=gumbel_r.isf(1/periods,loc=loc,scale=scale)
    rng=np.random.default_rng(seed)
    boot=[]
    for _ in range(bootstrap_replicates):
        sample=rng.choice(values,size=n,replace=True)
        if np.ptp(sample)<=1e-12:
            continue
        a,b=map(float,gumbel_r.fit(sample))
        curve=gumbel_r.isf(1/periods,loc=a,scale=b)
        if b>0 and np.isfinite(curve).all():
            boot.append(curve)
    if len(boot)<.9*bootstrap_replicates:
        return {'status':'unstable_bootstrap','n_years':n,'reason':'Fit bootstrap troppo instabile per mostrare una curva con intervalli.'}
    low,high=np.quantile(boot,[.025,.975],axis=0)
    ordered=sorted(annual_maxima,key=lambda row:row['hs_m'],reverse=True)
    return {'status':'available','distribution':'gumbel_r','fit_method':'maximum_likelihood',
            'loc_m':loc,'scale_m':scale,'n_years':n,'min_years':min_years,
            'first_year':min(row['year'] for row in annual_maxima),'last_year':max(row['year'] for row in annual_maxima),
            'return_period_years':periods.tolist(),'return_level_m':central.tolist(),
            'ci95_low_m':low.tolist(),'ci95_high_m':high.tolist(),
            'bootstrap_replicates':len(boot),'bootstrap_seed':seed,
            'empirical':[dict(row,return_period_years=(n+1)/rank) for rank,row in enumerate(ordered,1)]}


def build_directional_extremes(csv_path, *, time_column='time', hs_column='hs_m', direction_column='direction_deg',
                              sector_width_deg=45, min_years=30, bootstrap_replicates=400):
    import numpy as np
    import pandas as pd
    sector_index(0,sector_width_deg)
    path=Path(csv_path)
    columns=pd.read_csv(path,nrows=0).columns
    if direction_column not in columns:
        return {'status':'not_configured','reason':f'Colonna delle direzioni {direction_column!r} assente: il fit settoriale richiede data, Hs e direzione.'}
    frame=pd.read_csv(path,usecols=[time_column,hs_column,direction_column]).rename(
        columns={time_column:'time',hs_column:'hs_m',direction_column:'direction_deg'})
    frame['time']=pd.to_datetime(frame.time,utc=True,format='mixed')
    frame=frame.sort_values('time')
    if frame.empty or frame.time.duplicated().any():
        raise ValueError('La serie degli estremi deve avere tempi distinti e non essere vuota.')
    if ((frame.time.dt.minute!=0)|(frame.time.dt.second!=0)|(frame.time.dt.microsecond!=0)).any():
        return {'status':'unsupported_sampling','reason':'Per il fit settoriale usare la serie oraria ERA5 con campioni sulle ore intere.'}
    for name in ('hs_m','direction_deg'):
        frame[name]=pd.to_numeric(frame[name],errors='coerce')
    hs_valid=np.isfinite(frame.hs_m)&(frame.hs_m>=0)
    direction_valid=np.isfinite(frame.direction_deg)&frame.direction_deg.between(0,360)
    frame['valid']=hs_valid&((frame.hs_m==0)|direction_valid)
    frame['year']=frame.time.dt.year
    width=sector_width_deg
    frame['sector']=np.floor(((frame.direction_deg+width/2)%360)/width)
    annual=[]; included=[]
    for year in range(int(frame.year.min()),int(frame.year.max())+1):
        group=frame[frame.year==year]
        expected=8784 if calendar.isleap(year) else 8760
        valid=int(group.valid.sum())
        complete=valid==expected
        annual.append({'year':year,'valid_hours':valid,'expected_hours':expected,'coverage_fraction':valid/expected,'included':complete})
        if complete:
            included.append(year)
    sectors=[]
    for index in range(round(360/width)):
        center=index*width
        sector={'id':f'sector-{index}','start_deg':(center-width/2)%360,'end_deg':(center+width/2)%360,
                'center_deg':center,'width_deg':width,'annual_maxima':[]}
        for year in included:
            group=frame[(frame.year==year)&frame.valid&(frame.hs_m>0)&(frame.sector==index)]
            if not group.empty:
                peak=group.loc[group.hs_m.idxmax()]
                sector['annual_maxima'].append({'year':year,'hs_m':float(peak.hs_m),'time':peak.time.isoformat().replace('+00:00','Z')})
        missing=sorted(set(included)-{row['year'] for row in sector['annual_maxima']})
        if missing:
            sector['fit']={'status':'years_without_sector_waves','n_years':len(sector['annual_maxima']),
                           'reason':'Alcuni anni completi non hanno onde positive da questo settore: escluderli condizionerebbe il tempo di ritorno. Fit non mostrato.',
                           'years_without_waves':missing}
        else:
            sector['fit']=fit_gumbel(sector['annual_maxima'],min_years=min_years,bootstrap_replicates=bootstrap_replicates,seed=20261105+index)
        sectors.append(sector)
    result={'schema_version':1,'status':'available','direction_convention':'from_true_north_clockwise',
            'sector_width_deg':width,'sector_boundaries':'start_inclusive_end_exclusive',
            'annual_coverage_required':1.0,'min_years':min_years,'annual_coverage':annual,
            'included_years':included,'sectors':sectors,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'method':'Annual maximum within each directional sector in each complete UTC calendar year; stationary independent annual maxima; Gumbel MLE; percentile bootstrap resampling years.',
            'sampling_note':'Only complete hourly calendar years with valid Hs and direction (direction may be missing for calm Hs=0) are used. No-event years are not silently removed.',
            'references':['https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gumbel_r.html',
                          'https://confluence.ecmwf.int/spaces/FCST/pages/111155338/What+is+the+direction+convention+for+wave+fields']}
    validate_directional_extremes(result)
    return result


def validate_directional_extremes(extremes):
    if not extremes or extremes.get('status')!='available':
        return
    width=extremes['sector_width_deg']
    sector_index(0,width)
    if extremes['schema_version']!=1 or extremes['direction_convention']!='from_true_north_clockwise':
        raise ValueError('Formato o convenzione dei settori degli estremi non riconosciuti.')
    sectors=extremes['sectors']
    if len(sectors)!=round(360/width):
        raise ValueError('La partizione dei settori degli estremi non copre tutte le direzioni.')
    for index,sector in enumerate(sectors):
        if sector['id']!=f'sector-{index}' or sector['center_deg']!=index*width or sector['width_deg']!=width:
            raise ValueError('Settori degli estremi incoerenti.')
        if sector['start_deg']!=(index*width-width/2)%360 or sector['end_deg']!=(index*width+width/2)%360:
            raise ValueError('Estremi dei settori statistici incoerenti.')
        fit=sector['fit']
        if fit['status']!='available':
            continue
        if fit['n_years']<20 or fit['n_years']!=len(sector['annual_maxima']):
            raise ValueError('Numero di anni del fit Gumbel non valido.')
        if not math.isfinite(fit['loc_m']) or not math.isfinite(fit['scale_m']) or fit['scale_m']<=0:
            raise ValueError('Parametri Gumbel non validi.')
        periods=fit['return_period_years']
        arrays=[fit[key] for key in ('return_level_m','ci95_low_m','ci95_high_m')]
        if not periods or len(set(periods))!=len(periods) or periods!=sorted(periods) or periods[0]<=1:
            raise ValueError('Tempi di ritorno della curva non validi.')
        if any(len(a)!=len(periods) or any(not math.isfinite(v) for v in a) for a in arrays):
            raise ValueError('Curve Gumbel non valide.')
        if any(a>b for a,b in zip(fit['ci95_low_m'],fit['ci95_high_m'])):
            raise ValueError('Intervalli Gumbel non validi.')


def compare_directional_extremes(waves, extremes):
    if not extremes or extremes.get('status')!='available':
        return waves
    out=[]
    for wave in waves:
        index=sector_index(wave.get('direction_deg'),extremes['sector_width_deg'])
        sector=extremes['sectors'][index] if index is not None else None
        fit=sector['fit'] if sector else None
        period=gumbel_return_period(wave['hs_m'],fit['loc_m'],fit['scale_m']) if fit and fit['status']=='available' else None
        out.append(dict(wave,wave_sector_id=sector['id'] if sector else None,hs_return_period_years=period))
    return out
