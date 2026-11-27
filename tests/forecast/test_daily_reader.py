from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from forecast_service.inundation import build_map
from forecast_service.reader_summary import bulletin_summary,change_text,summary_lines
from forecast_service.map_context import surveyed_points
from test_sectors_and_maps import grid
from test_inundation_geojson import bulletin
from test_telegram_daily import fixture,NOW,START,FakeClient
from forecast_service import telegram_daily as t
class DailyReaderTests(unittest.TestCase):
    def test_daily_peaks_exports_and_context_preserve_full_period_and_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin();unit=dict(hourly=rows,mapping=mapping,wave_exposure={'sectors_deg':[[0,360]]});before=deepcopy(rows)
            meta,assets=build_map(unit,b,mapping,root,'venezia','whole')
            self.assertEqual(rows,before);self.assertEqual(sum(d['hours'] for d in meta['daily']),96)
            self.assertIn('sector_geometry',meta);self.assertIn('display_bounds',meta)
            for day in meta['daily']:
                # Parse time offsets rather than compare mixed ISO representations.
                from forecast_service.time_utils import parse_time
                samples=[r for r in rows if parse_time(day['period_from'])<=parse_time(r['time'])<parse_time(day['period_to'])]
                for layer in day['layers']:
                    self.assertEqual(layer['level_m'],max(r[layer['statistic']] for r in samples))
                    self.assertIn(layer['image'].removeprefix('data/'),assets)
                    self.assertIn('line_geometry',layer)
                for file in day['geojson_export']['files']:
                    features=json.loads(assets[file['url'].removeprefix('data/')])['features']
                    self.assertTrue(all(f['properties']['forecast_from_utc']==day['period_from'] for f in features))
    def test_validated_point_metadata_does_not_need_original_files(self):
        unit={'thresholds':[{'id':'kiosk','survey_statistics':{'points':[dict(longitude=8.2,latitude=44.1,elevation_m=1.3)]}}]}
        points=surveyed_points(unit,Path('/nonexistent'),'beach','one')
        self.assertEqual(len(points),1);self.assertEqual(points[0]['label'],'kiosk')
    def test_summary_missing_direction_is_not_numeric_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            b,units=fixture(folder);summary=bulletin_summary(units['1'],units['1']['hourly'])
            self.assertIsNone(summary['fraction']);self.assertEqual(summary['key'],'unavailable')
            self.assertIn('non disponibile',change_text(summary,{'key':'white'}))
    def test_telegram_change_uses_previous_sent_sector_only_and_never_repeats(self):
        with tempfile.TemporaryDirectory() as folder:
            b,units=fixture(folder);deliveries=t.prepare_deliveries(b,folder,now=NOW);state=t.empty_state();client=FakeClient();path=Path(folder)/'state.json'
            t.deliver_daily(deliveries,client,state,path,now=NOW,sleep=lambda _:None)
            for e in state['entries'].values():self.assertIn('summary',e)
            self.assertEqual(t.deliver_daily(deliveries,client,state,path,now=NOW,sleep=lambda _:None)['skipped'],3)
    def test_change_labels_disclose_shifted_validity_period(self):
        self.assertIn('più alta',change_text({'key':'orange'},{'key':'white'}));self.assertIn('diversi',change_text({'key':'white'},{'key':'white'}))
    def test_calendar_day_with_dst_has_25_hours_not_a_fixed_24(self):
        from datetime import datetime,timezone
        from forecast_service.time_utils import iso
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin();start=datetime(2026,10,24,22,tzinfo=timezone.utc)
            b.update(display_from=iso(start),display_to=iso(start+timedelta(hours=96)))
            for i,row in enumerate(rows):row['time']=iso(start+timedelta(hours=i))
            meta,_=build_map(dict(hourly=rows,wave_exposure={'sectors_deg':[[0,360]]}),b,mapping,root,'venezia','whole')
            self.assertEqual([d['hours'] for d in meta['daily']],[25,24,24,23])
    def test_change_is_appended_on_next_day_for_same_channel_and_sector(self):
        class Capture(FakeClient):
            def __init__(self):super().__init__();self.captions=[]
            def send_photo(self,delivery):self.captions.append(delivery['caption']);return super().send_photo(delivery)
        with tempfile.TemporaryDirectory() as folder:
            b,_=fixture(folder);deliveries=t.prepare_deliveries(b,folder,now=NOW);state=t.empty_state();client=Capture();path=Path(folder)/'state.json'
            for d in deliveries:d['summary']={'key':'white'}
            t.deliver_daily(deliveries,client,state,path,now=NOW,sleep=lambda _:None)
            tomorrow=deepcopy(deliveries)
            for d in tomorrow:d.update(day='2026-11-27',summary={'key':'orange'})
            t.deliver_daily(tomorrow,client,state,path,now=NOW+timedelta(days=1),sleep=lambda _:None)
            self.assertEqual(len(client.captions),6)
            self.assertTrue(all('fascia più alta' in c and 'periodi confrontati sono diversi' in c for c in client.captions[3:]))
