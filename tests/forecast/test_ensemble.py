import math
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from forecast_service.ensemble import sigma_clip,STATISTICS_METHOD
from forecast_service import pipeline as p


class EnsembleTests(unittest.TestCase):
    def test_three_sigma_removes_both_tails_but_keeps_the_boundary(self):
        for values,index in [([0.]*20+[100.],20),([-100.]+[0.]*20,0)]:
            mask,mean,sigma=sigma_clip(values)
            self.assertEqual(sum(mask),20)
            self.assertFalse(mask[index])
            self.assertGreater(abs(values[index]-mean),3*sigma)
        mask,mean,sigma=sigma_clip([0.]*9+[10.])
        self.assertEqual((mean,sigma),(1.,3.))
        self.assertTrue(all(mask))

    def test_degenerate_empty_and_nonfinite_inputs(self):
        self.assertEqual(sigma_clip([]),([],None,None))
        for values in ([2.],[2.]*30):
            mask,mean,sigma=sigma_clip(values)
            self.assertTrue(all(mask));self.assertEqual(mean,2.);self.assertEqual(sigma,0.)
        for value in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError):sigma_clip([1.,value])

    def test_filter_is_one_pass_not_iterative(self):
        mask,_,_=sigma_clip([0.]*98+[10.,100.])
        self.assertFalse(mask[-1]);self.assertTrue(mask[-2])

    def test_pipeline_preserves_raw_models_and_uses_filtered_denominator(self):
        config,impacts=p.load_configuration();loc=dict(config['locations']['venezia'],slopes=[.05])
        wave={'time':'2026-11-06T10:00:00Z','hs_m':1.,'tp_s':8.,'direction_deg':180.}
        outputs={**{f'low{i}':.5 for i in range(19)},'above':1.5,'outlier':100.}
        thresholds=[{'id':'fixed','elevation_m':1.1,'season':'all_year'}]
        with patch.object(p,'compute_runup',return_value=outputs):
            rows,raw=p.summarize_records([wave],loc,thresholds,impacts['summer_season'],0)
        row=rows[0]
        self.assertEqual(row['statistics_method'],STATISTICS_METHOD)
        self.assertEqual((row['n_estimates_raw'],row['n_estimates'],row['n_outliers']),(21,20,1))
        self.assertAlmostEqual(row['thresholds'][0]['fraction'],1/20)
        self.assertAlmostEqual(row['twl_mean_m'],.55)
        self.assertAlmostEqual(row['twl_p95_m'],.55)
        self.assertEqual(len(raw),21)
        self.assertFalse(next(r for r in raw if r['model']=='outlier')['included_in_summary'])
        self.assertEqual(next(r for r in raw if r['model']=='outlier')['twl_m'],100.)

    def test_screening_is_independent_for_each_hour_and_does_not_clip_a_storm_over_time(self):
        config,impacts=p.load_configuration();loc=dict(config['locations']['venezia'],slopes=[.05])
        waves=[{'time':f'2026-11-06T{hour}:00:00Z','hs_m':hs,'tp_s':8.,'direction_deg':180.} for hour,hs in [('10',1.),('11',2.)]]
        def outputs(inputs):
            offset=0 if inputs.hs==1 else 100
            return {**{f'm{i}':offset+.5 for i in range(20)},'outlier':offset+100}
        with patch.object(p,'compute_runup',side_effect=outputs):
            rows,raw=p.summarize_records(waves,loc,[],impacts['summer_season'],0)
        self.assertEqual([r['n_outliers'] for r in rows],[1,1])
        self.assertEqual([r['twl_mean_m'] for r in rows],[.5,100.5])
        self.assertEqual(len(raw),42)

if __name__=='__main__':unittest.main()
