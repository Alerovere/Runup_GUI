import csv
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from forecast_service.sealevel import align_sealevel, fetch_sealevel
from forecast_service.climate import build_climate, compare_waves
from forecast_service.era5_download import download_series, ts_range, year_chunks
from forecast_service.site_setup import slopes_from_transects


class SeaLevelTests(unittest.TestCase):
    def test_fixed_mean_is_preserved_instead_of_forecast_mean(self):
        waves=[{'time':'2020-01-01T01:00Z'}]
        levels=[{'time':'2020-01-01T00:30Z','ssh_m':.6},{'time':'2020-01-01T01:30Z','ssh_m':.8}]
        result=align_sealevel(waves,levels,.2,.1)
        self.assertAlmostEqual(result[0]['water_level_m'],.6)
        self.assertAlmostEqual(result[0]['ssh_m'],.7)
        # A changing forecast window does not change the fixed reference.
        longer=levels+[{'time':'2020-01-01T02:30Z','ssh_m':1.2}]
        self.assertEqual(result,align_sealevel(waves,longer,.2,.1))

    def test_missing_brackets_and_missing_hours_are_not_zeroed(self):
        waves=[{'time':'2020-01-01T01:00Z'}]
        with self.assertRaises(ValueError):
            align_sealevel(waves,[{'time':'2020-01-01T00:30Z','ssh_m':.6}],.2)
        with self.assertRaises(ValueError):
            align_sealevel(waves,[{'time':'2020-01-01T00:00Z','ssh_m':.6},{'time':'2020-01-01T02:00Z','ssh_m':.8}],.2)

    def test_copernicus_uses_zos_and_mdt_in_the_same_cell(self):
        import numpy as np
        import xarray as xr
        sea=xr.Dataset({'zos':(('time','latitude','longitude'),np.array([.6,.8]).reshape(2,1,1))},
                       coords={'time':['2020-01-01T00:30','2020-01-01T01:30'],'latitude':[44.0],'longitude':[8.5]})
        mean=xr.Dataset({'mdt':(('latitude','longitude'),[[.2]])},coords={'latitude':[44.0],'longitude':[8.5]})
        settings={'dataset_id':'ssh','static_dataset_id':'static'}
        loc={'wave_point':{'latitude':44.0,'longitude':8.5}}
        with patch.dict('os.environ',{'COPERNICUSMARINE_USERNAME':'test','COPERNICUSMARINE_PASSWORD':'test'}),patch('copernicusmarine.open_dataset',side_effect=[sea,mean]) as request:
            levels,reference,metadata=fetch_sealevel(loc,settings,dt.datetime(2020,1,1,tzinfo=dt.timezone.utc),2)
        self.assertEqual(reference,.2)
        self.assertEqual(request.call_args_list[0].kwargs['variables'],['zos'])
        self.assertEqual(request.call_args_list[1].kwargs['variables'],['mdt'])
        # Without an explicit part the Toolbox selects bathymetry, which has no MDT.
        self.assertEqual(request.call_args_list[1].kwargs['dataset_part'],'mdt')
        self.assertEqual(metadata['reference_source'],'static::mdt')


class HistoricalSetupTests(unittest.TestCase):
    def test_climate_percentile_and_observed_annual_maximum(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'series.csv'
            path.write_text('time,hs_m\n2020-01-01T00:00Z,1\n2020-01-01T01:00Z,2\n2020-01-01T02:00Z,3\n2020-01-01T03:00Z,4\n')
            climate=build_climate(path,'ERA5')
        rows,summary=compare_waves([{'hs_m':3}],climate)
        self.assertEqual(rows[0]['hs_percentile'],75)
        self.assertEqual(climate['annual_maxima']['2020']['hs_m'],4)
        self.assertEqual(summary['status'],'available')
        self.assertNotIn('hs_sorted_m',summary)

    def test_profiles_use_only_the_explicit_elevation_band(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profiles.csv'
            path.write_text('transect_id,x_m,z_m\na,0,0\na,10,0.5\na,20,1\na,30,5\nb,0,0\nb,10,0.7\nb,20,1.4\n')
            slopes=slopes_from_transects(path,0,1.5)
        self.assertAlmostEqual(slopes[0]['slope'],.05)
        self.assertAlmostEqual(slopes[1]['slope'],.07)
        self.assertEqual(slopes[0]['n_points'],3)

    def test_year_chunks_have_no_missing_or_duplicate_days(self):
        chunks=year_chunks(dt.date(1991,2,3),dt.date(2020,12,31))
        self.assertEqual(chunks[0][0],dt.date(1991,2,3))
        self.assertEqual(chunks[-1][1],dt.date(2020,12,31))
        for a,b in zip(chunks,chunks[1:]):
            self.assertEqual(a[1]+dt.timedelta(days=1),b[0])

    def test_era5_uses_cache_and_keeps_mean_period_separate(self):
        import pandas as pd
        import xarray as xr
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'fixture.nc'
            ds=xr.Dataset({'swh':('valid_time',np.ones(24)),'mwp':('valid_time',np.ones(24)*7),'mwd':('valid_time',np.ones(24)*135)},
                          coords={'valid_time':pd.date_range('2020-01-01',periods=24,freq='h'),'latitude':44.0,'longitude':8.5})
            ds.to_netcdf(source,engine='h5netcdf')
            class Client:
                calls=0
                def retrieve(self,dataset,request,target):
                    self.calls+=1
                    shutil.copyfile(source,target)
            client=Client()
            loc={'wave_point':{'latitude':44,'longitude':8.5}}
            first,metadata=download_series(loc,dt.date(2020,1,1),dt.date(2020,1,1),Path(folder)/'cache',client=client,cell=(8.5,44))
            second,_=download_series(loc,dt.date(2020,1,1),dt.date(2020,1,1),Path(folder)/'cache',client=client,cell=(8.5,44))
            self.assertEqual(client.calls,1)
            self.assertEqual(len(first),24)
            self.assertEqual(metadata['missing_hs_records'],0)
            self.assertIn('tm_s',first)
            self.assertNotIn('tp_s',first)


if __name__=='__main__':
    unittest.main()
