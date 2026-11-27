from copy import deepcopy
from datetime import datetime,timezone
import unittest
from unittest.mock import patch
from forecast_service.beach_profile import profile_snapshot
from forecast_service import pipeline as p
from forecast_service.ensemble import STATISTICS_METHOD


def fixture():
    unit=dict(thresholds=[dict(id='chioschi',short_label='Chioschi',elevation_m=1.4,season='all_year'),dict(id='passeggiata',short_label='Passeggiata',elevation_m=1.82,season='all_year')],wave_exposure={'sectors_deg':[[135,225]]})
    row=dict(time='2026-11-26T13:00:00Z',hs_m=1.2,tp_s=8.,direction_deg=180.,n_estimates=2000,statistics_method=STATISTICS_METHOD,twl_mean_m=1.13,twl_p75_m=1.29,twl_p95_m=1.55,twl_p995_m=1.86,thresholds=[dict(id='chioschi',active=True,fraction=.196),dict(id='passeggiata',active=True,fraction=.009)])
    return unit,row

class BeachProfileTests(unittest.TestCase):
    def test_p995_is_computed_on_same_filtered_samples_as_direct_fractions(self):
        values={str(i):i/100 for i in range(200)};values['outlier']=1000.
        loc=dict(slopes=[.05],roughness_m=0)
        wave=dict(time='2026-11-26T13:00Z',hs_m=1,tp_s=8,direction_deg=180)
        thresholds=[dict(id='promenade',elevation_m=1.82,season='all_year')]
        with patch.object(p,'compute_runup',return_value=values):rows,detail=p.summarize_records([wave],loc,thresholds,{},0)
        r=rows[0];filtered=[d['twl_m'] for d in detail if d['included_in_summary']]
        self.assertEqual(r['n_outliers'],1);self.assertEqual(r['twl_p995_m'],p.quantile(filtered,.995))
        self.assertEqual(r['thresholds'][0]['fraction'],sum(v>1.82 for v in filtered)/len(filtered))
        self.assertLess(r['twl_p95_m'],r['twl_p995_m']);self.assertLess(r['twl_p995_m'],r['twl_max_m'])
    def test_levels_and_percentages_share_the_greatest_mean_hour_not_other_peaks(self):
        unit,row=fixture();earlier=deepcopy(row);later=deepcopy(row)
        earlier.update(time='2026-11-26T12:00Z',twl_mean_m=.9,twl_p95_m=2.1,twl_p995_m=2.3)
        earlier['thresholds'][0]['fraction']=.8
        later.update(time='2026-11-26T14:00Z',twl_mean_m=1.0,twl_p95_m=1.6)
        before=deepcopy([earlier,row,later]);snapshot=profile_snapshot(unit,before)
        self.assertEqual(snapshot['time'],row['time']);self.assertEqual(snapshot['p995_m'],1.86)
        self.assertEqual(snapshot['structures'][0]['fraction'],.196);self.assertEqual(snapshot['structures'][1]['count'],18)
        self.assertEqual(before,[earlier,row,later]);self.assertFalse(snapshot['horizontal_distances_to_scale'])
    def test_legacy_tail_missing_and_invalid_order_are_not_invented(self):
        unit,row=fixture();row.pop('twl_p995_m');self.assertIsNone(profile_snapshot(unit,[row])['p995_m'])
        row['twl_p995_m']=1.;self.assertIsNone(profile_snapshot(unit,[row])['p995_m'])
    def test_nonfrontal_inactive_unknown_and_unfiltered_are_not_flooding_percentages(self):
        unit,row=fixture();row['direction_deg']=0
        snapshot=profile_snapshot(unit,[row]);self.assertEqual(snapshot['key'],'gray');self.assertFalse(snapshot['exposed']);self.assertTrue(all(a['fraction'] is None for a in snapshot['structures']))
        row['direction_deg']=180;row['thresholds'][0]['active']=False
        self.assertEqual(profile_snapshot(unit,[row])['structures'][0]['state'],'inactive')
        row['direction_deg']=None;self.assertIsNone(profile_snapshot(unit,[row])['structures'][1]['fraction'])
        row['statistics_method']='legacy';self.assertEqual(profile_snapshot(unit,[row])['status'],'unavailable')
    def test_p995_does_not_promote_impact_category(self):
        unit,row=fixture();row.update(twl_p75_m=1.0,twl_p95_m=1.3,twl_p995_m=10.)
        self.assertEqual(profile_snapshot(unit,[row])['key'],'white')
