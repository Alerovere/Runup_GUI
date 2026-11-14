from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from forecast_service import pipeline as p
from forecast_service.inundation import build_map,write_maps
from forecast_service.inundation_geojson import area_geometry,limit_geometry
from test_sectors_and_maps import grid,NOW


def bulletin():
    rows=[dict(time=p.iso(NOW+timedelta(hours=i)),twl_p75_m=.5,twl_p95_m=1.,
        statistics_method=p.STATISTICS_METHOD,hs_m=1.,direction_deg=90) for i in range(96)]
    return dict(mode='demo',processing_started_at='2026-11-11T08:42:17+02:00',generated_at='2026-11-11T06:43:00Z',display_hours=96),rows


class GeoJSONTests(unittest.TestCase):
    def test_geojson_polygons_match_cells_preserve_holes_and_are_wgs84(self):
        from rasterio.warp import transform_geom
        from rasterio.features import rasterize
        from shapely.geometry import shape
        from forecast_service.inundation_geojson import _coordinates
        mask=np.zeros((8,10),bool);mask[1:7,1:7]=True;mask[3:5,3:5]=False;mask[1,8]=True
        before=mask.copy();bounds=[[44.,8.],[44.001,8.002]]
        geo=area_geometry(mask,bounds)
        self.assertEqual(geo['type'],'MultiPolygon');self.assertTrue(shape(geo).is_valid)
        self.assertTrue(any(len(polygon)>1 for polygon in geo['coordinates']))
        self.assertTrue(all(8<=x<=8.0021 and 43.9999<=y<=44.0011 for polygon in geo['coordinates'] for ring in polygon for x,y in ring))
        projected=transform_geom('EPSG:4326','EPSG:3857',geo)
        transform,_,_=_coordinates(mask.shape,bounds)
        recovered=rasterize([(projected,1)],out_shape=mask.shape,transform=transform)
        np.testing.assert_array_equal(recovered,mask)
        np.testing.assert_array_equal(before,mask)
        self.assertIsNone(area_geometry(np.zeros_like(mask),bounds))

    def test_diagonal_cells_and_touching_holes_form_valid_polygons(self):
        from shapely.geometry import shape
        for mask in [np.eye(6,dtype=bool),np.array([[1,1,1],[1,0,1],[1,1,0]],dtype=bool)]:
            geo=area_geometry(mask,[[44.,8.],[44.001,8.001]])
            self.assertTrue(shape(geo).is_valid)

    def test_lines_omit_nodata_and_grid_edges_and_do_not_modify_masks(self):
        wet=np.ones((6,8),bool);valid=np.ones_like(wet);display=np.ones_like(wet)
        geo,report=limit_geometry(wet,valid,display,[[44.,8.],[44.001,8.001]],3.)
        self.assertIsNone(geo);self.assertEqual(report['filled_cells'],0)
        wet[:,4:]=False;valid[:,4:]=False
        before=wet.copy()
        geo,_=limit_geometry(wet,valid,display,[[44.,8.],[44.001,8.001]],3.)
        self.assertIsNone(geo);np.testing.assert_array_equal(wet,before)

    def test_export_has_both_estimates_issue_period_peak_datum_and_credits(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            rows[10]['twl_p95_m']=2.
            digest=hashlib.sha256((root/mapping['grid_file']).read_bytes()).hexdigest()
            result,assets=build_map(dict(name='Spiaggia',hourly=rows),b,mapping,root,'venezia','whole')
            export=result['geojson_export'];self.assertEqual(export['status'],'available')
            self.assertEqual({f['kind'] for f in export['files']},{'aree','limiti'})
            for file in export['files']:
                self.assertIn('20261111T064217Z',file['filename'])
                data=json.loads(assets[file['url'].removeprefix('data/')])
                self.assertEqual(len(data['features']),2)
                self.assertEqual([f['properties']['percentile'] for f in data['features']],[75,95])
                for feature,layer in zip(data['features'],result['layers']):
                    props=feature['properties']
                    self.assertEqual(props['issued_at_utc'],'2026-11-11T06:42:17+00:00')
                    self.assertEqual(props['forecast_from_utc'],NOW.isoformat())
                    self.assertEqual(props['forecast_to_utc'],(NOW+timedelta(hours=96)).isoformat())
                    self.assertEqual(props['peak_time_utc'],layer['peak_time'])
                    self.assertEqual(props['twl_level_m'],layer['level_m'])
                    self.assertEqual(props['cells'],layer['cells'])
                    self.assertEqual(props['data_mode'],'demo')
                    self.assertEqual(props['vertical_reference'],mapping['vertical_reference'])
                    self.assertEqual(props['survey_credit'],mapping['survey_credit'])
                    self.assertEqual(props['grid_sha256'],digest)
                    if file['kind']=='limiti':self.assertEqual(props['tolerance_m'],3.)
            self.assertEqual(hashlib.sha256((root/mapping['grid_file']).read_bytes()).hexdigest(),digest)

    def test_two_runs_have_different_filenames_and_retain_both_local_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            b['locations']={'venezia':dict(hourly=rows,mapping=mapping)}
            write_maps(b,root/'out',root)
            first=set((root/'out/maps/venezia').glob('*.geojson'))
            b['processing_started_at']='2026-11-11T06:42:18Z'
            write_maps(b,root/'out',root)
            all_files=set((root/'out/maps/venezia').glob('*.geojson'))
            self.assertEqual(len(first),2);self.assertEqual(len(all_files),4)
            self.assertTrue(first.issubset(all_files))

    def test_export_error_does_not_hide_valid_forecast_images(self):
        from shapely.errors import GEOSException
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root);b,rows=bulletin()
            with patch('forecast_service.inundation_geojson.export_geojson',side_effect=GEOSException('Prova errore GIS')):
                with self.assertLogs('forecast_service.inundation',level='WARNING'):
                    result,assets=build_map(dict(hourly=rows),b,mapping,root,'venezia','whole')
            self.assertEqual(result['status'],'available')
            self.assertEqual(result['geojson_export']['status'],'unavailable')
            self.assertEqual(len(result['layers']),2)
            self.assertFalse(any(name.endswith('.geojson') for name in assets))
