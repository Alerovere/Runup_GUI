import csv
from datetime import datetime,timedelta,timezone
import io,json
from pathlib import Path
import unittest
from unittest.mock import patch

from forecast_service import pipeline
from forecast_service.meteocean import parse_waves,parse_surge,fetch_meteocean,filter_surge

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
            waves=[{'time':pipeline.iso(start+timedelta(hours=i)),'hs_m':1,'tp_s':8,'direction_deg':135,'surge_m':.1,'surge_raw_m':.35,'surge_filter_support_hours':6} for i in range(96)]
            native=[{'time':pipeline.iso(start+timedelta(minutes=30*i)),'surge_m':.1,'surge_raw_m':.35,'surge_filter_support_hours':6} for i in range(192)]
            return waves,{'selected_point':None,'surge':{'url':'test'},'surge_processing':{'window_hours':6},'surge_native_rows':native}
        def tides(grid,start,hours,now):
            return {slug:[{'time':pipeline.iso(start+timedelta(hours=i)),'tide_m':.2} for i in range(hours)] for slug in grid['locations']},{'provider':'NOAA','cycle_utc':pipeline.iso(start-timedelta(hours=6))}
        with patch('forecast_service.meteocean.fetch_meteocean',side_effect=fetch),patch.object(pipeline,'compute_runup',return_value={'Stockdon et al. (2006)':.8}):
            bulletin,files=pipeline.build_bulletin(provider='meteocean',now=NOW+timedelta(hours=14),tide_fetcher=tides)
        self.assertEqual(bulletin['mode'],'meteocean')
        self.assertEqual(bulletin['display_from'],'2026-11-09T14:00:00Z')
        self.assertEqual(bulletin['display_to'],'2026-11-13T14:00:00Z')
        self.assertEqual(bulletin['update_schedule'],{'hours_utc':[6],'minute_utc':40,'interval_hours':24})
        self.assertEqual(bulletin['wave_model']['publication_hours_utc'],[6])
        self.assertEqual(bulletin['wave_model']['publication_minute_utc'],20)
        self.assertEqual(bulletin['stale_after_hours'],30)
        self.assertTrue(all(start==NOW+timedelta(hours=14) for _,start in calls))
        for loc in bulletin['locations'].values():
            self.assertAlmostEqual(loc['hourly'][0]['water_level_m'],.3)
            self.assertAlmostEqual(loc['hourly'][0]['twl_mean_m'],1.1)
            self.assertAlmostEqual(loc['hourly'][0]['water_level_raw_m'],.55)
            self.assertEqual(loc['hourly'][0]['tide_m'],.2)
            self.assertEqual(loc['sea_level_source']['surge_processing']['window_hours'],6)
            self.assertNotIn('surge_native_rows',loc['source'])
            self.assertIn('surge_native_csv',loc['source'])
            for sector in loc.get('sectors',{}).values():
                self.assertAlmostEqual(sector['hourly'][0]['twl_mean_m'],1.1)
                self.assertAlmostEqual(sector['hourly'][0]['water_level_raw_m'],.55)
            self.assertEqual(loc['sea_level_source']['mode'],'noaa_tide_meteocean_surge')
            self.assertNotIn('historical_reference',loc['sea_level_source'])
        exported=list(csv.DictReader(io.StringIO(files['borghetto-santo-spirito.csv'])))
        self.assertEqual(exported[0]['data_mode'],'meteocean')
        self.assertEqual(exported[0]['vertical_reference'],'noaa_htp_plus_meteocean_surge_provisional_msl')
        self.assertAlmostEqual(float(exported[0]['tide_m']),.2)
        self.assertAlmostEqual(float(exported[0]['surge_m']),.1)
        self.assertAlmostEqual(float(exported[0]['surge_raw_m']),.35)
        self.assertAlmostEqual(float(exported[0]['water_level_raw_m']),.55)
        self.assertAlmostEqual(float(exported[0]['surge_filter_support_hours']),6)
        native=list(csv.DictReader(io.StringIO(files['borghetto-santo-spirito-surge-native.csv'])))
        self.assertEqual(len(native),192)
        self.assertEqual(native[1]['time'],'2026-11-09T14:30:00Z')
        self.assertEqual(float(native[1]['surge_raw_m']),.35)

    def test_misaligned_tide_aborts_the_whole_bulletin(self):
        def fetch(settings,slug,start,hours,minimum_hours):
            return [{'time':pipeline.iso(start),'hs_m':1,'tp_s':8,'direction_deg':90,'surge_m':.1}],{'surge':{}}
        def tides(grid,start,hours,now): return {slug:[] for slug in grid['locations']},{}
        with patch('forecast_service.meteocean.fetch_meteocean',side_effect=fetch):
            with self.assertRaisesRegex(ValueError,'allineata'):
                pipeline.build_bulletin(provider='meteocean',now=NOW,tide_fetcher=tides)


class PublicationCoverageTests(unittest.TestCase):
    def test_morning_acquisition_has_four_future_days_and_rejects_yesterdays_feed(self):
        settings={'locations':{'site':{'waves_url':'waves','surge_url':'surge'}}}
        def downloader(url):return (wave_csv() if url=='waves' else surge_csv()),{}
        rows,_=fetch_meteocean(settings,'site',NOW+timedelta(hours=6),120,downloader=downloader)
        self.assertEqual(len(rows),114)
        self.assertEqual(rows[0]['time'],'2026-11-09T06:00:00Z')
        self.assertEqual(rows[95]['time'],'2026-11-13T05:00:00Z')
        def old(url):
            text=wave_csv() if url=='waves' else surge_csv()
            lines=text.splitlines();out=[]
            for line in lines:
                if line.startswith('time,'):out.append(line);continue
                time,rest=line.split(',',1)
                time=datetime.strptime(time,'%Y-%m-%d %H:%M:%S')-timedelta(days=1)
                out.append(f'{time:%Y-%m-%d %H:%M:%S},'+rest)
            return '\n'.join(out),{}
        with self.assertRaisesRegex(ValueError,'Copertura'):
            fetch_meteocean(settings,'site',NOW+timedelta(hours=6),120,downloader=old)


class SurgeFilterTests(unittest.TestCase):
    def series(self,values):
        return [{'time':NOW+timedelta(minutes=30*i),'surge_m':value} for i,value in enumerate(values)]

    def test_constant_and_centered_ramp_preserved_and_edges_not_zero_padded(self):
        rows,meta=filter_surge(self.series([.2]*49))
        self.assertTrue(all(abs(r['surge_m']-.2)<1e-12 for r in rows))
        self.assertEqual(rows[0]['surge_filter_support_hours'],3)
        self.assertEqual(rows[6]['surge_filter_support_hours'],6)
        self.assertEqual(meta['truncated_native_samples'],12)
        rows,_=filter_surge(self.series([i*.01 for i in range(49)]))
        for r in rows[6:-6]:self.assertAlmostEqual(r['surge_m'],r['surge_raw_m'])
        self.assertAlmostEqual(rows[0]['surge_m'],.03)
        self.assertAlmostEqual(rows[-1]['surge_m'],.45)

    def test_impulse_center_and_end_weights_have_no_half_sample_phase_shift(self):
        values=[0.0]*49;values[24]=1
        rows,_=filter_surge(self.series(values))
        self.assertAlmostEqual(rows[24]['surge_m'],1/12)
        self.assertAlmostEqual(rows[18]['surge_m'],1/24)
        for i in range(7):self.assertAlmostEqual(rows[24-i]['surge_m'],rows[24+i]['surge_m'])
        self.assertEqual(rows[17]['surge_m'],0)
        self.assertEqual(rows[24]['surge_raw_m'],1)

    def test_invalid_window_missing_samples_and_nonfinite_values_rejected(self):
        rows=self.series([.1]*49)
        for hours in [-1,25,float('nan'),True,'6']:
            with self.assertRaises(ValueError):filter_surge(rows,hours)
        with self.assertRaises(ValueError):filter_surge(rows[:10]+rows[11:])
        with self.assertRaises(ValueError):filter_surge(self.series([.1,float('nan')]))
        with self.assertRaises(ValueError):filter_surge(rows[:1])

    def test_filter_runs_on_half_hour_samples_before_hourly_selection_and_can_be_disabled(self):
        settings={'locations':{'site':{'waves_url':'waves','surge_url':'surge'}}}
        # A signal entirely missed by old hourly selection must contribute.
        text=''.join(f'{r["time"]:%Y-%m-%d %H:%M:%S},{r["surge_m"]}\n' for r in self.series([i%2*.2 for i in range(239)]))
        def download(url):return (wave_csv() if url=='waves' else text),{}
        rows,meta=fetch_meteocean(settings,'site',NOW,120,downloader=download)
        self.assertAlmostEqual(rows[8]['surge_m'],.1)
        self.assertEqual(rows[8]['surge_raw_m'],0)
        self.assertEqual(len(meta['surge_native_rows']),239)
        self.assertEqual(meta['surge_processing']['window_hours'],6)
        rows,meta=fetch_meteocean(dict(settings,surge_smoothing_hours=0),'site',NOW,120,downloader=download)
        self.assertEqual(rows[8]['surge_m'],0)
        self.assertEqual(meta['surge_processing']['method'],'disabled')
