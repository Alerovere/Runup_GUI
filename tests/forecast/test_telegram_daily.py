from copy import deepcopy
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
import zipfile

from forecast_service import telegram_daily as t
from forecast_service.time_utils import iso

START=datetime(2026,11,26,6,tzinfo=timezone.utc)
NOW=START+timedelta(minutes=15)
TOKEN='123456:'+'a'*35 # dummy value; no real secrets or network in tests
CHAT='-1001234567890'
PNG=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',1080,1350)


def fixture(folder,sectors=True):
    root=Path(folder);(root/'social').mkdir(exist_ok=True)
    rows=[dict(time=iso(START+timedelta(hours=i)),hs_m=1.,tp_s=8.,n_estimates=10,
        statistics_method=t.STATISTICS_METHOD,twl_mean_m=1.) for i in range(96)]
    generated=iso(START+timedelta(minutes=5));end=iso(START+timedelta(hours=96))
    units={}
    for key in (['1','2','3'] if sectors else ['whole']):
        name=f'{t.LOCATION}--{key}-20261126T060500Z.png';(root/'social'/name).write_bytes(PNG)
        units[key]=dict(name='Settore '+key,hourly=deepcopy(rows),social_card=dict(status='available',width=1080,height=1350,
            generated_at=generated,period_from=iso(START),period_to=end,url='data/social/'+name))
    parent=dict(name='Borghetto',sectors=units) if sectors else units['whole']
    b=dict(mode='meteocean',generated_at=generated,display_from=iso(START),display_to=end,display_hours=96,
        locations={t.LOCATION:parent,'venezia':{'name':'Must not be sent'}})
    return b,units


class FakeClient:
    chat_id=CHAT
    def __init__(self,failure_at=None,uncertain=False):self.sent=[];self.failure_at=failure_at;self.uncertain=uncertain
    def send_photo(self,delivery):
        self.sent.append(delivery['sector'])
        if len(self.sent)==self.failure_at:raise t.DeliveryError('Test failure',uncertain=self.uncertain)
        return 100+len(self.sent)


class TelegramDailyTests(unittest.TestCase):
    def test_preflight_only_borghetto_all_sectors_same_cycle_and_caption(self):
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);before=deepcopy(b);deliveries=t.prepare_deliveries(b,folder,now=NOW)
            self.assertEqual([d['sector'] for d in deliveries],['1','2','3']);self.assertEqual(b,before)
            for d in deliveries:
                self.assertIn('07:05 CET',d['caption']);self.assertIn(t.WARNING,d['caption']);self.assertIn('elaborazione di ricerca giornaliera',d['caption']);self.assertLessEqual(len(d['caption']),1024)
                self.assertIn('settore='+d['sector'],d['buttons']['inline_keyboard'][0][0]['url'])
                self.assertTrue(d['buttons']['inline_keyboard'][1][0]['url'].endswith('disclaimer.html'))
            b,_=fixture(folder,sectors=False);self.assertEqual(t.prepare_deliveries(b,folder,now=NOW)[0]['sector'],'whole')

    def test_demo_old_future_incomplete_or_stale_card_abort_before_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            original,_=fixture(folder)
            for mode in ['demo','unknown']:
                b=deepcopy(original);b['mode']=mode
                with self.assertRaises(ValueError):t.prepare_deliveries(b,folder,now=NOW)
            for now in (START+timedelta(hours=7),START-timedelta(minutes=5),START+timedelta(hours=97)):
                with self.assertRaises(ValueError):t.prepare_deliveries(original,folder,now=now)
            for edit in ('missing-hour','old-filter','stale-photo','wrong-period','wrong-size'):
                b=deepcopy(original);u=b['locations'][t.LOCATION]['sectors']['2']
                if edit=='missing-hour':u['hourly'].pop()
                if edit=='old-filter':u['hourly'][3]['statistics_method']='old'
                if edit=='stale-photo':u['social_card']['generated_at']=iso(START-timedelta(days=1))
                if edit=='wrong-period':u['social_card']['period_to']=iso(START+timedelta(hours=95))
                if edit=='wrong-size':u['social_card']['width']=500
                with self.assertRaises(ValueError,msg=edit):t.prepare_deliveries(b,folder,now=NOW)

    def test_only_expected_local_png_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            b,units=fixture(folder)
            for bad in ['data/social/../../secret.png','https://example.com/photo.png','data/social/venezia--whole-20261126T060500Z.png']:
                old=units['1']['social_card']['url'];units['1']['social_card']['url']=bad
                with self.assertRaises(ValueError):t.prepare_deliveries(b,folder,now=NOW)
                units['1']['social_card']['url']=old
            photo=Path(folder)/old.removeprefix('data/');photo.write_bytes(b'not a PNG')
            with self.assertRaises(ValueError):t.prepare_deliveries(b,folder,now=NOW)

    def test_daily_receipts_skip_repeated_builds_and_resume_after_explicit_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);items=t.prepare_deliveries(b,folder,now=NOW);path=Path(folder)/'receipt.json';state=t.empty_state()
            client=FakeClient(failure_at=2)
            with self.assertRaises(t.DeliveryError):t.deliver_daily(items,client,state,path,now=NOW,sleep=lambda _:None)
            stored=t.decode_state(path.read_bytes());self.assertEqual([e['status'] for e in stored['entries'].values()],['sent','failed'])
            client=FakeClient();result=t.deliver_daily(items,client,stored,path,now=NOW,sleep=lambda _:None)
            self.assertEqual(client.sent,['2','3']);self.assertEqual(result,dict(sent=2,skipped=1,pending=0))
            # Different generation, same UTC day => still one message per sector.
            for item in items:item['generated_at']=iso(NOW)
            client=FakeClient();result=t.deliver_daily(items,client,stored,path,now=NOW,sleep=lambda _:None)
            self.assertFalse(client.sent);self.assertEqual(result['skipped'],3)
            self.assertNotIn(CHAT,path.read_text());self.assertNotIn(TOKEN,path.read_text())

    def test_uncertain_delivery_is_not_retried_automatically(self):
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);items=t.prepare_deliveries(b,folder,now=NOW)[:1];path=Path(folder)/'receipt.json';client=FakeClient(failure_at=1,uncertain=True)
            with self.assertRaises(t.DeliveryError):t.deliver_daily(items,client,t.empty_state(),path,now=NOW)
            state=t.decode_state(path.read_bytes());self.assertEqual(next(iter(state['entries'].values()))['status'],'pending')
            retry=FakeClient();result=t.deliver_daily(items,retry,state,path,now=NOW)
            self.assertFalse(retry.sent);self.assertEqual(result['pending'],1)

    def test_new_day_or_different_channel_gets_its_own_bulletin(self):
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);items=t.prepare_deliveries(b,folder,now=NOW)[:1];path=Path(folder)/'receipt.json';state=t.empty_state()
            t.deliver_daily(items,FakeClient(),state,path,now=NOW)
            items[0]['day']='2026-11-27';client=FakeClient()
            self.assertEqual(t.deliver_daily(items,client,state,path,now=NOW+timedelta(days=1))['sent'],1)
            client=FakeClient();client.chat_id='-1009876543210'
            self.assertEqual(t.deliver_daily(items,client,state,path,now=NOW+timedelta(days=1))['sent'],1)

    def test_photo_request_is_multipart_with_caption_buttons_and_image(self):
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);delivery=t.prepare_deliveries(b,folder,now=NOW)[0];requests=[]
            def open_request(request,**kw):requests.append(request);return BytesIO(b'{"ok":true,"result":{"message_id":42}}')
            client=t.TelegramClient(TOKEN,CHAT,open_request=open_request)
            self.assertEqual(client.send_photo(delivery),42)
            req=requests[0];self.assertEqual(req.get_method(),'POST');self.assertTrue(req.full_url.endswith('/sendPhoto'))
            for value in (CHAT.encode(),t.WARNING.encode(),PNG,b'inline_keyboard',b'name="photo"'):self.assertIn(value,req.data)
            self.assertIn('multipart/form-data',req.get_header('Content-type'))

    def test_rate_limit_retries_only_after_explicit_rejection_and_transport_errors_hide_token(self):
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);d=t.prepare_deliveries(b,folder,now=NOW)[0]
            replies=[b'{"ok":false,"error_code":429,"parameters":{"retry_after":2}}',b'{"ok":true,"result":{"message_id":8}}'];wait=[]
            client=t.TelegramClient(TOKEN,CHAT,open_request=lambda *a,**k:BytesIO(replies.pop(0)),sleep=wait.append)
            self.assertEqual(client.send_photo(d),8);self.assertEqual(wait,[3])
            def timeout(*args,**kwargs):raise URLError('https://api.telegram.org/bot'+TOKEN+'/sendPhoto')
            with self.assertRaises(t.DeliveryError) as context:t.TelegramClient(TOKEN,CHAT,open_request=timeout).send_photo(d)
            self.assertTrue(context.exception.uncertain);self.assertNotIn(TOKEN,str(context.exception))
            def forbidden(*a,**k):raise HTTPError('https://api.telegram.org/bot'+TOKEN,403,'forbidden',{},BytesIO(b'{}'))
            with self.assertRaises(t.DeliveryError) as context:t.TelegramClient(TOKEN,CHAT,open_request=forbidden).send_photo(d)
            self.assertFalse(context.exception.uncertain);self.assertNotIn(TOKEN,str(context.exception))
            for raw in (b'not JSON',b'[]',b'{"ok":true,"result":{}}',b'{"ok":true,"result":[1]}',b'{"ok":true,"result":{"message_id":true}}',b'{"ok":false,"parameters":[1]}',b'{"ok":false,"error_code":500}'):
                with self.assertRaises(t.DeliveryError) as context:t.TelegramClient(TOKEN,CHAT,open_request=lambda *a,**k:BytesIO(raw)).send_photo(d)
                self.assertTrue(context.exception.uncertain)

    def test_restore_uses_only_receipts_of_the_trusted_forecast_workflow(self):
        state=t.empty_state();archive=BytesIO()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('receipt.json',json.dumps(state))
        def artifact(i,branch='main',repo=12):return dict(id=i,name=t.STATE_ARTIFACT,expired=False,size_in_bytes=500,
            workflow_run=dict(id=i,head_repository_id=repo,head_branch=branch))
        calls=[]
        def api(endpoint):
            calls.append(endpoint)
            if 'artifacts?' in endpoint:return json.dumps(dict(total_count=4,artifacts=[artifact(1),artifact(2),artifact(3,'test'),artifact(4,repo=99)])).encode()
            if endpoint.endswith('/runs/2'):return json.dumps(dict(path='.github/workflows/not-the-forecast.yml',event='push')).encode()
            if endpoint.endswith('/runs/1'):return json.dumps(dict(path='.github/workflows/local-forecast.yml',event='schedule')).encode()
            if endpoint.endswith('/artifacts/1/zip'):return archive.getvalue()
            self.fail('Unexpected API endpoint: '+endpoint)
        self.assertEqual(t.restore_state('owner/repo',12,'main',api=api),state)
        self.assertFalse(any('/runs/3' in c or '/runs/4' in c or '/artifacts/2/zip' in c for c in calls))
        self.assertEqual(t.restore_state('owner/repo',12,'main',api=lambda _:b'{"total_count":0,"artifacts":[]}'),t.empty_state())

    def test_restore_errors_do_not_silently_reset_receipts_or_extract_zip_paths(self):
        with patch.object(t.subprocess,'run',side_effect=t.subprocess.CalledProcessError(1,['gh'],stderr=TOKEN.encode())):
            with self.assertRaises(t.DeliveryError) as context:t.restore_state('owner/repo',12,'main')
            self.assertNotIn(TOKEN,str(context.exception))
        archive=BytesIO()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../../receipt.json','{}')
        def api(endpoint):
            if 'artifacts?' in endpoint:return json.dumps(dict(artifacts=[dict(id=1,name=t.STATE_ARTIFACT,size_in_bytes=500,workflow_run=dict(id=1,head_repository_id=12,head_branch='main'))])).encode()
            if '/runs/' in endpoint:return b'{"path":".github/workflows/local-forecast.yml","event":"workflow_dispatch"}'
            return archive.getvalue()
        with self.assertRaises(ValueError):t.restore_state('owner/repo',12,'main',api=api)
        with self.assertRaises(ValueError):t.decode_state(b'{"schema_version":1,"entries":{"bad":"value"}}')

    def test_cli_defaults_to_dry_run_without_secrets_or_any_network(self):
        import importlib.util
        path=Path(__file__).resolve().parents[2]/'scripts/send_telegram_bulletin.py'
        spec=importlib.util.spec_from_file_location('telegram_cli',path);cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);(Path(folder)/'forecast.json').write_text(json.dumps(b))
            clock=unittest.mock.Mock();clock.now.return_value=NOW
            with patch.object(cli,'datetime',clock),patch('sys.argv',['telegram','--data',folder]),patch.object(cli,'TelegramClient',side_effect=AssertionError('No network')),patch.object(cli,'restore_state',side_effect=AssertionError('No GitHub network')),patch('sys.stdout',new_callable=__import__('io').StringIO) as output:
                self.assertEqual(cli.main(),0);self.assertIn('Nessun messaggio inviato',output.getvalue())
