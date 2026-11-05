"""Helpers for a local onboarding wizard; no remote services are invoked."""
import csv
import math


def slopes_from_transects(path, z_min, z_max):
    import numpy as np
    if not math.isfinite(z_min) or not math.isfinite(z_max) or z_min >= z_max:
        raise ValueError('Definire un intervallo di quote crescente per il tratto di spiaggia.')
    groups={}
    with open(path,encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle)
        if not {'transect_id','x_m','z_m'}<=set(reader.fieldnames or []):
            raise ValueError('Il CSV richiede transect_id,x_m,z_m; distanze e quote in metri.')
        for row in reader:
            x,z=float(row['x_m']),float(row['z_m'])
            if not math.isfinite(x) or not math.isfinite(z):
                raise ValueError('Il profilo contiene valori non finiti.')
            if z_min<=z<=z_max:
                groups.setdefault(row['transect_id'],[]).append((x,z))
    result=[]
    for name,points in groups.items():
        if len(points)<3 or len({x for x,_ in points})!=len(points):
            raise ValueError(f'Transetto {name}: almeno tre ascisse distinte nel tratto selezionato.')
        x,z=np.array(points).T
        slope,intercept=np.polyfit(x,z,1)
        denominator=float(np.sum((z-z.mean())**2))
        r2=1-float(np.sum((z-(slope*x+intercept))**2))/denominator if denominator>0 else 0
        if not 0<abs(slope)<1:
            raise ValueError(f'Pendenza non fisica o nulla nel transetto {name}.')
        result.append({'transect_id':name,'slope':float(abs(slope)),'n_points':len(points),'r_squared':r2,
                       'z_min_m':z_min,'z_max_m':z_max})
    if not result:
        raise ValueError('Nessun punto nell’intervallo di quote richiesto.')
    return result
