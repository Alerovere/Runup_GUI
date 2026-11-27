"""Shared reading of filtered hourly estimates; never recomputes model outputs."""
from datetime import timedelta
import math
from zoneinfo import ZoneInfo
from forecast_service.ensemble import STATISTICS_METHOD
from forecast_service.exposure import is_exposed
from forecast_service.time_utils import parse_time
TZ=ZoneInfo('Europe/Rome')
def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def reference_threshold(unit):
    thresholds=unit.get('thresholds',[])
    return next((t for t in thresholds if t['id']=='strutture_turistiche_fisse'),
                next((t for t in thresholds if t.get('season')=='all_year'),thresholds[0] if thresholds else None))


def display_thresholds(unit):
    """Prefer kiosks and promenade; retain actual per-sector IDs and elevations."""
    thresholds=unit.get('thresholds',[])
    def text(t):return ' '.join(str(t.get(k,'')) for k in ('id','short_label','description')).lower()
    kiosks=next((t for t in thresholds if 'chiosc' in text(t) or t['id']=='strutture_turistiche_fisse'),None)
    promenade=next((t for t in thresholds if 'passeggiat' in text(t) or t['id']=='infrastrutture_fisse'),None)
    chosen=[t for t in (kiosks,promenade) if t]
    return chosen or thresholds[:2]


def row_state(unit, row, threshold):
    sample=next((t for t in row.get('thresholds',[]) if threshold and t['id']==threshold['id']),None)
    if not threshold or sample is None or not row.get('n_estimates',0)>0 or not finite(sample.get('fraction')) or not all(finite(row.get(k)) for k in ('twl_p75_m','twl_p95_m')):
        return 'missing',None,None
    if row.get('statistics_method')!=STATISTICS_METHOD: return 'unfiltered',None,None
    if sample.get('active') is False: return 'inactive',None,None
    exposure=is_exposed(row.get('direction_deg'),unit.get('wave_exposure')) if finite(row.get('hs_m')) and row['hs_m']>0 else None
    if exposure is False: return 'nonfrontal',None,None
    if exposure is None: return 'unknown-direction',None,None
    rank=2 if row['twl_p75_m']>threshold['elevation_m'] else 1 if row['twl_p95_m']>threshold['elevation_m'] else 0
    return 'numeric',rank,sample['fraction']


def day_summary(unit, rows, threshold=None):
    threshold=threshold or reference_threshold(unit)
    states=[row_state(unit,r,threshold) for r in rows]
    numeric=[(state,row) for state,row in zip(states,rows) if state[0]=='numeric']
    if numeric:
        key=['white','yellow','orange'][max(s[1] for s,_ in numeric)]
        state,peak=max(numeric,key=lambda item:item[0][2])
        fraction=state[2]
    else:
        key='gray' if any(s[0]=='nonfrontal' for s in states) and not any(s[0] in ('unknown-direction','unfiltered') for s in states) else 'unavailable'
        peak=None;fraction=None
    inactive=bool(states) and all(s[0]=='inactive' for s in states)
    partial=(parse_time(rows[0]['time']).astimezone(TZ).strftime('%H:%M')!='00:00' or
             parse_time(rows[-1]['time']).astimezone(TZ).strftime('%H:%M')!='23:00' or
             any(parse_time(b['time'])-parse_time(a['time'])!=timedelta(hours=1) for a,b in zip(rows,rows[1:]))) if rows else True
    return dict(key=key,fraction=fraction,peak_time=peak['time'] if peak else None,inactive=inactive,partial=partial)


def bulletin_summary(unit,rows):
    assets=[]
    for threshold in display_thresholds(unit):
        summary=day_summary(unit,rows,threshold)
        assets.append(dict(id=threshold['id'],name=str(threshold.get('short_label') or threshold.get('description') or threshold['id'])[:40],**summary))
    wave=max((r for r in rows if finite(r.get('hs_m'))),key=lambda r:r['hs_m'],default=None)
    return dict(**day_summary(unit,rows),assets=assets,wave=wave,exposure=unit.get('wave_exposure'))

def percentage(value):
    if not finite(value):return 'non valutabile'
    if 0<value<.001:return '<0,1%'
    if .999<value<1:return '>99,9%'
    return (f'{value*100:.1f}'.rstrip('0').rstrip('.')).replace('.',',')+'%'

def change_text(current,previous):
    """Comparison of like summaries, not of identical validity periods."""
    if not isinstance(previous,dict):return ''
    ranks={'white':0,'yellow':1,'orange':2}
    a,b=current.get('key'),previous.get('key')
    if a not in ranks or b not in ranks:return 'Confronto col bollettino precedente non disponibile (direzione o dati).'
    label='stessa fascia' if a==b else 'fascia più alta' if ranks[a]>ranks[b] else 'fascia più bassa'
    return 'Rispetto al bollettino precedente: '+label+'. I periodi confrontati sono diversi.'

def summary_lines(summary):
    lines=[]
    for asset in summary['assets']:
        if asset['key']=='gray':lines.append(asset['name']+': direzione da verificare.')
        elif asset['fraction'] is not None:
            when=parse_time(asset['peak_time']).astimezone(TZ).strftime('%d/%m %H:%M')
            lines.append(asset['name']+': '+percentage(asset['fraction'])+' sopra quota'+(' · picco '+when if asset['fraction']>0 else '')+'.')
        else:lines.append(asset['name']+(': fuori stagione.' if asset['inactive'] else ': confronto non disponibile.'))
    wave=summary.get('wave')
    if wave:
        direction=wave.get('direction_deg');names='N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW'.split()
        label=names[int((direction%360)/22.5+.5)%16] if finite(direction) else 'non disponibile'
        height=f"{wave['hs_m']:.2f}".replace('.',',');when=parse_time(wave['time']).astimezone(TZ).strftime('%d/%m %H:%M')
        lines.append('Onde al largo: '+height+' m · da '+label+' · '+when+'.')
        if is_exposed(direction,summary.get('exposure')) is False:lines.append('Al picco, onde da altre direzioni: il riparo della costa non è simulato.')
    if summary['key']=='gray':lines.append('Grigio non significa condizioni sicure.')
    return lines
