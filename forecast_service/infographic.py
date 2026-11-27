"""Offline 4:5 social cards with wave direction and total-water-level forecasts.

No forecast models, map masks, classifications or time series are modified here.
"""
from datetime import timedelta
from io import BytesIO
import json
import logging
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from forecast_service.ensemble import STATISTICS_METHOD
from forecast_service.beach_profile import profile_snapshot
from forecast_service.profile_image import draw_profile
from forecast_service.exposure import is_exposed
from forecast_service.time_utils import parse_time, iso

WIDTH, HEIGHT = 1080, 1350
ASSETS = Path(__file__).resolve().parent / 'assets'
SITE_ASSETS = Path(__file__).resolve().parents[1] / 'forecast_site/assets'
PUBLIC_URL = 'https://alerovere.github.io/Runup_GUI/'
EU_DISCLAIMER = ('Finanziato dall’Unione europea. Le opinioni espresse sono esclusivamente quelle degli autori e non riflettono necessariamente quelle dell’Unione europea o dell’Agenzia esecutiva del Consiglio europeo della ricerca (ERCEA). Né l’Unione europea né l’autorità che concede il finanziamento possono esserne ritenute responsabili.')
TZ = ZoneInfo('Europe/Rome')
COLORS = {'white':('#ffffff','#b9c7c2'), 'yellow':('#fff3c4','#cbb052'),
          'orange':('#ffdfbd','#c98b50'), 'gray':('#e5e9e8','#9ba9a4'),
          'unavailable':('#edf0ef','#bac4c1')}
INK, MUTED = '#153e41', '#536c69'


def finite(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def number(value, digits=2):
    return f'{value:.{digits}f}'.replace('.',',') if finite(value) else '—'


def percent(value):
    if not finite(value): return '—'
    if 0 < value < .001: return '<0,1%'
    if .999 < value < 1: return '>99,9%'
    return number(value*100,0 if abs(value*100-round(value*100))<1e-8 else 1)+'%'


def compass(degrees):
    if not finite(degrees): return '—'
    names='N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW'.split()
    return names[int((degrees%360)/22.5+.5)%16]


def local(value, year=False):
    dt=parse_time(value).astimezone(TZ)
    return dt.strftime('%d/%m/%Y %H:%M' if year else '%d/%m %H:%M')


def level_reference(bulletin,unit):
    meta=unit.get('sea_level_source',{})
    if bulletin['mode']=='demo':return 'riferimento sintetico dimostrativo'
    if meta.get('mode')=='noaa_tide_meteocean_surge':return 'livello medio del modello, raccordo locale provvisorio'
    if meta.get('mode')=='constant_msl':return 'livello medio mare assunto'
    ref=meta.get('historical_reference') or unit.get('sea_level_reference') or {}
    if ref.get('kind')=='copernicus_historical_mean':return 'media Copernicus '+str(ref['year'])+', raccordo locale da validare'
    return 'riferimento provvisorio del modello, da validare'


from forecast_service.reader_summary import reference_threshold, display_thresholds, row_state, day_summary


def card_data(bulletin,unit):
    start=parse_time(bulletin.get('display_from',bulletin['processing_started_at']))
    end=parse_time(bulletin['display_to']) if bulletin.get('display_to') else start+timedelta(hours=bulletin['display_hours'])
    rows=[r for r in unit['hourly'] if start<=parse_time(r['time'])<end]
    if not rows:raise ValueError('Nessun campione nel periodo dell’elaborazione.')
    valid=[r for r in rows if r.get('statistics_method')==STATISTICS_METHOD and r.get('n_estimates',0)>0 and finite(r.get('twl_p95_m'))]
    wave=max((r for r in rows if finite(r.get('hs_m'))),key=lambda r:r['hs_m'],default=None)
    twl=max(valid,key=lambda r:r['twl_p95_m'],default=None)
    groups={}
    for row in rows:groups.setdefault(parse_time(row['time']).astimezone(TZ).date(),[]).append(row)
    structures=display_thresholds(unit)
    days=[dict(date=date.isoformat(),**day_summary(unit,group),structures=[dict(id=t['id'],**day_summary(unit,group,t)) for t in structures]) for date,group in groups.items()]
    if len(days)>5:raise ValueError('La scheda 4:5 supporta al massimo cinque date nel periodo di 96 ore.')
    return dict(period_from=iso(start),period_to=iso(end),hours=len(rows),wave=wave,twl=twl,
                days=days,threshold=reference_threshold(unit),structures=structures,rows=rows,
                profile=profile_snapshot(unit,rows,structures))


class Canvas:
    def __init__(self):
        self.image=Image.new('RGB',(WIDTH,HEIGHT),'#f5f7f2')
        self.draw=ImageDraw.Draw(self.image)

    def font(self,size,bold=False):
        return ImageFont.truetype(str(ASSETS/'fonts'/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),size)

    def text(self,text,x,y,size=22,bold=False,width=984,lines=1,color=INK):
        font=self.font(size,bold);out=[];line=''
        for word in str(text).split():
            trial=(line+' '+word).strip()
            if line and self.draw.textlength(trial,font=font)>width:out.append(line);line=word
            else:line=trial
        if line:out.append(line)
        if len(out)>lines:
            out=out[:lines];out[-1]+='…'
        for line in out:
            while self.draw.textlength(line,font=font)>width and len(line)>1:line=line[:-2]+'…'
            self.draw.text((x,y),line,font=font,fill=color)
            y+=size+6
        return y

    def box(self,rect,fill='white',border='#d7dfd8',radius=18):
        self.draw.rounded_rectangle(rect,radius,fill=fill,outline=border,width=2)



def chart_points(rows, start):
    """Display samples only: use the same filtered ensemble at each hour."""
    result=[]
    for row in rows:
        valid=row.get('statistics_method')==STATISTICS_METHOD and row.get('n_estimates',0)>0
        def filtered(key):return row.get(key) if valid and finite(row.get(key)) else None
        mean=filtered('twl_mean_m')
        low,high=filtered('twl_p25_m'),filtered('twl_p75_m')
        if low is None or high is None or low>high:low=high=None
        result.append(dict(x=(parse_time(row['time'])-start).total_seconds()/3600,
            hs=row.get('hs_m') if finite(row.get('hs_m')) else None,
            tp=row.get('tp_s') if finite(row.get('tp_s')) else None,
            direction=row['direction_deg']%360 if finite(row.get('direction_deg')) and finite(row.get('hs_m')) and row['hs_m']>0 else None,
            twl=mean,low=low,high=high))
    return result


def smooth_segments(points):
    """PCHIP for drawing only; preserve knots, missing data and hourly gaps."""
    from scipy.interpolate import PchipInterpolator
    runs=[];run=[]
    for x,y in points:
        if not finite(y) or (run and not 0<x-run[-1][0]<=1.000001):
            if run:runs.append(run);run=[]
        if finite(y):run.append((x,y))
    if run:runs.append(run)
    result=[]
    for run in runs:
        if len(run)<2:result.append(run);continue
        xs,ys=zip(*run);curve=PchipInterpolator(xs,ys,extrapolate=False);dense=[]
        for i in range(len(run)-1):
            for j in range(6):
                x=xs[i]+(xs[i+1]-xs[i])*j/6
                dense.append((x,float(curve(x))))
        dense.append(run[-1]);result.append(dense)
    return result


def central_bands(points):
    """Keep P25/P75 ordered, falling back to linear in crossed intervals."""
    lower=smooth_segments([(p['x'],p['low']) for p in points])
    upper=smooth_segments([(p['x'],p['high']) for p in points]);bands=[]
    originals={p['x']:p for p in points}
    for lo,hi in zip(lower,upper):
        if len(lo)!=len(hi) or any(a[0]!=b[0] for a,b in zip(lo,hi)):continue
        band=[(a[0],a[1],b[1]) for a,b in zip(lo,hi)]
        for i in range(0,len(band)-1,6):
            if any(low>high for _,low,high in band[i:i+7]):
                first,last=originals[band[i][0]],originals[band[i+6][0]]
                for j in range(7):
                    x=band[i+j][0];t=(x-first['x'])/(last['x']-first['x'])
                    band[i+j]=(x,first['low']+(last['low']-first['low'])*t,
                               first['high']+(last['high']-first['high'])*t)
        bands.append(band)
    return bands


def dashed_line(draw,points,fill,width=3,dash=9,gap=6):
    phase=0
    for a,b in zip(points,points[1:]):
        length=math.hypot(b[0]-a[0],b[1]-a[1]);offset=0
        while offset<length:
            period=dash+gap;position=phase%period
            step=min(length-offset,(dash-position) if position<dash else period-position)
            if step<1e-8:phase+=1e-7;continue
            if position<dash:
                draw.line([(a[0]+(b[0]-a[0])*offset/length,a[1]+(b[1]-a[1])*offset/length),
                           (a[0]+(b[0]-a[0])*(offset+step)/length,a[1]+(b[1]-a[1])*(offset+step)/length)],fill=fill,width=width)
            phase+=step;offset+=step


def axis_limits(values):
    values=[v for v in values if finite(v)]
    low=min([0]+values);high=max([0]+values)
    span=max(high-low,.4);raw=span/3;power=10**math.floor(math.log10(raw))
    step=next(v*power for v in (1,2,2.5,5,10) if v*power>=raw)
    bottom=math.floor(low/step)*step;top=math.ceil((high+span*.02)/step)*step
    return bottom,max(top,bottom+step),step


def draw_forecast_charts(c,data,unit):
    start=parse_time(data['period_from']);duration=(parse_time(data['period_to'])-start).total_seconds()/3600
    points=chart_points(data['rows'],start);d=c.draw
    ticks=[]
    # One date per local midnight avoids crowded labels in the two narrow panels.
    for h in range(math.ceil(duration)+1):
        dt=(start+timedelta(hours=h)).astimezone(TZ)
        if dt.hour==0:ticks.append((h,dt))
    def x_position(x,left):return left+362*x/duration
    def axis(values,left,top,bottom,right_axis=False):
        minimum,maximum,step=axis_limits(values);right=left+362
        yp=lambda value:bottom-(bottom-top)*(value-minimum)/(maximum-minimum)
        for i in range(round((maximum-minimum)/step)+1):
            value=minimum+i*step;y=yp(value)
            if not right_axis:d.line([(left,y),(right,y)],fill='#e0e7e1',width=1)
            label=number(value,2).rstrip('0').rstrip(',')
            c.text(label,right+8 if right_axis else left-40,y-9,14,width=42,color=MUTED)
        if not right_axis:
            for x,_ in ticks:d.line([(x_position(x,left),top),(x_position(x,left),bottom)],fill='#e4e9e4',width=1)
        return yp
    def line(key,left,yp,color,width=3,dashed=False,fill=None,base=None):
        for run in smooth_segments([(p['x'],p[key]) for p in points]):
            coords=[(x_position(x,left),yp(y)) for x,y in run]
            if len(coords)==1:
                x,y=coords[0];d.ellipse((x-2,y-2,x+2,y+2),fill=color);continue
            if fill:d.polygon([(coords[0][0],yp(base)),*coords,(coords[-1][0],yp(base))],fill=fill)
            if dashed:dashed_line(d,coords,color,width)
            else:d.line(coords,fill=color,width=width,joint='curve')
    def legend(x,y,label,color,dashed=False):
        if dashed:dashed_line(d,[(x,y+10),(x+24,y+10)],color,3)
        else:d.line([(x,y+10),(x+24,y+10)],fill=color,width=3)
        c.text(label,x+31,y,16,width=200,color=INK)
    c.box((48,757,530,1191));c.box((550,757,1032,1191))
    c.text('ONDE PREVISTE',68,772,22,True,width=442)
    legend(76,811,'Altezza (m)','#3e7194');legend(290,811,'Periodo (s)','#b66b35',True)
    hs_y=axis([p['hs'] for p in points],110,858,995)
    tp_y=axis([p['tp'] for p in points],110,858,995,True)
    line('hs',110,hs_y,'#3e7194',4,fill='#eaf2f8',base=0)
    line('tp',110,tp_y,'#b66b35',3,True)
    if not any(p['hs'] is not None or p['tp'] is not None for p in points):c.text('Dati non disponibili',148,912,19,width=330,color=MUTED)
    c.text('m',83,836,14,color=MUTED);c.text('s',489,836,14,color=MUTED)
    c.text('Provenienza delle onde (da)',76,1018,17,True,width=420)
    for deg,label in ((0,'N'),(90,'E'),(180,'S'),(270,'W'),(360,'N')):
        y=1049+deg/360*76
        d.line([(110,y),(472,y)],fill='#e4e9e4',width=1)
        c.text(label,84,y-8,12,width=24,color=MUTED)
    for x,_ in ticks:d.line([(x_position(x,110),1049),(x_position(x,110),1125)],fill='#e4e9e4',width=1)
    available_direction=False
    for point in points:
        if point['direction'] is None:continue
        available_direction=True
        exposed=is_exposed(point['direction'],unit.get('wave_exposure'))
        color='#498b66' if exposed is False else '#ba6b37' if exposed is True else '#9ba9a4'
        x=x_position(point['x'],110);y=1049+point['direction']/360*76
        d.ellipse((x-2,y-2,x+2,y+2),fill=color)
    if not available_direction:c.text('Direzione non disponibile',146,1075,18,width=340,color=MUTED)
    for x,label,color in ((78,'Altre direzioni','#498b66'),(237,'Verso costa','#ba6b37'),(382,'Non definita','#9ba9a4')):
        d.ellipse((x,1168,x+7,1175),fill=color);c.text(label,x+14,1161,13,width=137,color=MUTED)
    for x,dt in ticks:c.text(dt.strftime('%d/%m'),x_position(x,110)-22,1138,14,width=55,color=MUTED)
    draw_profile(c,data['profile'],structure_icon,dashed_line)



def structure_icon(draw,x,y,kind,color=INK,scale=1):
    """Simple kiosk / promenade pictograms, with a text legend on the card."""
    def line(points,width=2):draw.line([(x+a*scale,y+b*scale) for a,b in points],fill=color,width=max(1,round(width*scale)))
    if kind=='kiosk':
        line([(0,10),(12,1),(24,10),(0,10)]);line([(4,10),(4,25),(20,25),(20,10)])
        line([(0,26),(24,26)]);line([(8,15),(16,15),(16,25)])
    else:
        line([(0,26),(26,26)]);line([(0,8),(26,8)]);line([(0,16),(26,16)])
        for col in (3,13,23):line([(col,3),(col,24)])


def render_card(bulletin,parent,unit,output,*,slug,unit_id):
    data=card_data(bulletin,unit);c=Canvas();d=c.draw
    c.text('ondeariva',48,28,32,True)
    c.box((764,24,1032,124),'#fff0d9','#dfbf96',12)
    d.polygon([(780,54),(792,30),(804,54)],fill='#b16d24');c.text('!',789,35,15,True,width=10,color='white')
    c.text('Attenzione',817,33,17,True,width=198,color='#75451f')
    c.text('Non usare per previsioni, allerte o decisioni gestionali.',781,65,16,width=234,lines=3,color='#75451f')
    c.text(parent['name'],48,82,34,True,width=672,lines=2)
    if unit is not parent:c.text(unit['name'],48,162,23,width=672,lines=2)
    c.text('Elaborazione '+local(bulletin['generated_at'],True)+' · ora italiana',48,222,18,color=MUTED)
    c.text('Periodo: '+local(data['period_from'])+' → '+local(data['period_to'])+' · '+str(bulletin['display_hours'])+' ore',48,249,18,color=MUTED)
    c.box((48,286,530,446));c.box((550,286,1032,446))
    wave,twl=data['wave'],data['twl']
    c.text('ONDE AL LARGO · Hs MASSIMA',68,300,20,True,width=440)
    c.text(number(wave.get('hs_m') if wave else None)+' m',68,328,48,True,width=440)
    c.text(('Tp '+number(wave.get('tp_s'),1)+' s · da '+compass(wave.get('direction_deg'))) if wave else 'Dati non disponibili',68,390,24,width=440)
    c.text(local(wave['time']) if wave else '—',68,423,16,color=MUTED)
    c.text('ACQUA SULLA SPIAGGIA · TWL ALTO',570,300,19,True,width=440)
    c.text(number(twl.get('twl_p95_m') if twl else None)+' m',570,328,48,True,width=440)
    c.text('Onde + livello del mare',570,390,23,width=440)
    c.text(local(twl['time']) if twl else 'Dati non disponibili',570,423,16,color=MUTED)
    c.text('GIORNO PER GIORNO',48,472,23,True,width=984)
    c.text('Risultati dei modelli sopra la quota delle strutture indicate',48,507,20,width=984,lines=1,color=MUTED)
    c.text('Confronto tra quote, non probabilità di allagamento',48,534,17,width=984,color=MUTED)
    structures=data['structures']
    for j,t in enumerate(structures):
        x=48+j*490;kind='promenade' if 'passeggiat' in str(t).lower() or t['id']=='infrastrutture_fisse' else 'kiosk'
        structure_icon(d,x,551,kind,scale=.8)
        c.text(t.get('short_label') or t.get('description') or t['id'],x+32,551,19,True,width=440)
    weekdays=['lun','mar','mer','gio','ven','sab','dom'];n=max(1,len(data['days']));gap=12;w=(984-gap*(n-1))//n
    for i,day in enumerate(data['days']):
        x=48+i*(w+gap);c.box((x,589,x+w,718),'white','#ced9d2',12)
        dt=parse_time(day['date']+'T12:00:00Z');label=weekdays[dt.weekday()]+' '+dt.strftime('%d/%m')
        c.text(label+(' *' if day['partial'] else ''),x+10,597,18,True,width=w-20)
        for j,(t,result) in enumerate(zip(structures,day['structures'])):
            y=630+j*40;color,border=COLORS[result['key']]
            c.box((x+7,y-1,x+w-7,y+34),color,border,7)
            kind='promenade' if 'passeggiat' in str(t).lower() or t['id']=='infrastrutture_fisse' else 'kiosk'
            structure_icon(d,x+15,y+2,kind,scale=.8)
            c.text(percent(result['fraction']),x+48,y,24,True,width=w-64)
    c.text('* Giornata parziale · — onde da altre direzioni o dati non valutabili · Le percentuali non sono probabilità.',48,728,14,color=MUTED)
    draw_forecast_charts(c,data,unit)
    c.text('Dati: '+('dimostrativi' if bulletin['mode']=='demo' else 'MeteOcean – UniGE (onde e surge) · NOAA (marea)' if bulletin['mode']=='meteocean' else 'Copernicus Marine'),48,1203,15,color=MUTED)
    # Official funding artwork, with proportions and wording preserved.
    logo=SITE_ASSETS/'eu-erc-horizon-europe.png'
    if logo.exists():
        with Image.open(logo) as raw:
            art=raw.convert('RGBA');art.thumbnail((244,105),Image.Resampling.LANCZOS)
            c.image.paste(art,(48,1224),art)
    c.text('MARINA · ERC · Grant 101334860',318,1225,19,True,width=714)
    c.text('alerovere.github.io/Runup_GUI/',318,1255,21,True,width=714)
    c.text(EU_DISCLAIMER,318,1288,11,width=714,lines=3,color=MUTED)
    if bulletin['mode']=='demo':c.text('DATI DIMOSTRATIVI',330,39,17,True,color='#9c5024')
    info=dict(schema_version=4,slug=slug,unit_id=unit_id,generated_at=bulletin['generated_at'],
              period_from=data['period_from'],period_to=data['period_to'],hours=data['hours'],
              content='wave_beach_profile_forecast',map_statistic=None,
              charts=dict(layout='side_by_side',interpolation='pchip_display_only',wave_fields=['hs_m','tp_s','direction_deg'],
                  direction_interpolation='none',direction_convention='nautical_from_north_clockwise',
                  profile_statistic='twl_mean_m',profile_upper='twl_p95_m',profile_tail='twl_p995_m'),
              profile=data['profile'],
              wave_peak_time=wave['time'] if wave else None,twl_peak_time=twl['time'] if twl else None,
              daily=data['days'],structures=[dict(id=t['id'],label=t.get('short_label'),elevation_m=t['elevation_m']) for t in data['structures']],
              vertical_reference=level_reference(bulletin,unit),twl_statistic='twl_p95_m',funding_disclaimer=EU_DISCLAIMER,
              url=PUBLIC_URL+'?localita='+slug+('&settore='+unit_id if unit_id!='whole' else ''),
              disclaimer='Elaborazione sperimentale. Non usare per previsioni, allerte o decisioni gestionali.')
    png_info=PngImagePlugin.PngInfo();png_info.add_text('Onde-a-riva',json.dumps(info,ensure_ascii=False))
    stream=BytesIO();c.image.save(stream,format='PNG',pnginfo=png_info,optimize=True)
    return stream.getvalue(),info


def write_cards(bulletin,output,root=None):
    """One immutable PNG per sector, or per whole location without sectors."""
    output=Path(output)
    stamp=parse_time(bulletin['generated_at']).strftime('%Y%m%dT%H%M%SZ')
    for slug,parent in bulletin['locations'].items():
        for unit_id,unit in (parent.get('sectors') or {'whole':parent}).items():
            try:
                if not all(re.fullmatch(r'[a-z0-9-]+',s) for s in (slug,unit_id)):raise ValueError('Identificativo non valido.')
                raw,info=render_card(bulletin,parent,unit,output,slug=slug,unit_id=unit_id)
                filename=f'{slug}--{unit_id}-{stamp}.png';destination=output/'social'/filename
                destination.parent.mkdir(parents=True,exist_ok=True)
                temp=destination.with_suffix('.png.tmp');temp.write_bytes(raw);temp.replace(destination)
                unit['social_card']=dict(status='available',url='data/social/'+filename,filename=filename,
                    width=WIDTH,height=HEIGHT,generated_at=bulletin['generated_at'],period_from=info['period_from'],
                    period_to=info['period_to'],map_statistic=info['map_statistic'])
            except Exception as error:
                logging.getLogger(__name__).warning('Infografica %s/%s non disponibile: %s',slug,unit_id,error,exc_info=True)
                unit['social_card']=dict(status='unavailable',reason=str(error))
