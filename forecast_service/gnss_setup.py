"""Measured XYZ beach-face transects: no DEM sampling or elevation selection."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

GNSS_OLS_METHOD = 'gnss_full_beachface_ols_v1'
GNSS_ATTRIBUTE_METHOD = 'gnss_slope_attribute_v1'


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label}: serve un numero finito.')
    return float(value)


def _load(path):
    data = json.loads(Path(path).read_text())
    if data.get('type') != 'FeatureCollection' or not data.get('features'):
        raise ValueError('GNSS: serve un GeoJSON FeatureCollection non vuoto.')
    if any(f.get('type')!='Feature' or not isinstance(f.get('properties'),dict) for f in data['features']):
        raise ValueError('GNSS: elementi o attributi GeoJSON non validi.')
    return data


def inspect_gnss(path):
    """Fields for dropdowns; a declared CRS is read without silently overriding it."""
    from pyproj import CRS
    data = _load(path)
    fields = sorted({key for f in data['features'] for key in f['properties']})
    numeric = [key for key in fields if all(isinstance(f['properties'].get(key),(int,float)) and
        not isinstance(f['properties'][key],bool) and math.isfinite(f['properties'][key]) for f in data['features'])]
    declared = data.get('crs',{}).get('properties',{}).get('name')
    return dict(fields=fields,numeric_fields=numeric,count=len(data['features']),
        crs=CRS.from_user_input(declared).to_string() if declared else 'EPSG:4326',
        crs_declared=bool(declared),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def extract_gnss_profiles(path, *, geojson_crs, profile_crs='EPSG:32632', id_field='transect_id',
                          slope_field=None, r2_field=None, z_correction_m=0.):
    """Preserve every measured XYZ vertex. Transform XY only, never GNSS Z."""
    import pandas as pd
    from pyproj import CRS, Transformer
    data = _load(path)
    source = CRS.from_user_input(geojson_crs)
    target = CRS.from_user_input(profile_crs)
    if not target.is_projected or not all(abs(a.unit_conversion_factor-1)<1e-9 for a in target.axis_info[:2]):
        raise ValueError('GNSS: il CRS dei profili deve essere proiettato in metri.')
    declared = data.get('crs',{}).get('properties',{}).get('name')
    if declared and not source.equals(CRS.from_user_input(declared),ignore_axis_order=True):
        raise ValueError('Il CRS dichiarato nel GeoJSON GNSS differisce da quello selezionato.')
    correction = _number(z_correction_m,'Correzione quote GNSS')
    converter = Transformer.from_crs(source.to_2d(),target.to_2d(),always_xy=True)
    records, diagnostics, references = [], [], {}
    for feature in data['features']:
        props = feature['properties']; identifier = props.get(id_field)
        if isinstance(identifier,bool) or identifier is None or not str(identifier).strip():
            raise ValueError(f'GNSS: identificativo assente nel campo {id_field}.')
        key = str(identifier)
        if key in references:
            raise ValueError(f'GNSS: identificativo duplicato {key}.')
        geometry = feature.get('geometry') or {}
        if geometry.get('type') != 'LineString':
            raise ValueError(f'GNSS {key}: serve una LineString XYZ, una per transetto.')
        vertices = np.asarray(geometry.get('coordinates'),dtype=float)
        if vertices.ndim!=2 or vertices.shape[0]<2 or vertices.shape[1]<3 or not np.isfinite(vertices[:,:3]).all():
            raise ValueError(f'GNSS {key}: servono almeno due vertici XYZ con quote finite in metri.')
        if len(vertices)>100000 or len(records)+len(vertices)>1000000:
            raise ValueError('GNSS: troppi punti nel file.')
        x,y = converter.transform(vertices[:,0],vertices[:,1])
        xy = np.column_stack([x,y])
        if not np.isfinite(xy).all():
            raise ValueError(f'GNSS {key}: coordinate trasformate non valide; verificare il CRS.')
        distances = np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        if distances[-1]<=0 or (np.diff(distances)<=0).any():
            raise ValueError(f'GNSS {key}: punti consecutivi coincidenti o lunghezza nulla.')
        reference = {}
        if slope_field:
            beta = _number(props.get(slope_field),f'GNSS {key}, campo {slope_field}')
            if not 0<beta<1:raise ValueError(f'GNSS {key}: la pendenza nel campo {slope_field} deve essere fra 0 e 1 (m/m).')
            reference['provided_slope'] = beta
        if r2_field:
            r2 = _number(props.get(r2_field),f'GNSS {key}, campo {r2_field}')
            if not 0<=r2<=1:raise ValueError(f'GNSS {key}: R² nel campo {r2_field} deve essere fra 0 e 1.')
            reference['provided_r_squared'] = r2
        references[key] = reference
        for distance,(px,py),pz in zip(distances,xy,vertices[:,2]):
            records.append(dict(TR_ID=key,distance=float(distance),X=float(px),Y=float(py),SAMPLE_1=float(pz)+correction))
        chord = float(np.linalg.norm(xy[-1]-xy[0]))
        diagnostics.append(dict(transect_id=key,n_points=len(vertices),missing_z=0,length_m=float(distances[-1]),
            curved_profile=chord==0 or distances[-1]>chord*1.01,**reference))
    metadata = dict(method='gnss_measured_xyz_v1',transects_source_name=Path(path).name,
        transects_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),geojson_crs=source.to_string(),
        profile_crs=target.to_string(),id_field=id_field,slope_field=slope_field,r2_field=r2_field,
        z_source='geometry_xyz',z_correction_m=correction,z_units='m',references=references)
    return pd.DataFrame(records),pd.DataFrame(diagnostics),metadata


def analyze_gnss_transects(frame, *, references=None, slope_source='xyz', orientation='auto'):
    """Fit all measured vertices against Euclidean XY distance from the sea end.

    Short GNSS profiles use non-overlapping end groups for orientation, unlike
    the DEM teaching workflow whose first/last 10-point rule stays unchanged.
    An optional supplied beta is an explicit alternative, never mixed silently.
    """
    import pandas as pd
    if slope_source not in ('xyz','attribute') or orientation not in ('auto','distance_increases_landward','distance_increases_seaward'):
        raise ValueError('Sorgente pendenza o orientamento GNSS non valido.')
    summaries,profiles,selections = [],{},{}
    references = references or {}
    for key,group in frame.groupby('TR_ID',sort=False):
        key = str(key)
        try:
            p = group.sort_values('distance').copy()
            if len(p)<2 or not np.isfinite(p[['distance','X','Y','SAMPLE_1']].to_numpy(dtype=float)).all():
                raise ValueError('Servono almeno due punti GNSS con coordinate e quote finite.')
            edge = min(10,max(1,len(p)//2))
            difference = float(p.SAMPLE_1.iloc[:edge].mean()-p.SAMPLE_1.iloc[-edge:].mean())
            flip = difference>0 if orientation=='auto' else orientation=='distance_increases_seaward'
            if flip:p=p.iloc[::-1]
            p=p.reset_index(drop=True)
            p['x_mare']=np.hypot(p.X-p.X.iloc[0],p.Y-p.Y.iloc[0])
            x,z = p.x_mare.to_numpy(),p.SAMPLE_1.to_numpy()
            if len(np.unique(x))<2:raise ValueError('Servono almeno due distanze GNSS distinte.')
            fitted, fitted_intercept = np.polyfit(x,z,1)
            reference = references.get(key,{})
            if slope_source=='attribute' and 'provided_slope' not in reference:
                raise ValueError('Selezionare un campo pendenza per usare i valori forniti.')
            beta = float(fitted) if slope_source=='xyz' else float(reference['provided_slope'])
            if not math.isfinite(beta) or not 0<beta<1:raise ValueError('Pendenza GNSS non valida; verificare i punti e l’orientamento mare–terra.')
            intercept = float(fitted_intercept) if slope_source=='xyz' else float(z.mean()-beta*x.mean())
            variance = float(np.sum((z-z.mean())**2))
            r2 = 1-float(np.sum((z-(beta*x+intercept))**2))/variance if variance>0 else 0.
            attrs = dict(reversed=bool(flip),orientation=orientation,orientation_ambiguous=abs(difference)<1e-12,
                dropped_nan_z=0,distance_source='euclidean_xy')
            p.attrs.update(attrs)
            summary = dict(transect_id=key,status='valid',error='',slope=beta,n_points=len(p),r_squared=r2,
                fit_intercept_m=intercept,z_min_m=None,z_max_m=None,stop_index=len(p),first_above_zmax_found=False,
                selected_x_min_m=float(x.min()),selected_x_max_m=float(x.max()),
                method=GNSS_OLS_METHOD if slope_source=='xyz' else GNSS_ATTRIBUTE_METHOD,**attrs,**reference)
            if 'provided_slope' in reference:summary['slope_difference_from_field']=beta-reference['provided_slope']
            summaries.append(summary);profiles[key]=p;selections[key]=pd.Series(True,index=p.index)
        except (ValueError,KeyError,TypeError) as error:
            summaries.append(dict(transect_id=key,status='invalid',error=str(error),slope=None))
    return pd.DataFrame(summaries),profiles,selections


def gnss_map_profiles(dem_path,transects_path,profiles,*,profile_crs,geojson_crs,id_field):
    """DEM-only coastal starts, oriented using GNSS, independent of GNSS datum.

    The dense DEM samples are for map seeds only; never feed them back to the
    GNSS fit, sector assignment, or Monte Carlo source slopes.
    """
    from forecast_service.geospatial_setup import extract_dem_profiles
    from forecast_service.site_setup import prepare_profile
    sampled,report,metadata = extract_dem_profiles(dem_path,transects_path,profile_crs=profile_crs,
        geojson_crs=geojson_crs,id_field=id_field)
    prepared = {}
    for key,p in profiles.items():
        prepared[key] = prepare_profile(sampled[sampled.TR_ID==key],orientation=
            'distance_increases_seaward' if p.attrs['reversed'] else 'distance_increases_landward')
        # The coastal search follows the ordered line, including bends. Using
        # Euclidean radius here would admit a later return leg into the prefix.
        # This column is only for map seeds, never the GNSS slope regression.
        prepared[key]['x_mare'] = (prepared[key]['distance']-prepared[key]['distance'].iloc[0]).abs()
        prepared[key].attrs['distance_source'] = 'along_line_map_seeds_only'
    return prepared,report,metadata
