import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import xarray as xr

from forecast_service.sealevel_reference import (DATASET_ID,apply_reference,build_reference,
    download_reference,validate_location_reference,validate_reference)
from forecast_service.sealevel import fetch_sealevel,align_sealevel


class HistoricalReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.point={'latitude':44.08,'longitude':8.33}
        cls.cell={'latitude':44.0625,'longitude':8.333333015441895}
        start=datetime(2025,1,1,tzinfo=timezone.utc)
        cls.records=[{'time':(start+timedelta(hours=i)).isoformat(),'ssh_m':-.5 if i%2 else -.3} for i in range(8760)]
        cls.reference=build_reference(cls.records,2025,cls.point,cls.cell,dataset_version='202511')

    def test_complete_negative_reference_is_a_fixed_annual_mean(self):
        ref=self.reference
        self.assertAlmostEqual(ref['mean_ssh_m'],-.4)
        self.assertEqual(ref['n_records'],8760)
        self.assertEqual(sum(m['n_records'] for m in ref['monthly'].values()),8760)
        self.assertEqual(ref['local_datum_status'],'not_validated')
        with self.assertRaises(ValueError): build_reference(self.records[:-1],2025,self.point,self.cell,dataset_version='202511')
        bad=self.records[:-1]+[self.records[0]]
        with self.assertRaises(ValueError): build_reference(bad,2025,self.point,self.cell,dataset_version='202511')

    def test_location_and_cell_changes_require_a_new_reference(self):
        location=apply_reference({'wave_point':self.point},self.reference)
        self.assertAlmostEqual(location['mean_reference_m'],-.4)
        validate_location_reference(location,dataset_id=DATASET_ID,selected_point=self.cell)
        moved=copy.deepcopy(location);moved['wave_point']['longitude']+=.1
        with self.assertRaisesRegex(ValueError,'punto'):validate_location_reference(moved)
        with self.assertRaisesRegex(ValueError,'cella'):validate_location_reference(location,selected_point={'latitude':44.,'longitude':8.5})
        with self.assertRaisesRegex(ValueError,'dataset'):validate_location_reference(location,dataset_id='another_dataset')
        mismatch=copy.deepcopy(location);mismatch['mean_reference_m']=0
        with self.assertRaisesRegex(ValueError,'coincidono'):validate_location_reference(mismatch)

    def test_forecast_pins_the_product_version_and_never_downloads_mdt(self):
        location=apply_reference({'wave_point':self.point},self.reference)
        sea=xr.Dataset({'zos':(('time','latitude','longitude'),np.array([-.5,-.3]).reshape(2,1,1))},
                       coords={'time':['2026-11-05T00:00','2026-11-05T01:00'],'latitude':[self.cell['latitude']],'longitude':[self.cell['longitude']]})
        with patch.dict('os.environ',{'COPERNICUSMARINE_USERNAME':'test','COPERNICUSMARINE_PASSWORD':'test'}),patch('copernicusmarine.open_dataset',return_value=sea) as request:
            records,mean,metadata=fetch_sealevel(location,{'dataset_id':DATASET_ID},datetime(2026,11,5,tzinfo=timezone.utc),2)
        self.assertEqual(request.call_count,1)
        self.assertEqual(request.call_args.kwargs['dataset_version'],'202511')
        self.assertEqual(metadata['reference_source'],'copernicus_historical_mean')
        self.assertEqual(metadata['historical_reference']['year'],2025)
        waves=[{'time':r['time']} for r in records]
        levels=align_sealevel(waves,records,mean)
        self.assertAlmostEqual(levels[0]['water_level_m'],-.1)
        self.assertAlmostEqual(levels[1]['water_level_m'],.1)

    def test_download_validates_a_full_year_and_reuses_cache_without_credentials(self):
        times=np.arange(np.datetime64('2025-01-01T00'),np.datetime64('2026-01-01T00'),np.timedelta64(1,'h'))
        ds=xr.Dataset({'zos':(('time','latitude','longitude'),np.full((8760,1,1),-.4))},
                      coords={'time':times,'latitude':[self.cell['latitude']],'longitude':[self.cell['longitude']]})
        catalogue=SimpleNamespace(products=[SimpleNamespace(datasets=[SimpleNamespace(dataset_id=DATASET_ID,versions=[SimpleNamespace(label='202511')])])])
        location={'wave_point':self.point}
        with tempfile.TemporaryDirectory() as folder,patch('copernicusmarine.describe',return_value=catalogue) as describe,patch('copernicusmarine.open_dataset',return_value=ds) as request:
            first=download_reference(location,2025,'test','test',cache=folder)
            second=download_reference(location,2025,None,None,cache=folder)
            self.assertEqual(first,second)
            self.assertEqual(request.call_count,1)
            self.assertEqual(describe.call_count,1)
            self.assertEqual(request.call_args.kwargs['dataset_version'],'202511')

    def test_stored_borghetto_reference_is_complete_and_matches_the_location(self):
        from forecast_service.pipeline import ROOT,load_configuration
        locations,_=load_configuration()
        location=locations['locations']['borghetto-santo-spirito']
        reference=json.loads((ROOT/'config/study_sites/borghetto-santo-spirito/sea_level_reference_2025.json').read_text())
        validate_reference(reference,location=location,dataset_id=DATASET_ID)
        self.assertEqual(location['sea_level_reference'],reference)
        self.assertEqual(reference['year'],2025)
        self.assertAlmostEqual(reference['mean_ssh_m'],-.4032,places=4)


if __name__=='__main__': unittest.main()
