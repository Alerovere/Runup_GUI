from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import patch
import numpy as np
import xarray as xr
from forecast_service import pipeline as p

NOW=datetime(2026,11,5,16,tzinfo=timezone.utc)

class WaveMetadataTests(unittest.TestCase):
    def test_only_explicit_plausible_forecast_reference_is_used(self):
        ds=xr.Dataset(coords={'forecast_reference_time':np.datetime64('2026-11-05T12:00')})
        result=p.wave_cycle_reference(ds,NOW)
        self.assertEqual(result['forecast_reference_time'],'2026-11-05T12:00:00Z')
        self.assertEqual(result['forecast_reference_time_source'],'coordinate:forecast_reference_time')
        ds=xr.Dataset(attrs={'forecast_reference_time':'2026-11-05T00:00:00Z'})
        self.assertEqual(p.wave_cycle_reference(ds,NOW)['forecast_reference_time'],'2026-11-05T00:00:00Z')

    def test_archive_date_download_time_future_date_and_mixed_cycles_are_not_used(self):
        for attrs in ({'bulletin_date':'2023-11-01','bulletin_type':'analysis'},
                      {'downloaded_at':NOW.isoformat()},
                      {'forecast_reference_time':'2023-11-01T00:00:00Z'},
                      {'forecast_reference_time':'2026-11-05T20:00:00Z'},
                      {'forecast_reference_time':'2026-11-05'}):
            self.assertEqual(p.wave_cycle_reference(xr.Dataset(attrs=attrs),NOW),{})
        ds=xr.Dataset(coords={'forecast_reference_time':('record',np.array(['2026-11-05T00:00','2026-11-05T12:00'],dtype='datetime64[m]'))})
        self.assertEqual(p.wave_cycle_reference(ds,NOW),{})

    def test_completion_time_is_after_processing_start_and_fixed_clock_remains_reproducible(self):
        timeline=[NOW,NOW+timedelta(minutes=2)]
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return timeline.pop(0)
        with patch.object(p,'datetime',Clock),patch.object(p,'compute_runup',return_value={'Stockdon et al. (2006)':.8}):
            bulletin,_=p.build_bulletin(demo=True)
        self.assertEqual(bulletin['processing_started_at'],p.iso(NOW))
        self.assertEqual(bulletin['generated_at'],p.iso(NOW+timedelta(minutes=2)))
        with patch.object(p,'compute_runup',return_value={'Stockdon et al. (2006)':.8}):
            fixed,_=p.build_bulletin(demo=True,now=NOW)
        self.assertEqual(fixed['processing_started_at'],fixed['generated_at'])
        self.assertEqual(fixed['wave_model']['publication_hours_utc'],[6,20])

if __name__=='__main__':unittest.main()
