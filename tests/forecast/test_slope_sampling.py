import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from forecast_service.slope_sampling import sample_slopes, validate_sampling
from forecast_service.sectors import resolve_sectors
from forecast_service import pipeline as p
from forecast_service.site_package import write_site_package, import_site_package
from test_sectors_and_maps import config, NOW


class SamplingTests(unittest.TestCase):
    def test_truncated_samples_preserve_bounds_and_repeated_measurement_weights(self):
        values,meta=sample_slopes([.02,.02,.1],method='truncated_normal',count=2000)
        self.assertEqual(len(values),2000)
        self.assertTrue(all(.02<=v<=.1 for v in values))
        self.assertAlmostEqual(meta['source_mean'],.14/3)
        self.assertAlmostEqual(meta['source_std'],np.std([.02,.02,.1],ddof=0))
        self.assertLess(sum(v>.08 for v in values)/len(values),.25)
        validate_sampling(values,meta,[.1,.02,.02],unit_id='whole')

    def test_streams_are_reproducible_per_sector_and_independent_of_source_order(self):
        args=dict(method='truncated_normal',count=80,seed=42)
        a,am=sample_slopes([.02,.04,.08],unit_id='a',**args)
        self.assertEqual((a,am),sample_slopes([.08,.04,.02],unit_id='a',**args))
        b,_=sample_slopes([.02,.04,.08],unit_id='b',**args)
        self.assertNotEqual(a,b)

    def test_one_transect_or_constant_slope_does_not_invent_spread(self):
        for source in ([.04],[.04,.04,.04]):
            values,meta=sample_slopes(source,method='truncated_normal')
            self.assertEqual(values,[.04]);self.assertTrue(meta['degenerate'])
            self.assertEqual(meta['effective_count'],1)

    def test_validation_reuses_saved_samples_without_new_random_draws(self):
        values,meta=sample_slopes([.02,.04,.08],method='truncated_normal',count=80)
        with patch('forecast_service.slope_sampling.sample_slopes',side_effect=AssertionError('Nuova estrazione')):
            validate_sampling(values,meta,[.02,.04,.08],unit_id='whole')

    def test_measured_and_linear_alternatives(self):
        source=[.02,.02,.08]
        self.assertEqual(sample_slopes(source)[0],[.02,.08])
        np.testing.assert_allclose(sample_slopes(source,method='linear_range',count=4)[0],[.02,.04,.06,.08])

    def test_invalid_input_and_stale_samples_are_rejected(self):
        for source in ([],[0],[float('nan')],[True],[1]):
            with self.assertRaises(ValueError):sample_slopes(source)
        for kwargs in ({'count':1},{'count':2001},{'seed':-1},{'method':'unknown'}):
            with self.assertRaises(ValueError):sample_slopes([.02,.08],**kwargs)
        values,meta=sample_slopes([.02,.08],method='truncated_normal',count=20)
        with self.assertRaisesRegex(ValueError,'non coerenti'):validate_sampling(values,meta,[.03,.08],unit_id='whole')
        values[0]=.025
        with self.assertRaises(ValueError):validate_sampling(values,meta,[.02,.08],unit_id='whole')

    def test_sector_sampling_roundtrip_and_forecast_use_saved_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);locations,impacts=config(root)
            loc=locations['locations']['venezia']
            loc['transects']=[dict(transect_id=k,slope=s) for k,s in zip('abcd',[.02,.04,.07,.09])]
            loc['slopes'],loc['slope_sampling']=sample_slopes([.02,.04,.07,.09],method='truncated_normal',count=8)
            for key,ids in [('ovest',['a','b']),('est',['c','d'])]:
                sector=loc['sectors'][key];sector['transect_ids']=ids
                values=[r['slope'] for r in loc['transects'] if r['transect_id'] in ids]
                sector['slopes'],sector['slope_sampling']=sample_slopes(values,method='truncated_normal',count=8,unit_id=key)
            payload=dict(schema_version=1,slug='venezia',data_mode='study',location=loc,thresholds=impacts['locations']['venezia']['thresholds'],provenance={})
            # Include the existing climatology, as the normal setup package does.
            climate=json.loads((root/loc['climatology_file']).read_text()) if loc.get('climatology_file') else None
            package=write_site_package(root/'site.zip',payload,climatology=climate)
            import_site_package(package,root,replace=True)
            loaded,_=p.load_configuration(root)
            self.assertEqual(loaded['locations']['venezia']['sectors']['ovest']['slopes'],loc['sectors']['ovest']['slopes'])
            bulletin,_=p.build_bulletin(root=root,demo=True,now=NOW)
            units=bulletin['locations']['venezia']['sectors']
            self.assertEqual(units['est']['slopes'],loc['sectors']['est']['slopes'])
            expected,_=p.summarize_records(bulletin['locations']['venezia']['hourly'],units['est'],units['est']['thresholds'],units['est']['summer_season'],0.)
            self.assertEqual(expected[0]['twl_p95_m'],units['est']['hourly'][0]['twl_p95_m'])
            self.assertNotEqual(units['ovest']['hourly'][0]['twl_p95_m'],units['est']['hourly'][0]['twl_p95_m'])
            changed=copy.deepcopy(loc);changed['transects'][0]['slope']=.03
            with self.assertRaises(ValueError):resolve_sectors(changed,payload['thresholds'])
