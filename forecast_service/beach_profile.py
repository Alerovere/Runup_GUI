"""Read-only snapshot for a schematic beach profile, never a mapped transect.

One common hour for levels and structure percentages: the greatest filtered
hourly mean in the supplied period. P99.5 illustrates the screened upper tail;
it never controls impact categories or replaces direct exceedance counts.
"""
from forecast_service.ensemble import STATISTICS_METHOD
from forecast_service.exposure import is_exposed
from forecast_service.reader_summary import finite, reference_threshold, row_state


def profile_snapshot(unit, rows, thresholds=None):
    valid=[r for r in rows if r.get('statistics_method')==STATISTICS_METHOD
           and finite(r.get('n_estimates')) and r['n_estimates']>0
           and finite(r.get('twl_mean_m')) and finite(r.get('twl_p95_m'))]
    if not valid:
        return dict(status='unavailable',reason='Nessun risultato filtrato valido nelle ore selezionate.',structures=[])
    peak=max(valid,key=lambda r:r['twl_mean_m'])
    tail=peak.get('twl_p995_m')
    if not finite(tail) or tail<peak['twl_p95_m']:tail=None
    state,rank,_=row_state(unit,peak,reference_threshold(unit))
    key=['white','yellow','orange'][rank] if state=='numeric' else 'gray' if state=='nonfrontal' else 'unavailable'
    assets=[]
    for threshold in (unit.get('thresholds',[]) if thresholds is None else thresholds):
        condition,_,fraction=row_state(unit,peak,threshold)
        if condition!='numeric' or fraction is None or not 0<=fraction<=1:fraction=None
        sample=next((t for t in peak.get('thresholds',[]) if t['id']==threshold['id']),{})
        assets.append(dict(id=threshold['id'],label=threshold.get('short_label') or threshold.get('description') or threshold['id'],
            elevation_m=threshold['elevation_m'],state=condition,fraction=fraction,
            count=round(fraction*peak['n_estimates']) if fraction is not None else None,
            season_unconfirmed=sample.get('active') is None))
    return dict(status='available',selection='peak_of_filtered_mean',time=peak['time'],
        mean_m=peak['twl_mean_m'],p95_m=peak['twl_p95_m'],p995_m=tail,
        n_estimates=peak['n_estimates'],direction_deg=peak.get('direction_deg'),
        exposed=is_exposed(peak.get('direction_deg'),unit.get('wave_exposure')) if finite(peak.get('hs_m')) and peak['hs_m']>0 else None,
        state=state,key=key,
        structures=assets,schematic=True,horizontal_distances_to_scale=False)
