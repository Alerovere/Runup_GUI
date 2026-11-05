"""Beach-face slope following Stockdon_runup_soluzione.ipynb, cells 24–25.

The supplied teaching notebook defines selection and orientation. Diagnostics
reject degenerate fits; a negative slope is not converted to an absolute value.
"""
import math

BEACHFACE_METHOD_VERSION = 'stockdon_teaching_notebook_v1'


def prepare_profile(frame, *, distance_col='distance', elevation_col='SAMPLE_1',
                    x_col='X', y_col='Y', orientation='auto'):
    import numpy as np
    import pandas as pd
    if orientation not in ('auto','distance_increases_landward','distance_increases_seaward'):
        raise ValueError('Orientamento non riconosciuto.')
    spatial = x_col is not None and y_col is not None
    if (x_col is None) != (y_col is None):
        raise ValueError('Specificare entrambe le colonne X/Y oppure nessuna.')
    required=[distance_col,elevation_col]+([x_col,y_col] if spatial else [])
    missing=set(required)-set(frame.columns)
    if missing:
        raise ValueError(f'Colonne mancanti: {sorted(missing)}')
    profile=frame.copy()
    for name in required:
        profile[name]=pd.to_numeric(profile[name],errors='raise')
    dropped=int(profile[elevation_col].isna().sum())
    profile=profile.dropna(subset=[elevation_col]).sort_values(distance_col)
    if len(profile)<2 or not np.isfinite(profile[required].to_numpy(dtype=float)).all():
        raise ValueError('Servono almeno due punti con distanze, coordinate e quote finite.')
    if profile[distance_col].duplicated().any():
        raise ValueError('Distanze duplicate nel transetto: verificare il CSV.')
    sea_at_end=bool(profile[elevation_col].iloc[:10].mean()>profile[elevation_col].iloc[-10:].mean())
    ambiguous=bool(abs(profile[elevation_col].iloc[:10].mean()-profile[elevation_col].iloc[-10:].mean())<1e-12)
    flip=sea_at_end if orientation=='auto' else orientation=='distance_increases_seaward'
    if flip:
        profile=profile.iloc[::-1]
    profile=profile.reset_index(drop=True)
    if spatial:
        profile['x_mare']=np.hypot(profile[x_col]-profile[x_col].iloc[0],profile[y_col]-profile[y_col].iloc[0])
    else:
        # Compatibility with 1-D profiles: declared separately in the metadata.
        profile['x_mare']=(profile[distance_col]-profile[distance_col].iloc[0]).abs()
    profile.attrs.update(reversed=bool(flip),orientation=orientation,orientation_ambiguous=ambiguous,
                         dropped_nan_z=dropped,distance_source='euclidean_xy' if spatial else 'one_dimensional_distance')
    return profile


def fit_beachface(profile,z_min,z_max,*,elevation_col='SAMPLE_1'):
    import numpy as np
    if not math.isfinite(z_min) or not math.isfinite(z_max) or z_min>=z_max:
        raise ValueError('Definire un intervallo di quote crescente.')
    # Same sea-connected prefix and regression as pendenza_battigia in cell 25.
    above=np.where(profile[elevation_col]>z_max)[0]
    stop=int(above[0]) if len(above) else len(profile)
    selected=(profile[elevation_col]>=z_min)&(profile.index<stop)
    x=profile.loc[selected,'x_mare'].to_numpy(dtype=float)
    z=profile.loc[selected,elevation_col].to_numpy(dtype=float)
    if len(x)<2 or len(np.unique(x))<2:
        raise ValueError('Meno di due distanze distinte prima del primo punto sopra Z_MAX.')
    slope,intercept=np.polyfit(x,z,1)
    if not math.isfinite(slope) or not 0<slope<1:
        raise ValueError(f'Pendenza {slope:.6g} non valida: controllare orientamento e tratto di battigia.')
    variance=float(np.sum((z-z.mean())**2))
    r2=1-float(np.sum((z-(slope*x+intercept))**2))/variance if variance>0 else 0.0
    diagnostics={'slope':float(slope),'n_points':int(len(x)),'r_squared':r2,'fit_intercept_m':float(intercept),
                 'z_min_m':float(z_min),'z_max_m':float(z_max),'stop_index':stop,
                 'first_above_zmax_found':bool(len(above)),'selected_x_min_m':float(x.min()),
                 'selected_x_max_m':float(x.max()),'method':BEACHFACE_METHOD_VERSION,**profile.attrs}
    return diagnostics,selected


def analyze_transects(frame,z_min,z_max,*,id_col='TR_ID',distance_col='distance',elevation_col='SAMPLE_1',
                      x_col='X',y_col='Y',orientation='auto'):
    import pandas as pd
    if id_col not in frame or frame[id_col].isna().any():
        raise ValueError('Colonna identificativo assente o con valori mancanti.')
    summaries=[]; profiles={}; selections={}
    for identifier,group in frame.groupby(id_col,sort=False):
        identifier=str(identifier)
        try:
            p=prepare_profile(group,distance_col=distance_col,elevation_col=elevation_col,
                              x_col=x_col,y_col=y_col,orientation=orientation)
            summary,selected=fit_beachface(p,z_min,z_max,elevation_col=elevation_col)
            summaries.append(dict(summary,transect_id=identifier,status='valid',error=''))
            profiles[identifier]=p; selections[identifier]=selected
        except (ValueError,KeyError,TypeError) as error:
            summaries.append({'transect_id':identifier,'status':'invalid','error':str(error),'slope':None})
    return pd.DataFrame(summaries),profiles,selections


def slopes_from_transects(path,z_min,z_max):
    import pandas as pd
    frame=pd.read_csv(path)
    if {'TR_ID','distance','SAMPLE_1','X','Y'}<=set(frame):
        options={}
    elif {'transect_id','x_m','z_m'}<=set(frame):
        options=dict(id_col='transect_id',distance_col='x_m',elevation_col='z_m',x_col=None,y_col=None)
    else:
        raise ValueError('CSV QGIS: TR_ID,distance,SAMPLE_1,X,Y; oppure CSV 1-D: transect_id,x_m,z_m.')
    summary,_,_=analyze_transects(frame,z_min,z_max,**options)
    if summary.empty:
        raise ValueError('Il CSV non contiene transetti.')
    invalid=summary[summary.status!='valid']
    if not invalid.empty:
        raise ValueError('; '.join(f"{r.transect_id}: {r.error}" for r in invalid.itertuples()))
    return summary.drop(columns=['status','error']).to_dict('records')
