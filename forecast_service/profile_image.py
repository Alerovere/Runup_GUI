"""Raster version of the same display-only profile used on the website."""
import math
from zoneinfo import ZoneInfo
from PIL import Image,ImageDraw
from forecast_service.time_utils import parse_time


def draw_profile(c,profile,structure_icon,dashed_line):
    d=c.draw;ink='#153e41';muted='#536c69';left,right=575,1007
    c.text('PROFILO DELLA SPIAGGIA',570,772,21,True,width=442)
    if profile['status']!='available':
        c.text('Risultati non disponibili',575,855,19,width=422,color=muted)
        c.text('Nessun profilo ricostruito',575,884,16,width=422,color=muted);return
    number=lambda value:f'{value:.2f}'.replace('.',',')
    stamp=parse_time(profile['time']).astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m %H:%M')
    c.text('Ora rappresentata: '+stamp,575,805,16,width=422,color=ink)
    away=profile.get('exposed') is False;water='#738882' if away else '#2685a5'
    if away:c.text('Onde da altre direzioni · riparo non simulato',575,827,13,width=422,color=muted)
    levels=[0,profile['mean_m'],profile['p95_m'],*[s['elevation_m'] for s in profile['structures']]]
    if profile['p995_m'] is not None:levels.append(profile['p995_m'])
    floor=min(levels);ceiling=max(.5,*levels)*1.15;shore=left+55
    def point(z):return shore+(right-shore)*min(1,max(0,z/ceiling)),984-(z-floor)/(ceiling-floor)*126
    zx,zy=point(0);_,top=point(ceiling)
    d.polygon([(zx,zy),(right,top),(right,1000),(zx,1000)],fill='#e7d9b8')
    d.line([(zx,zy),(right,top)],fill='#b8a57d',width=2)
    def waterline(z):
        ex,ey=point(z);sy=ey if z<=0 else zy
        sea=[(left+(shore-left)*i/24,sy-3-4*math.sin(i/24*4*math.pi)) for i in range(25)]
        swash=[(shore+(ex-shore)*i/40,sy+(ey-sy)*i/40-9*math.sin(math.pi*i/40)) for i in range(1,41)]
        return sea+swash
    color=tuple(int(water[i:i+2],16) for i in (1,3,5))
    overlay=Image.new('RGBA',c.image.size);paint=ImageDraw.Draw(overlay)
    for z,alpha in [(profile['p95_m'],50),(profile['mean_m'],130)]:
        points=waterline(z);closing=[(zx,zy),(left,zy+15)] if z>0 else [(shore,1000),(left,1000)]
        paint.polygon(points+closing,fill=(*color,alpha))
    c.image.paste(overlay,(0,0),overlay)
    d.line(waterline(profile['mean_m']),fill=water,width=3,joint='curve')
    dashed_line(d,[(left,zy),(right,zy)],'#9aafa4',1,dash=4,gap=6)
    if profile['p995_m'] is not None:
        end=point(profile['p995_m']);dashed_line(d,[(zx,zy),end],water,2,dash=1,gap=6)
        x,y=end;d.ellipse((x-3,y-3,x+3,y+3),fill='white',outline=water,width=1)
    for i,s in enumerate(profile['structures']):
        x,y=point(s['elevation_m']);kind='promenade' if any(word in (s['id']+' '+s['label']).lower() for word in ['passeggiat','infrastrutt','strad']) else 'kiosk'
        structure_icon(d,x-10,y-30,kind,scale=.75)
        d.ellipse((x-6,y-6,x+6,y+6),fill='white',outline=muted,width=1)
        c.text(str(i+1),x-3,y-6,10,width=12,color=ink)
    c.text('Mare',575,955,12,color=muted);c.text('Zero di riferimento',575,995,12,width=180,color=muted)
    for y,label,z,alpha in [(1017,'Media',profile['mean_m'],255),(1040,'Stime più alte (P95)',profile['p95_m'],90),(1063,'Coda (P99,5)',profile['p995_m'],255)]:
        if label.startswith('Coda'):dashed_line(d,[(578,y+8),(601,y+8)],water,2,dash=1,gap=6)
        else:d.line([(578,y+8),(601,y+8)],fill=water if alpha==255 else '#b8d9e4',width=5)
        c.text(label+': '+(number(z)+' m' if z is not None else 'non disponibile'),610,y,14,width=392,color=ink)
    for i,s in enumerate(profile['structures']):
        c.text(f"{i+1}. {s['label']} · quota {number(s['elevation_m'])} m",575,1090+i*22,14,width=432,color=ink)
    c.text('Picco della media · distanze non in scala',575,1141,13,width=432,color=muted)
    c.text('Quote: raccordo locale da validare',575,1162,13,width=432,color=muted)
