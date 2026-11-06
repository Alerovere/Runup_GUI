import csv
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from forecast_service import pipeline as p
from src.runup_models import RunupInputs, compute_runup, fallback_runup

NOW = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.config, self.impacts = p.load_configuration()
        self.loc = self.config['locations']['venezia']
        self.thresholds = self.impacts['locations']['venezia']['thresholds']

    def test_existing_scientific_results_are_preserved_for_every_slope(self):
        wave = {'time': p.iso(NOW), 'hs_m': 1.5, 'tp_s': 8.0, 'direction_deg': 135.0}
        rows, detail = p.summarize_records([wave], self.loc, self.thresholds, self.impacts['summer_season'], .25)
        for slope in self.loc['slopes']:
            original = compute_runup(RunupInputs(1.5, 8.0, slope, .25, self.loc['roughness_m']))
            for name, expected in original.items():
                actual = [r for r in detail if r['model'] == name and r['slope'] == slope]
                if math.isfinite(expected):
                    self.assertEqual(len(actual), 1)
                    self.assertAlmostEqual(actual[0]['runup_m'], expected, places=12)
                    self.assertAlmostEqual(actual[0]['twl_m'], expected + .25, places=12)
                else:
                    self.assertFalse(actual)
        self.assertEqual(rows[0]['n_estimates_raw'], len(detail))
        self.assertEqual(rows[0]['n_estimates'], sum(r['included_in_summary'] for r in detail))
        self.assertLessEqual(rows[0]['twl_min_m'], rows[0]['twl_p05_m'])
        self.assertLessEqual(rows[0]['twl_p95_m'], rows[0]['twl_max_m'])

    def test_stockdon_fallback_matches_the_existing_formula(self):
        inputs = RunupInputs(1.5, 8.0, .05, 0)
        result = fallback_runup(inputs)['Stockdon et al. (2006)']
        l0 = 9.81 * 8**2 / (2*math.pi)
        expected = 1.1*(.35*.05*math.sqrt(1.5*l0) + .5*math.sqrt(1.5*l0*(.563*.05**2+.004)))
        self.assertAlmostEqual(result, expected)

    def test_threshold_is_strictly_exceeded_and_fraction_uses_valid_results(self):
        loc = dict(self.loc, slopes=[.05])
        wave = {'time': p.iso(NOW), 'hs_m': 1, 'tp_s': 8, 'direction_deg': 90}
        thresholds = [{'id': 'x', 'elevation_m': .7, 'season': 'all_year'}]
        with patch.object(p, 'compute_runup', return_value={'equal': .7, 'over': .9, 'missing': float('nan')}):
            rows, detail = p.summarize_records([wave], loc, thresholds, self.impacts['summer_season'], 0)
        self.assertEqual(rows[0]['thresholds'][0]['fraction'], .5)
        self.assertEqual(len(detail), 2)

    def test_unknown_season_is_explicit_and_boundaries_use_italian_date(self):
        threshold = self.thresholds[0]
        self.assertIsNone(p.seasonal_activity(threshold, p.iso(NOW), self.impacts['summer_season']))
        season = {'start_month_day': '06-01', 'end_month_day': '09-30'}
        self.assertTrue(p.seasonal_activity(threshold, '2026-05-31T22:00:00Z', season))
        self.assertFalse(p.seasonal_activity(threshold, '2026-09-30T22:00:00Z', season))
        self.assertTrue(p.seasonal_activity(self.thresholds[2], p.iso(NOW), season))

    def test_calm_or_invalid_hours_remain_missing_instead_of_zero_risk(self):
        waves = [{'time': p.iso(NOW), 'hs_m': 0, 'tp_s': 8, 'direction_deg': 90},
                 {'time': p.iso(NOW+timedelta(hours=1)), 'hs_m': 1, 'tp_s': 8, 'direction_deg': 90}]
        with patch.object(p, 'compute_runup', return_value={'one': 1.0}):
            rows, _ = p.summarize_records(waves, self.loc, self.thresholds, self.impacts['summer_season'], 0)
        self.assertEqual(rows[0]['n_estimates'], 0)
        self.assertIsNone(rows[0]['twl_mean_m'])
        self.assertIsNone(rows[0]['thresholds'][0]['fraction'])

    def test_live_bulletin_fails_if_the_model_library_is_missing(self):
        with patch.object(p, 'models', None), self.assertRaisesRegex(RuntimeError, 'fallback'):
            p.build_bulletin(now=NOW)

    def test_demo_is_labelled_in_json_and_csv_and_is_strict_json(self):
        with patch.object(p, 'compute_runup', return_value={'Stockdon et al. (2006)': .8}):
            bulletin, csvs = p.build_bulletin(demo=True, now=NOW)
        self.assertEqual(bulletin['mode'], 'demo')
        self.assertEqual(bulletin['ensemble_statistics']['method'], 'sigma_clip_3_population_v1')
        for loc in bulletin['locations'].values():
            self.assertEqual(len(loc['hourly']), 120)
            self.assertIsNone(loc['source']['dataset_id'])
            self.assertEqual(p.parse_time(loc['valid_to'])-p.parse_time(loc['valid_from']), timedelta(hours=120))
        with tempfile.TemporaryDirectory() as directory:
            p.write_bulletin(bulletin, csvs, directory)
            stored = json.loads((Path(directory)/'forecast.json').read_text())
            self.assertEqual(stored['mode'], 'demo')
            with (Path(directory)/'venezia.csv').open() as handle:
                exported=list(csv.DictReader(handle))
                labels={(row['data_mode'],row['vertical_reference']) for row in exported}
            self.assertEqual(len(exported),sum(row['n_estimates_raw'] for row in stored['locations']['venezia']['hourly']))
            self.assertTrue(all(row['included_in_summary']=='True' for row in exported))
            self.assertEqual(labels,{('demo','synthetic_reference')})
            self.assertFalse((Path(directory)/'forecast.json.tmp').exists())

    def test_one_failed_location_prevents_a_partial_bulletin(self):
        calls = []
        def fetcher(location, dataset, start, hours):
            calls.append(location['name'])
            if len(calls) == 2:
                raise ValueError('Cella marina non disponibile')
            return p.demonstration_waves(location, start, hours)
        with patch.object(p, 'compute_runup', return_value={'Stockdon et al. (2006)': .8}):
            with self.assertRaisesRegex(ValueError, 'Cella marina'):
                p.build_bulletin(now=NOW, fetcher=fetcher,
                    sealevel_fetcher=lambda loc,settings,start,hours: __import__('forecast_service.sealevel',fromlist=['demonstration_sealevel']).demonstration_sealevel(loc,p.demonstration_waves(loc,start,hours)[0]))
        self.assertEqual(len(calls), 2)

    def test_copernicus_requires_contiguous_hours_and_retains_selected_coordinates(self):
        import numpy as np
        import xarray as xr
        times = [NOW.replace(tzinfo=None)+timedelta(hours=i) for i in range(120)]
        ds = xr.Dataset({key: (('time','latitude','longitude'), np.ones((120,1,1))*value)
                         for key,value in [('VHM0',1.5),('VTPK',8),('VMDR',135)]},
                        coords={'time':times,'latitude':[45.33],'longitude':[12.5]})
        with patch.dict('os.environ', {'COPERNICUSMARINE_USERNAME':'test','COPERNICUSMARINE_PASSWORD':'test'}):
            with patch('copernicusmarine.open_dataset',return_value=ds), patch('forecast_service.wave_cycle.verified_native_cycle',return_value={'forecast_reference_time':'2026-11-05T00:00:00Z'}) as verify:
                rows, metadata = p.fetch_copernicus(self.loc,self.config['dataset_id'],NOW,120)
            self.assertEqual(len(rows),120)
            verify.assert_called_once()
            self.assertEqual(len(verify.call_args.args[1]),120)
            self.assertEqual(metadata['forecast_reference_time'],'2026-11-05T00:00:00Z')
            self.assertEqual(metadata['selected_point']['latitude'],45.33)
            with patch('copernicusmarine.open_dataset',return_value=ds), patch('forecast_service.wave_cycle.verified_native_cycle',return_value={'forecast_reference_status':'unverified'}):
                unlabelled_rows, unlabelled_metadata = p.fetch_copernicus(self.loc,self.config['dataset_id'],NOW,120)
            self.assertEqual(unlabelled_rows,rows)
            self.assertNotIn('forecast_reference_time',unlabelled_metadata)
            with patch('copernicusmarine.open_dataset',return_value=ds.isel(time=slice(0,119))):
                with self.assertRaisesRegex(ValueError,'incompleta'):
                    p.fetch_copernicus(self.loc,self.config['dataset_id'],NOW,120)


if __name__ == '__main__':
    unittest.main()
