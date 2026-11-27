from copy import deepcopy
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from forecast_service.beach_profile import profile_snapshot
from forecast_service.inundation import build_map
from forecast_service.infographic import card_data,render_card
from forecast_service.exposure import wave_is_exposed,EXPOSURE_POLICY
from test_beach_profile import fixture
from test_inundation_geojson import bulletin
from test_sectors_and_maps import grid
from test_infographic import fixture as card_fixture

class DirectionalDisplayTests(unittest.TestCase):
    def test_profile_ignores_a_higher_away_peak_without_modifying_raw_estimates(self):
        unit,row=fixture();away=deepcopy(row);away.update(time='2026-11-26T14:00Z',direction_deg=0,twl_mean_m=5,twl_p95_m=6,twl_p995_m=7)
        rows=[row,away];before=deepcopy(rows);result=profile_snapshot(unit,rows)
        self.assertEqual(result['time'],row['time']);self.assertTrue(result['exposed']);self.assertEqual(result['hours_frontal'],1)
        self.assertEqual(rows,before)
        blocked=profile_snapshot(unit,[away]);self.assertEqual(blocked['status'],'not_applicable');self.assertNotIn('mean_m',blocked)
        self.assertNotIn('mare calmo',blocked['reason'].split('Questo non indica')[0])
    def test_north_is_not_a_special_case_and_missing_exposure_is_not_assumed_front(self):
        self.assertTrue(wave_is_exposed(dict(hs_m=1,direction_deg=359),{'sectors_deg':[[315,45]]}))
        self.assertFalse(wave_is_exposed(dict(hs_m=1,direction_deg=180),{'sectors_deg':[[315,45]]}))
        for r,e in [(dict(hs_m=1,direction_deg=180),None),(dict(hs_m=0,direction_deg=180),{'sectors_deg':[[0,360]]}),(dict(hs_m=1,direction_deg=None),{'sectors_deg':[[0,360]]})]:self.assertIsNone(wave_is_exposed(r,e))
    def test_map_daily_layers_and_gis_ignore_nonfrontal_hours_and_withhold_blocked_days(self):
        from forecast_service.time_utils import parse_time
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin();unit=dict(hourly=rows,wave_exposure={'sectors_deg':[[70,130]]})
            for i,r in enumerate(rows):
                if i>=24:r.update(direction_deg=270,twl_mean_m=10,twl_p75_m=12)
            before=deepcopy(rows);meta,assets=build_map(unit,b,mapping,root,'venezia','whole')
            self.assertEqual(meta['exposure_policy'],EXPOSURE_POLICY);self.assertEqual(meta['hours_frontal'],24)
            self.assertEqual([l['level_m'] for l in meta['layers']],[.4,.5]);self.assertEqual(rows,before)
            blocked=[d for d in meta['daily'] if not d['hours_frontal']];self.assertTrue(blocked)
            for day in blocked:
                self.assertEqual(day['status'],'not_applicable');self.assertFalse(day['layers']);self.assertEqual(day['geojson_export']['files'],[])
                self.assertEqual(day['mobile_export']['status'],'not_applicable')
                self.assertFalse(any(day['date'] in key for key in assets))
            for day in meta['daily']:
                for l in day['layers']:
                    self.assertTrue(l['exposed_at_peak']);self.assertLess(parse_time(l['peak_time']),parse_time(rows[24]['time']))
            for file in meta['geojson_export']['files']:
                for f in json.loads(assets[file['url'].removeprefix('data/')])['features']:
                    self.assertEqual(f['properties']['exposure_policy'],EXPOSURE_POLICY)
                    self.assertEqual(f['properties']['hours_frontal'],24)
    def test_all_away_or_unknown_has_no_flood_images_or_gis_and_is_not_zero_risk(self):
        for exposure in [{'sectors_deg':[[180,270]]},None]:
            with self.subTest(exposure=exposure),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);mapping,_=grid(root);b,rows=bulletin();result,assets=build_map(dict(hourly=rows,wave_exposure=exposure),b,mapping,root,'venezia','whole')
                self.assertEqual(result['hours_frontal'],0);self.assertNotEqual(result['status'],'available');self.assertEqual(result['layers'],[])
                self.assertEqual(result['geojson_export']['files'],[]);self.assertFalse(any(name.endswith(('.geojson','.kmz','-mean.png','-p75.png')) for name in assets))
                self.assertNotIn('level_m',result);self.assertIn('sector_geometry',result)
    def test_png_has_no_profile_or_twl_number_for_all_away_waves_but_keeps_offshore_waves(self):
        b,unit=card_fixture()
        for row in unit['hourly']:row['direction_deg']=0
        before=deepcopy(unit['hourly']);data=card_data(b,unit)
        self.assertIsNone(data['twl']);self.assertEqual(data['profile']['status'],'not_applicable');self.assertIsNotNone(data['wave'])
        with tempfile.TemporaryDirectory() as folder:
            raw,meta=render_card(b,b['locations']['borghetto'],unit,folder,slug='borghetto',unit_id='uno')
            self.assertEqual(Image.open(BytesIO(raw)).size,(1080,1350));self.assertIsNone(meta['twl_peak_time'])
        self.assertEqual(unit['hourly'],before)
        from types import SimpleNamespace
        from forecast_service.profile_image import draw_profile
        labels=[]
        canvas=SimpleNamespace(draw=None,text=lambda text,*a,**k:labels.append(text))
        def forbidden(*a,**k):raise AssertionError('No profile geometry should be drawn')
        draw_profile(canvas,data['profile'],forbidden,forbidden)
        self.assertIn('Risalita non rappresentata',labels)
