from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from forecast_service import pipeline as p
from forecast_service.inundation import build_map
from test_sectors_and_maps import grid,NOW
from test_inundation_geojson import bulletin


class MapEstimateTests(unittest.TestCase):
    def test_mean_is_mean_across_models_at_its_peak_not_time_average(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            rows[10]['twl_mean_m']=.8
            rows[25]['twl_p75_m']=2.
            rows[30]['twl_p95_m']=100.;rows[30]['twl_max_m']=1000.
            result,_=build_map(dict(name='Spiaggia',hourly=rows),b,mapping,root,'venezia','whole')
            mean,upper=result['layers']
            self.assertEqual(result['default_layer'],'mean')
            self.assertEqual([x['kind'] for x in result['layers']],['mean','central_upper'])
            self.assertEqual([x['level_m'] for x in result['layers']],[.8,2.])
            self.assertEqual(mean['peak_time'],rows[10]['time']);self.assertEqual(upper['peak_time'],rows[25]['time'])
            self.assertEqual(mean['peak_windows'],[dict(**{'from':p.parse_time(rows[10]['time']).isoformat(),'to':(NOW+timedelta(hours=11)).isoformat()})])
            self.assertIsNone(mean['percentile']);self.assertEqual(upper['percentile'],75)
            self.assertEqual(mean['statistic'],'twl_mean_m')

    def test_equal_peaks_are_grouped_as_actual_time_windows(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            for i in [2,3,8]:rows[i]['twl_mean_m']=.8
            result,_=build_map(dict(hourly=rows),b,mapping,root,'venezia','whole')
            windows=result['layers'][0]['peak_windows']
            self.assertEqual(windows,[{'from':(NOW+timedelta(hours=2)).isoformat(),'to':(NOW+timedelta(hours=4)).isoformat()},
                                      {'from':(NOW+timedelta(hours=8)).isoformat(),'to':(NOW+timedelta(hours=9)).isoformat()}])

    def test_level_below_seeds_has_explicit_quality_flag_without_hiding_other_view(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            for r in rows:r['twl_mean_m']=-2.
            result,assets=build_map(dict(hourly=rows),b,mapping,root,'venezia','whole')
            self.assertEqual(result['status'],'available')
            self.assertEqual(result['layers'][0]['seed_condition'],'below_seed_level')
            self.assertEqual(result['layers'][0]['cells'],0)
            self.assertGreater(result['layers'][1]['cells'],0)
            data=json.loads(assets[result['geojson_export']['files'][0]['url'].removeprefix('data/')])
            self.assertIsNone(data['features'][0]['geometry'])
            self.assertTrue(data['features'][0]['properties']['quality_note'])

    def test_kmz_has_both_estimates_dates_and_separate_visibility(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            rows[2]['twl_mean_m']=.8;rows[8]['twl_p75_m']=2.
            result,assets=build_map(dict(name='Spiaggia & test',hourly=rows),b,mapping,root,'venezia','whole')
            self.assertEqual(result['mobile_export']['status'],'available')
            raw=assets[result['mobile_export']['url'].removeprefix('data/')]
            with ZipFile(BytesIO(raw)) as a:
                self.assertEqual(a.namelist(),['doc.kml']);doc=ET.fromstring(a.read('doc.kml'))
            ns={'k':'http://www.opengis.net/kml/2.2'}
            folders=doc.findall('k:Document/k:Folder',ns)
            self.assertEqual([f.find('k:visibility',ns).text for f in folders],['1','0'])
            self.assertIn('media',folders[0].find('k:name',ns).text)
            self.assertIn('centrale',folders[1].find('k:name',ns).text)
            self.assertTrue(doc.findall('.//k:Polygon',ns));self.assertTrue(doc.findall('.//k:LineString',ns))
            self.assertTrue(any('2026' in e.text and 'CET' in e.text for e in doc.findall('.//k:Placemark/k:name',ns)))
            values={d.attrib['name']:d.find('k:value',ns).text for d in doc.findall('.//k:ExtendedData/k:Data',ns)}
            self.assertIn('peak_time_utc',values);self.assertIn('forecast_from_utc',values)
            self.assertEqual(values['data_mode'],'demo')
