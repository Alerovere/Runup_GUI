import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from scipy.stats import gumbel_r

from forecast_service.extremes import (build_directional_extremes, compare_directional_extremes,
    fit_gumbel, gumbel_return_period, sector_index, validate_directional_extremes)


class GumbelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.annual=[{'year':1980+i,'hs_m':float(h),'time':f'{1980+i}-01-01T00:00:00Z'}
                    for i,h in enumerate(gumbel_r.ppf(np.arange(1,41)/41,loc=2,scale=.4))]
        cls.fit=fit_gumbel(cls.annual,bootstrap_replicates=100)

    def test_return_period_inverts_known_gumbel_return_levels(self):
        for period in (1.01,2,5,10,50,100):
            height=gumbel_r.isf(1/period,loc=2,scale=.4)
            self.assertAlmostEqual(gumbel_return_period(height,2,.4),period,places=9)
        self.assertEqual(gumbel_return_period(-1e6,2,.4),1)
        self.assertIsNone(gumbel_return_period(1e6,2,.4))

    def test_fit_and_bootstrap_preserve_scale_and_have_valid_bands(self):
        result=self.fit
        self.assertEqual(result['status'],'available')
        self.assertEqual(result['n_years'],40)
        self.assertAlmostEqual(result['loc_m'],2,delta=.1)
        self.assertAlmostEqual(result['scale_m'],.4,delta=.1)
        self.assertTrue(all(a<=b for a,b in zip(result['ci95_low_m'],result['ci95_high_m'])))
        self.assertTrue(all(a<b for a,b in zip(result['return_level_m'],result['return_level_m'][1:])))
        twice=[dict(row,hs_m=row['hs_m']*2) for row in self.annual]
        scaled=fit_gumbel(twice,bootstrap_replicates=100)
        np.testing.assert_allclose(scaled['return_level_m'],np.asarray(result['return_level_m'])*2,rtol=1e-10)
        np.testing.assert_allclose(scaled['ci95_high_m'],np.asarray(result['ci95_high_m'])*2,rtol=1e-10)
        self.assertIn(40,result['return_period_years'])

    def test_insufficient_constant_and_duplicate_annual_blocks(self):
        self.assertEqual(fit_gumbel(self.annual[:19],bootstrap_replicates=100)['status'],'insufficient_years')
        constant=[dict(row,hs_m=2) for row in self.annual]
        self.assertEqual(fit_gumbel(constant,bootstrap_replicates=100)['status'],'constant_maxima')
        with self.assertRaises(ValueError): fit_gumbel(self.annual+[self.annual[0]],bootstrap_replicates=100)

    def test_sector_boundaries_have_no_overlap_and_wrap_at_zero(self):
        self.assertEqual(sector_index(0,45),0)
        self.assertEqual(sector_index(360,45),0)
        self.assertEqual(sector_index(22.4999,45),0)
        self.assertEqual(sector_index(22.5,45),1)
        self.assertEqual(sector_index(337.5,45),0)
        self.assertEqual(sector_index(90,45),2)
        self.assertIsNone(sector_index(None,45))

    def test_forecast_is_compared_with_its_own_sector_without_modifying_inputs(self):
        extremes={'status':'available','sector_width_deg':180,'sectors':[
            {'id':'sector-0','fit':{'status':'available','loc_m':2,'scale_m':.4}},
            {'id':'sector-1','fit':{'status':'available','loc_m':4,'scale_m':.8}}]}
        waves=[{'hs_m':3,'direction_deg':0},{'hs_m':3,'direction_deg':180},{'hs_m':2}]
        before=copy.deepcopy(waves)
        result=compare_directional_extremes(waves,extremes)
        self.assertEqual(waves,before)
        self.assertEqual(result[0]['wave_sector_id'],'sector-0')
        self.assertEqual(result[1]['wave_sector_id'],'sector-1')
        self.assertGreater(result[0]['hs_return_period_years'],result[1]['hs_return_period_years'])
        self.assertIsNone(result[2]['hs_return_period_years'])
        json.dumps(result,allow_nan=False)


class AnnualSectorTests(unittest.TestCase):
    def series(self):
        time=pd.date_range('2000-01-01','2002-01-01',freq='h',tz='UTC')
        index=np.arange(len(time))
        return pd.DataFrame({'time':time,'hs_m':1+(index%19)/10,'direction_deg':np.where(index%2,20,200)})

    def build(self,frame):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'series.csv'; frame.to_csv(path,index=False)
            return build_directional_extremes(path,sector_width_deg=180,bootstrap_replicates=100)

    def test_maximum_is_taken_within_each_sector_in_each_complete_year(self):
        result=self.build(self.series())
        self.assertEqual(result['included_years'],[2000,2001])
        self.assertEqual(result['annual_coverage'][0]['expected_hours'],8784)
        self.assertFalse(result['annual_coverage'][-1]['included'])
        for sector in result['sectors']:
            self.assertEqual([row['year'] for row in sector['annual_maxima']],[2000,2001])
        invalid=copy.deepcopy(result)
        invalid['sectors'][0]['start_deg']=1
        with self.assertRaises(ValueError): validate_directional_extremes(invalid)

    def test_missing_positive_wave_direction_excludes_year_but_calm_does_not(self):
        frame=self.series()
        frame.loc[frame.time.eq(pd.Timestamp('2001-02-01',tz='UTC')),'direction_deg']=np.nan
        self.assertEqual(self.build(frame)['included_years'],[2000])
        frame.loc[frame.time.eq(pd.Timestamp('2001-02-01',tz='UTC')),'hs_m']=0
        self.assertEqual(self.build(frame)['included_years'],[2000,2001])

    def test_no_wave_year_is_not_silently_removed_to_condition_the_return_period(self):
        frame=self.series(); frame.loc[frame.time.dt.year==2001,'direction_deg']=20
        result=self.build(frame)
        sector=result['sectors'][1]
        self.assertEqual(sector['fit']['status'],'years_without_sector_waves')
        self.assertEqual(sector['fit']['years_without_waves'],[2001])

    def test_missing_direction_column_keeps_return_period_unavailable(self):
        result=self.build(self.series().drop(columns='direction_deg'))
        self.assertEqual(result['status'],'not_configured')


if __name__=='__main__': unittest.main()
