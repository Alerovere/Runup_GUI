"""Daily Borghetto bulletin delivery; no forecast calculations or stored secrets.

Only the explicit CLI --send path can contact Telegram. Receipts live in Actions
artifacts outside Pages, contain no credentials, and key a UTC day/channel/sector.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4
import zipfile
from zoneinfo import ZoneInfo

from forecast_service.ensemble import STATISTICS_METHOD
from forecast_service.reader_summary import bulletin_summary, summary_lines, change_text
from forecast_service.time_utils import parse_time, iso
from forecast_service.research_notice import RESEARCH_NOTICE, DISCLAIMER_URL

LOCATION='borghetto-santo-spirito'
PUBLIC_URL='https://alerovere.github.io/Runup_GUI/'
STATE_ARTIFACT='telegram-borghetto-state-v1'
STATE_LIMIT=64*1024
WARNING=RESEARCH_NOTICE


class DeliveryError(Exception):
    def __init__(self,message,*,uncertain=False):
        super().__init__(message);self.uncertain=uncertain


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def prepare_deliveries(bulletin,data_dir,*,now):
    """Validate every selected sector before any message is sent."""
    if bulletin.get('mode') not in ('meteocean','copernicus'):
        raise ValueError('Telegram accetta soltanto elaborazioni reali; demo esclusa.')
    generated=parse_time(bulletin['generated_at']);start=parse_time(bulletin['display_from']);end=parse_time(bulletin['display_to'])
    if not -timedelta(minutes=5)<=now-generated<=timedelta(hours=6):
        raise ValueError('Elaborazione troppo vecchia o data futura: nessun invio.')
    if bulletin.get('display_hours')!=96 or end-start!=timedelta(hours=96) or not start<=now<end:
        raise ValueError('Il bollettino deve coprire 96 ore e includere il momento di invio.')
    parent=bulletin.get('locations',{}).get(LOCATION)
    if not parent:raise ValueError('Borghetto non presente nel bollettino.')
    data_dir=Path(data_dir).resolve();deliveries=[]
    for sector,unit in (parent.get('sectors') or {'whole':parent}).items():
        if not re.fullmatch('[a-z0-9-]+',sector):raise ValueError('Identificativo settore non valido.')
        rows=[r for r in unit.get('hourly',[]) if start<=parse_time(r['time'])<end]
        if len(rows)!=96 or any(parse_time(r['time'])!=start+timedelta(hours=i) or
            r.get('statistics_method')!=STATISTICS_METHOD or not finite(r.get('n_estimates')) or r['n_estimates']<=0 or
            not all(finite(r.get(k)) and r[k]>=0 for k in ('hs_m','tp_s')) or not finite(r.get('twl_mean_m')) for i,r in enumerate(rows)):
            raise ValueError('Copertura o risultati non validi per un settore: nessun invio.')
        card=unit.get('social_card') or {}
        expected=rf'data/social/{LOCATION}--{sector}-\d{{8}}T\d{{6}}Z\.png'
        if card.get('status')!='available' or card.get('width')!=1080 or card.get('height')!=1350 or card.get('generated_at')!=bulletin['generated_at'] or not re.fullmatch(expected,str(card.get('url',''))):
            raise ValueError('Infografica assente o non coerente con questa elaborazione.')
        if parse_time(card['period_from'])!=start or parse_time(card['period_to'])!=end:
            raise ValueError('Il periodo dell’infografica non coincide con il bollettino.')
        image=(data_dir/card['url'].removeprefix('data/')).resolve()
        if not image.is_relative_to(data_dir) or not image.is_file() or not 24<=image.stat().st_size<=5*1024*1024:
            raise ValueError('File PNG non disponibile o non valido.')
        with image.open('rb') as stream:header=stream.read(24)
        if header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR' or struct.unpack('>II',header[16:24])!=(1080,1350):
            raise ValueError('Formato o dimensioni dell’infografica non validi.')
        def local(value):return parse_time(value).astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y %H:%M %Z')
        name=str(unit.get('name',sector))[:160]
        summary=bulletin_summary(unit,rows)
        caption=(f'🌊 Borghetto Santo Spirito — elaborazione di ricerca giornaliera\n📍 {name}\n\n'
                 +'\n'.join(summary_lines(summary))+ '\nStime dei modelli × pendenze, non probabilità di allagamento.\n\n'
                 +f'Elaborazione: {local(generated)}\nPeriodo: {local(start)} → {local(end)}\n\n⚠️ {WARNING}')
        if len(caption)>1024:raise ValueError('Didascalia troppo lunga.')
        url=PUBLIC_URL+'?localita='+LOCATION+('&settore='+sector if sector!='whole' else '')
        buttons={'inline_keyboard':[[{'text':'Apri l’ultima elaborazione','url':url}],
                                    [{'text':'Avvertenze e condizioni d’uso','url':DISCLAIMER_URL}]]}
        deliveries.append(dict(sector=sector,name=name,image=image,caption=caption,buttons=buttons,day=generated.date().isoformat(),generated_at=iso(generated),summary=summary))
    if not deliveries:raise ValueError('Nessun settore da inviare.')
    return deliveries


def empty_state():return dict(schema_version=1,entries={})


def decode_state(raw):
    if len(raw)>STATE_LIMIT:raise ValueError('Registro Telegram troppo grande.')
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('schema_version')!=1 or not isinstance(data.get('entries'),dict):
        raise ValueError('Registro Telegram non valido.')
    for key,value in data['entries'].items():
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}/[a-f0-9]{24}/[a-z0-9-]+',key) or not isinstance(value,dict) or value.get('status') not in ('sent','pending','failed'):
            raise ValueError('Voce del registro Telegram non valida.')
    return data


def write_state(path,state):
    path=Path(path);raw=json.dumps(state,ensure_ascii=False,allow_nan=False,sort_keys=True)
    if len(raw.encode())>STATE_LIMIT:raise ValueError('Registro Telegram troppo grande.')
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(raw,encoding='utf-8');temp.replace(path)


def gh_api(endpoint):
    """gh handles authenticated GitHub redirects; tokens never enter arguments/logs."""
    try:
        result=subprocess.run(['gh','api','--hostname','github.com',endpoint],check=True,capture_output=True,timeout=45)
        return result.stdout
    except (OSError,subprocess.SubprocessError):
        raise DeliveryError('Impossibile recuperare il registro da GitHub; invio sospeso per evitare duplicati.') from None


def restore_state(repository,repository_id,branch,*,api=gh_api):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Repository non valido.')
    result=json.loads(api(f'repos/{repository}/actions/artifacts?name={STATE_ARTIFACT}&per_page=100'))
    # Only receipts from this repository's real forecast workflow/default branch.
    for artifact in sorted(result.get('artifacts',[]),key=lambda a:a['id'],reverse=True):
        run=artifact.get('workflow_run') or {}
        if artifact.get('name')!=STATE_ARTIFACT or artifact.get('expired') or run.get('head_repository_id')!=int(repository_id) or run.get('head_branch')!=branch:continue
        details=json.loads(api(f'repos/{repository}/actions/runs/{int(run["id"])}'))
        if details.get('path')!='.github/workflows/local-forecast.yml' or details.get('event') not in ('schedule','workflow_dispatch'):continue
        if artifact.get('size_in_bytes',STATE_LIMIT+1)>STATE_LIMIT:
            raise ValueError('Archivio del registro Telegram troppo grande.')
        raw=api(f'repos/{repository}/actions/artifacts/{int(artifact["id"])}/zip')
        if len(raw)>STATE_LIMIT:raise ValueError('Archivio del registro Telegram troppo grande.')
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            if archive.namelist()!=['receipt.json'] or archive.getinfo('receipt.json').file_size>STATE_LIMIT:
                raise ValueError('Archivio del registro Telegram non valido.')
            return decode_state(archive.read('receipt.json'))
    # An empty result is the expected first activation. API failures never reset state.
    if result.get('total_count',0)>100:
        raise ValueError('Nessun registro attendibile nei primi 100 risultati: verificare prima di inviare.')
    return empty_state()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None


class TelegramClient:
    def __init__(self,token,chat_id,*,open_request=None,sleep=time.sleep):
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}',token):raise ValueError('Token Telegram non valido: verificare il secret.')
        if not re.fullmatch(r'-\d+',chat_id) or int(chat_id)>=-1000000000000:raise ValueError('Chat ID del canale non valido: verificare il secret.')
        self.token=token;self.chat_id=chat_id;self.open_request=open_request or build_opener(NoRedirect()).open;self.sleep=sleep

    def send_photo(self,delivery):
        boundary='OndeARiva'+uuid4().hex;parts=[]
        fields=dict(chat_id=self.chat_id,caption=delivery['caption'],reply_markup=json.dumps(delivery['buttons'],ensure_ascii=False))
        for name,value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="bollettino.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),delivery['image'].read_bytes(),f'\r\n--{boundary}--\r\n'.encode()])
        request=Request('https://api.telegram.org/bot'+self.token+'/sendPhoto',data=b''.join(parts),headers={'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
        for attempt in range(3):
            try:
                with self.open_request(request,timeout=30) as response:result=json.loads(response.read(1024*1024))
            except HTTPError as error:
                code=error.code
                try:result=json.loads(error.read(64*1024))
                except Exception:result={}
                if not isinstance(result,dict):result={}
                if 400<=code<500:result.update(ok=False,error_code=code)
                else:raise DeliveryError('Risposta Telegram non confermata; controllare il canale prima di riprovare.',uncertain=True) from None
            except Exception:
                # Never expose exception URLs (which contain the bot token).
                raise DeliveryError('Esito Telegram non confermato; nessun nuovo tentativo automatico oggi.',uncertain=True) from None
            if not isinstance(result,dict):raise DeliveryError('Risposta Telegram non valida: controllare il canale.',uncertain=True)
            if result.get('ok') is True:
                payload=result.get('result');message=payload.get('message_id') if isinstance(payload,dict) else None
                if isinstance(message,int) and not isinstance(message,bool) and message>0:return message
                raise DeliveryError('Conferma Telegram incompleta: controllare il canale.',uncertain=True)
            code=result.get('error_code');parameters=result.get('parameters');delay=parameters.get('retry_after') if isinstance(parameters,dict) else None
            if code==429 and attempt<2 and isinstance(delay,int) and 0<delay<=30:
                self.sleep(delay+1);continue
            if isinstance(code,int) and 400<=code<500:
                raise DeliveryError(f'Telegram ha rifiutato l’invio (codice {code}): verificare token e permessi del bot.')
            raise DeliveryError('Risposta Telegram non confermata: controllare il canale.',uncertain=True)


def deliver_daily(deliveries,client,state,state_path,*,now,sleep=time.sleep):
    """Persist each receipt immediately. Pending sends require human reconciliation."""
    cutoff=(now-timedelta(days=30)).date().isoformat()
    state['entries']={k:v for k,v in state['entries'].items() if k.split('/')[0]>=cutoff}
    scope=sha256((client.chat_id+'|'+LOCATION).encode()).hexdigest()[:24]
    write_state(state_path,state);sent=skipped=uncertain=0
    for delivery in deliveries:
        key=delivery['day']+'/'+scope+'/'+delivery['sector'];old=state['entries'].get(key,{})
        if old.get('status')=='sent':skipped+=1;continue
        if old.get('status')=='pending':uncertain+=1;continue
        if sent:sleep(1.1)
        previous=[(k,v) for k,v in state['entries'].items() if k<key and k.split('/')[1:]==key.split('/')[1:] and v.get('status')=='sent' and isinstance(v.get('summary'),dict)]
        change=change_text(delivery.get('summary',{}),max(previous,key=lambda item:item[0])[1]['summary']) if previous else ''
        if change:
            candidate=delivery['caption'].replace('\n\n⚠️','\n'+change+'\n\n⚠️')
            if len(candidate)<=1024:delivery=dict(delivery,caption=candidate)
        entry=dict(status='pending',generated_at=delivery['generated_at'],updated_at=iso(now),summary={'key':delivery.get('summary',{}).get('key','unavailable')})
        state['entries'][key]=entry;write_state(state_path,state)
        try:message=client.send_photo(delivery)
        except DeliveryError as error:
            if not error.uncertain:entry['status']='failed'
            write_state(state_path,state);raise
        entry.update(status='sent',message_id=message);write_state(state_path,state);sent+=1
    return dict(sent=sent,skipped=skipped,pending=uncertain)
