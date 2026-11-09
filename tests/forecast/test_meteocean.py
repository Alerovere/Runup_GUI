import csv
from datetime import datetime,timedelta,timezone
import io,json
from pathlib import Path
import unittest
from unittest.mock import patch

from forecast_service import pipeline
from forecast_service.meteocean import parse_waves,parse_surge,fetch_meteocean

UTC=timezone.utc
NOW=datetime(2026,11,9,0,tzinfo=UTC)


def wave_csv(count=120):
    return 'time,Hs,Tp,Dirp,Dirpx\n'+''.join(f'{NOW+timedelta(hours=i):%Y-%m-%d %H:%M:%S},1,8,350,0\n' for i in range(count))


def surge_csv(count=239):
    return ''.join(f'{NOW+timedelta(minutes=30*i):%Y-%m-%d %H:%M:%S},0.1\n' for i in range(count))


class MeteOceanTests(unittest.TestCase):
    def test_native_first_surge_row_is_not_discarded_as_header(self):
        rows=parse_surge(surge_csv())
        self.assertEqual(len(rows),239)
        self.assertEqual(rows[0]['time'],NOW)
        self.assertEqual(rows[0]['surge_m'],.1)

    def test_wavewatch_direction_is_preserved_without_a_180_degree_flip(self):
        rows=parse_waves(wave_csv())
        self.assertEqual(rows[0]['direction_deg'],350)
        self.assertEqual(rows[0]['tp_s'],8)
        self.assertEqual(rows[0]['time'].tzinfo,UTC)

    def test_missing_duplicate_nan_and_unphysical_values_are_rejected(self):
        rows=wave_csv().splitlines()
        for text in ['\n'.join(rows[:4]+rows[5:]),'\n'.join(rows[:4]+[rows[3]]+rows[4:]),
                     wave_csv().replace(',1,8,',',nan,8,',1),wave_csv().replace(',1,8,',',1,0,',1)]:
            with self.assertRaises(ValueError): parse_waves(text)
        with self.assertRaises(ValueError): parse_surge(surge_csv().replace(',0.1',',nan',1))

    def test_partial_or_mixed_daily_feeds_do_not_look_like_a_complete_forecast(self):
        settings={'locations':{'site':{'waves_url':'waves','surge_url':'surge'}}}
        def downloader(url): return (wave_csv(95) if url=='waves' else surge_csv()),{}
        with self.assertRaisesRegex(ValueError,'Copertura'):fetch_meteocean(settings,'site',NOW,120,downloader=downloader)
        def mixed(url):return (wave_csv() if url=='waves' else surge_csv().replace('2026-11-09','2026-11-08')),{}
        with self.assertRaises(ValueError): fetch_meteocean(settings,'site',NOW,120,downloader=mixed)

    def test_meteocean_level_is_tide_plus_surge_without_copernicus_mean(self):
        calls=[]
        def fetch(settings,slug,start,hours,minimum_hours):
            calls.append((slug,start))
            waves=[{'time':pipeline.iso(start+timedelta(hours=i)),'hs_m':1,'tp_s':8,'direction_deg':135,'surge_m':.1} for i in range(96)]
            return waves,{'selected_point':None,'surge':{'url':'test'}}
        def tides(grid,start,hours,now):
            return {slug:[{'time':pipeline.iso(start+timedelta(hours=i)),'tide_m':.2} for i in range(hours)] for slug in grid['locations']},{'provider':'NOAA','cycle_utc':pipeline.iso(start-timedelta(hours=6))}
        with patch('forecast_service.meteocean.fetch_meteocean',side_effect=fetch),patch.object(pipeline,'compute_runup',return_value={'Stockdon et al. (2006)':.8}):
            bulletin,files=pipeline.build_bulletin(provider='meteocean',now=NOW+timedelta(hours=14),tide_fetcher=tides)
        self.assertEqual(bulletin['mode'],'meteocean')
        self.assertEqual(bulletin['display_to'],'2026-11-13T00:00:00Z')
        self.assertEqual(bulletin['stale_after_hours'],30)
        self.assertTrue(all(start==NOW for _,start in calls))
        for loc in bulletin['locations'].values():
            self.assertAlmostEqual(loc['hourly'][0]['water_level_m'],.3)
            self.assertAlmostEqual(loc['hourly'][0]['twl_mean_m'],1.1)
            self.assertEqual(loc['sea_level_source']['mode'],'noaa_tide_meteocean_surge')
            self.assertNotIn('historical_reference',loc['sea_level_source'])
        exported=list(csv.DictReader(io.StringIO(files['borghetto-santo-spirito.csv'])))
        self.assertEqual(exported[0]['data_mode'],'meteocean')
        self.assertEqual(exported[0]['vertical_reference'],'noaa_htp_plus_meteocean_surge_provisional_msl')
        self.assertAlmostEqual(float(exported[0]['tide_m']),.2)
        self.assertAlmostEqual(float(exported[0]['surge_m']),.1)

    def test_misaligned_tide_aborts_the_whole_bulletin(self):
        def fetch(settings,slug,start,hours,minimum_hours):
            return [{'time':pipeline.iso(start),'hs_m':1,'tp_s':8,'direction_deg':90,'surge_m':.1}],{'surge':{}}
        def tides(grid,start,hours,now): return {slug:[] for slug in grid['locations']},{}
        with patch('forecast_service.meteocean.fetch_meteocean',side_effect=fetch):
            with self.assertRaisesRegex(ValueError,'allineata'):
                pipeline.build_bulletin(provider='meteocean',now=NOW,tide_fetcher=tides)
