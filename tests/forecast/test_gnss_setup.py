import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from forecast_service.gnss_setup import inspect_gnss,extract_gnss_profiles,analyze_gnss_transects,gnss_map_profiles,GNSS_OLS_METHOD,GNSS_ATTRIBUTE_METHOD


def write(path,coordinates=None,properties=None):
    path.write_text(json.dumps(dict(type='FeatureCollection',crs=dict(type='name',properties=dict(name='EPSG:32632')),
        features=[dict(type='Feature',properties=properties or dict(transect_id=1,tan_beta=.1,r2=.99),
        geometry=dict(type='LineString',coordinates=coordinates if coordinates is not None else [[500000.,4880000.,-1.],[500002.,4880000.,-.8],[500004.,4880000.,-.6]]))])))
    return path


@unittest.skipUnless(importlib.util.find_spec('pyproj'),'PyProj richiesto dal setup opzionale.')
class GNSSTests(unittest.TestCase):
    def test_all_xyz_vertices_are_used_without_dem_or_elevation_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write(Path(folder)/'gnss.geojson')
            frame,report,meta=extract_gnss_profiles(path,geojson_crs='EPSG:32632',slope_field='tan_beta',r2_field='r2')
            summary,profiles,masks=analyze_gnss_transects(frame,references=meta['references'])
            self.assertEqual(len(frame),3);self.assertEqual(report.n_points.iloc[0],3)
            np.testing.assert_array_equal(frame.SAMPLE_1,[-1.,-.8,-.6])
            self.assertAlmostEqual(summary.slope.iloc[0],.1)
            self.assertEqual(summary.method.iloc[0],GNSS_OLS_METHOD)
            self.assertIsNone(summary.z_min_m.iloc[0]);self.assertIsNone(summary.z_max_m.iloc[0])
            self.assertTrue(masks['1'].all());self.assertEqual(len(profiles['1']),3)
            self.assertAlmostEqual(summary.provided_slope.iloc[0],.1)

    def test_short_reversed_profile_is_oriented_using_nonoverlapping_ends(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write(Path(folder)/'gnss.geojson',[[500004,4880000,-.6],[500002,4880000,-.8],[500000,4880000,-1.]])
            frame,_,_=extract_gnss_profiles(path,geojson_crs='EPSG:32632')
            summary,profiles,_=analyze_gnss_transects(frame)
            self.assertAlmostEqual(summary.slope.iloc[0],.1)
            self.assertTrue(summary.reversed.iloc[0]);self.assertFalse(summary.orientation_ambiguous.iloc[0])
            self.assertEqual(profiles['1'].SAMPLE_1.iloc[0],-1.)

    def test_supplied_beta_is_an_explicit_alternative_with_distinct_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write(Path(folder)/'gnss.geojson',properties=dict(code='a',beta=.2,quality=.98))
            frame,_,meta=extract_gnss_profiles(path,geojson_crs='EPSG:32632',id_field='code',slope_field='beta',r2_field='quality')
            fitted,_,_=analyze_gnss_transects(frame,references=meta['references'])
            supplied,_,_=analyze_gnss_transects(frame,references=meta['references'],slope_source='attribute')
            self.assertAlmostEqual(fitted.slope.iloc[0],.1);self.assertEqual(supplied.slope.iloc[0],.2)
            self.assertEqual(supplied.method.iloc[0],GNSS_ATTRIBUTE_METHOD)
            self.assertEqual(supplied.provided_r_squared.iloc[0],.98)
            self.assertNotEqual(supplied.r_squared.iloc[0],.98)

    def test_vertical_correction_changes_heights_but_not_slope(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write(Path(folder)/'gnss.geojson')
            original,_,_=extract_gnss_profiles(path,geojson_crs='EPSG:32632')
            shifted,_,meta=extract_gnss_profiles(path,geojson_crs='EPSG:32632',z_correction_m=10.)
            np.testing.assert_allclose(shifted.SAMPLE_1,original.SAMPLE_1+10)
            a,_,_=analyze_gnss_transects(original);b,_,_=analyze_gnss_transects(shifted)
            self.assertAlmostEqual(a.slope.iloc[0],b.slope.iloc[0])
            self.assertEqual(meta['z_correction_m'],10.)

    def test_curved_vertex_order_is_preserved_not_sorted_or_interpolated(self):
        with tempfile.TemporaryDirectory() as folder:
            coords=[[500000,4880000,0],[500002,4880000,.2],[500004,4880000,.4],[500003,4880000,.3]]
            frame,report,_=extract_gnss_profiles(write(Path(folder)/'gnss.geojson',coords),geojson_crs='EPSG:32632')
            summary,profiles,masks=analyze_gnss_transects(frame)
            self.assertTrue(report.curved_profile.iloc[0]);self.assertEqual(profiles['1'].x_mare.tolist(),[0,2,4,3])
            self.assertEqual(len(profiles['1']),4);self.assertTrue(masks['1'].all())
            self.assertAlmostEqual(summary.slope.iloc[0],.1)

    def test_missing_z_crs_mismatch_duplicate_ids_and_bad_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'gnss.geojson'
            for coords in ([[500000,4880000],[500001,4880000]],[[500000,4880000,0],[500001,4880000,None]]):
                with self.assertRaisesRegex(ValueError,'XYZ'):extract_gnss_profiles(write(path,coords),geojson_crs='EPSG:32632')
            write(path)
            with self.assertRaisesRegex(ValueError,'CRS dichiarato'):extract_gnss_profiles(path,geojson_crs='EPSG:4326')
            with self.assertRaisesRegex(ValueError,'identificativo assente'):extract_gnss_profiles(path,geojson_crs='EPSG:32632',id_field='missing')
            data=json.loads(path.read_text());data['features']*=2;path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'duplicato'):extract_gnss_profiles(path,geojson_crs='EPSG:32632')

    def test_invalid_fit_requires_explicit_correction_not_absolute_slope(self):
        with tempfile.TemporaryDirectory() as folder:
            frame,_,_=extract_gnss_profiles(write(Path(folder)/'gnss.geojson'),geojson_crs='EPSG:32632')
            summary,profiles,_=analyze_gnss_transects(frame,orientation='distance_increases_seaward')
            self.assertEqual(summary.status.iloc[0],'invalid');self.assertEqual(profiles,{})

    @unittest.skipUnless(importlib.util.find_spec('rasterio'),'Rasterio richiesto per la cartografia.')
    def test_map_starts_use_dem_heights_even_with_a_different_gnss_datum(self):
        import rasterio
        from rasterio.transform import from_origin
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=write(root/'gnss.geojson',[[500000.5,4879999.5,-100.],[500010.5,4879999.5,-99.]])
            dem=root/'dem.tif'
            with rasterio.open(dem,'w',driver='GTiff',height=2,width=20,count=1,dtype='float32',crs='EPSG:32632',transform=from_origin(500000,4880000,1,1)) as dst:
                dst.write(np.tile(np.arange(20,dtype=np.float32)*.2,(2,1)),1)
            frame,_,_=extract_gnss_profiles(path,geojson_crs='EPSG:32632')
            summary,profiles,_=analyze_gnss_transects(frame)
            maps,_,_=gnss_map_profiles(dem,path,profiles,profile_crs='EPSG:32632',geojson_crs='EPSG:32632',id_field='transect_id')
            self.assertAlmostEqual(summary.slope.iloc[0],.1)
            self.assertEqual(profiles['1'].SAMPLE_1.iloc[0],-100.)
            self.assertEqual(maps['1'].SAMPLE_1.iloc[0],0.)
            self.assertAlmostEqual(maps['1'].SAMPLE_1.iloc[-1],2.)
            write(path,[[500000.5,4879999.5,-100.],[500005.5,4879999.5,-99.5],[500003.5,4879999.5,-99.7]])
            curved,_,_=extract_gnss_profiles(path,geojson_crs='EPSG:32632')
            _,profiles,_=analyze_gnss_transects(curved)
            maps,_,_=gnss_map_profiles(dem,path,profiles,profile_crs='EPSG:32632',geojson_crs='EPSG:32632',id_field='transect_id')
            self.assertEqual(profiles['1'].x_mare.tolist(),[0.,5.,3.])
            self.assertTrue((np.diff(maps['1'].x_mare)>=0).all())
            self.assertAlmostEqual(maps['1'].x_mare.iloc[-1],7.)


@unittest.skipUnless(importlib.util.find_spec('ipywidgets') and importlib.util.find_spec('pyproj'),'Moduli del setup opzionale.')
class GNSSFormTests(unittest.TestCase):
    def test_fields_and_crs_are_selected_from_the_file(self):
        from forecast_service.gnss_forms import GNSSFieldEditor
        with tempfile.TemporaryDirectory() as folder:
            editor=GNSSFieldEditor(write(Path(folder)/'gnss.geojson'))
            values=editor.read()
            self.assertEqual(values['id_field'],'transect_id');self.assertEqual(values['geojson_crs'],'EPSG:32632')
            self.assertEqual(values['slope_field'],'tan_beta');self.assertEqual(values['r2_field'],'r2')
            editor.method.value='attribute';editor.slope.value=None
            with self.assertRaises(ValueError):editor.read()

    def test_gnss_has_no_zmin_zmax_controls_and_dem_retains_them(self):
        from forecast_service.gnss_forms import ProfileFitEditor
        gnss=ProfileFitEditor(gnss=True)
        self.assertIsNone(gnss.z_min);self.assertIsNone(gnss.z_max)
        self.assertIsNone(gnss.read()['z_min']);self.assertIsNone(gnss.read()['z_max'])
        dem=ProfileFitEditor(z_min=.2,z_max=1.2)
        self.assertEqual(dem.read()['z_min'],.2);self.assertEqual(dem.read()['z_max'],1.2)
        dem.z_min.value=2.
        with self.assertRaises(ValueError):dem.read()
