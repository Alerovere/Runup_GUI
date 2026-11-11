import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from forecast_service.geospatial_setup import extract_dem_profiles, sectors_from_beachfaces
from forecast_service.site_setup import analyze_transects

HAS_GEO = all(importlib.util.find_spec(name) for name in ('rasterio', 'pyproj', 'shapely'))


def feature_collection(path, features):
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}))
    return path


def feature(identifier, coordinates, kind='LineString', field='TR_ID'):
    return {'type': 'Feature', 'properties': {field: identifier, 'name': identifier},
            'geometry': {'type': kind, 'coordinates': coordinates}}


@unittest.skipUnless(HAS_GEO, 'Rasterio, PyProj e Shapely richiesti dal setup opzionale.')
class GeoSetupTests(unittest.TestCase):
    def inputs(self, folder, scale=1.):
        import rasterio
        from rasterio.transform import from_origin
        root = Path(folder); dem = root/'full-dem.tif'
        z = np.tile(np.arange(100, dtype=np.float32)*.05, (40, 1))
        z[10, 5] = -9999
        with rasterio.open(dem, 'w', driver='GTiff', height=40, width=100, count=1, dtype='float32', crs='EPSG:32632', transform=from_origin(500000, 4880000, 1, 1), nodata=-9999) as dst:
            dst.write(z, 1); dst.scales = [scale]
        lines = feature_collection(root/'transects.geojson', [
            feature('A', [[500000.5, 4879989.5], [500080.5, 4879989.5]]),
            feature('B', [[500080.5, 4879969.5], [500000.5, 4879969.5]])])
        return root, dem, lines

    def extract(self, dem, lines, **kwargs):
        return extract_dem_profiles(dem, lines, profile_crs='EPSG:32632', geojson_crs='EPSG:32632', **kwargs)

    def test_extraction_orientation_nodata_and_original_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            _, dem, lines = self.inputs(folder)
            points, report, metadata = self.extract(dem, lines)
            self.assertAlmostEqual(metadata['step_m'], 1.)
            self.assertEqual(report.missing_z.tolist(), [1, 0])
            self.assertTrue(np.isnan(points[(points.TR_ID == 'A') & (points.distance == 5)].SAMPLE_1.iloc[0]))
            summary, profiles, masks = analyze_transects(points, 0, 1)
            self.assertEqual(summary.status.tolist(), ['valid', 'valid'])
            np.testing.assert_allclose(summary.slope, [.05, .05], atol=1e-10)
            self.assertTrue(profiles['B'].attrs['reversed'])
            self.assertEqual(profiles['A'].loc[masks['A'], 'X'].max(), 500020.5)

    def test_geojson_z_is_ignored_and_dem_scale_applied_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root, dem, lines = self.inputs(folder, scale=2.)
            feature_collection(lines, [feature('A', [[500000.5, 4879989.5, 900], [500010.5, 4879989.5, 900]])])
            points, _, metadata = self.extract(dem, lines, step_m=2)
            self.assertAlmostEqual(points.SAMPLE_1.iloc[0], 0.)
            self.assertAlmostEqual(points.SAMPLE_1.iloc[-1], 1.)
            self.assertEqual(metadata['dem_scale'], 2.)

    def test_outside_extent_is_nodata_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            _, dem, lines = self.inputs(folder)
            feature_collection(lines, [feature('outside', [[499998.5, 4879989.5], [500005.5, 4879989.5]])])
            points, report, _ = self.extract(dem, lines)
            self.assertEqual(report.outside_dem.iloc[0], 2)
            self.assertTrue(points.SAMPLE_1.iloc[:2].isna().all())

    def test_bad_ids_disconnected_lines_and_crs_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            _, dem, lines = self.inputs(folder)
            data = json.loads(lines.read_text()); data['features'][1]['properties']['TR_ID'] = 'A'
            lines.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'duplicato'):
                self.extract(dem, lines)
            feature_collection(lines, [feature('A', [[[500000, 4880000], [500001, 4880000]], [[500003, 4880000], [500004, 4880000]]], 'MultiLineString')])
            with self.assertRaisesRegex(ValueError, 'continue'):
                self.extract(dem, lines)
            with self.assertRaisesRegex(ValueError, 'proiettato'):
                extract_dem_profiles(dem, lines, profile_crs='EPSG:4326')

    def area_file(self, root, overlapping=False):
        north_bottom = 4879960 if overlapping else 4879980
        return feature_collection(root/'areas.geojson', [
            feature('nord', [[[499999, north_bottom], [500100, north_bottom], [500100, 4880001], [499999, 4880001], [499999, north_bottom]]], 'Polygon', 'sector_id'),
            feature('sud', [[[499999, 4879950], [500100, 4879950], [500100, 4879980], [499999, 4879980], [499999, 4879950]]], 'Polygon', 'sector_id')])

    def test_sector_assignment_uses_fitted_beachface_and_keeps_full_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root, dem, lines = self.inputs(folder)
            points, _, _ = self.extract(dem, lines)
            _, profiles, selections = analyze_transects(points, 0, 1)
            sectors, polygons, report = sectors_from_beachfaces(self.area_file(root), profiles, selections, ['A', 'B'], geojson_crs='EPSG:32632')
            self.assertEqual(sectors['nord']['transect_ids'], ['A'])
            self.assertEqual(sectors['sud']['transect_ids'], ['B'])
            self.assertEqual(report.method.tolist(), ['beachface_midpoint', 'beachface_midpoint'])
            self.assertEqual(len(profiles['B']), 81)
            self.assertEqual(polygons['nord']['type'], 'Polygon')
            self.assertLess(polygons['nord']['coordinates'][0][0][0], 10.)

    def test_ambiguous_areas_need_explicit_assignment(self):
        with tempfile.TemporaryDirectory() as folder:
            root, dem, lines = self.inputs(folder)
            points, _, _ = self.extract(dem, lines)
            _, profiles, selections = analyze_transects(points, 0, 1)
            areas = self.area_file(root, overlapping=True)
            with self.assertRaisesRegex(ValueError, '2 settori'):
                sectors_from_beachfaces(areas, profiles, selections, ['A', 'B'], geojson_crs='EPSG:32632')
            sectors, _, report = sectors_from_beachfaces(areas, profiles, selections, ['A', 'B'], geojson_crs='EPSG:32632', manual={'B': 'sud'})
            self.assertEqual(sectors['sud']['transect_ids'], ['B'])
            self.assertEqual(report.method.tolist(), ['beachface_midpoint', 'manual'])

    def test_full_area_dem_is_cropped_with_margin_only_at_preprocessing(self):
        from forecast_service.mapping_setup import prepare_mapping
        from forecast_service.inundation import load_grid
        from pyproj import Transformer
        with tempfile.TemporaryDirectory() as folder:
            root, dem, _ = self.inputs(folder)
            converter = Transformer.from_crs(32632, 4326, always_xy=True)
            ring = [converter.transform(*point) for point in [(500010, 4879985), (500025, 4879985), (500025, 4879995), (500010, 4879995), (500010, 4879985)]]
            polygon = {'type': 'Polygon', 'coordinates': [ring]}
            metadata, assets = prepare_mapping(dem, root/'out', slug='test', display_polygon=polygon,
                seed_points=[converter.transform(500011, 4879990)], survey_credit='DEMO', survey_date='2026', license='Test',
                vertical_reference='Zero DEMO', vertical_alignment_confirmed=True, clip_to_polygon=True, clip_buffer_m=10)
            z, seeds, display, bounds = load_grid(assets['cartography/whole/grid.npz'])
            self.assertLess(z.shape[1], 100)
            self.assertTrue(seeds.any())
            self.assertTrue((~display).any())
            self.assertEqual(metadata['clip_buffer_m'], 10)

    def test_orthophoto_has_independent_metric_resolution_and_transparent_uncovered_areas(self):
        import rasterio
        from rasterio.transform import from_origin
        from rasterio.io import MemoryFile
        from pyproj import Transformer
        from forecast_service.mapping_setup import prepare_mapping
        from forecast_service.site_package import validate_cartography
        with tempfile.TemporaryDirectory() as folder:
            root, dem, _ = self.inputs(folder)
            ortho = root/'full-ortho.tif'
            with rasterio.open(ortho, 'w', driver='GTiff', height=40, width=50, count=3, dtype='uint8', crs='EPSG:32632', transform=from_origin(500000, 4880000, 1, 1)) as dst:
                dst.write(np.zeros((3, 40, 50), dtype=np.uint8))
            original = dem.read_bytes(), ortho.read_bytes()
            converter = Transformer.from_crs(32632, 4326, always_xy=True)
            ring = [converter.transform(*point) for point in [(500001, 4879961), (500099, 4879961), (500099, 4879999), (500001, 4879999), (500001, 4879961)]]
            args = dict(slug='test', orthophoto_path=ortho, display_polygon={'type': 'Polygon', 'coordinates': [ring]},
                        seed_points=[converter.transform(500002, 4879990)], survey_credit='DEMO', survey_date='2026', license='Test',
                        vertical_reference='Zero DEMO', vertical_alignment_confirmed=True, max_dimension=32)
            metadata, assets = prepare_mapping(dem, root/'out', orthophoto_resolution_m=.5, **args)
            self.assertGreater(metadata['orthophoto_shape'][1], metadata['prepared_grid_shape'][1])
            self.assertTrue(all(res <= .5 for res in metadata['orthophoto_ground_resolution_m']))
            with MemoryFile(assets['cartography/whole/orthophoto.png'].read_bytes()) as memory:
                with memory.open() as image:
                    rgba = image.read()
            self.assertTrue((rgba[3] == 0).any())
            self.assertTrue((rgba[3] == 255).any())
            self.assertTrue((rgba[:3, rgba[3] == 255] == 0).all())
            validate_cartography(assets, {'mapping': metadata})
            self.assertEqual(original, (dem.read_bytes(), ortho.read_bytes()))
            with self.assertRaisesRegex(ValueError, '4096'):
                prepare_mapping(dem, root/'too-large', orthophoto_resolution_m=.005, **args)


if __name__ == '__main__':
    unittest.main()
