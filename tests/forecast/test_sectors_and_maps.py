import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from forecast_service import pipeline as p
from forecast_service.sectors import resolve_sectors, validate_mappings
from forecast_service.inundation import connected_mask, build_map, load_grid, png_bytes
from forecast_service.site_package import write_site_package, import_site_package

NOW = datetime(2026, 11, 11, 6, tzinfo=timezone.utc)


def config(root):
    (root/'config').mkdir(parents=True)
    for name in ('locations.json', 'impact_thresholds.json'):
        shutil.copyfile(p.ROOT/'config'/name, root/'config'/name)
    shutil.copytree(p.ROOT/'config/climatology', root/'config/climatology', dirs_exist_ok=True)
    # This isolated fixture must not inherit newly imported surveys, hundreds of
    # Monte Carlo slopes, or map paths whose files are absent from the fixture.
    fixture=json.loads((root/'config/locations.json').read_text())
    for location in fixture['locations'].values():
        for field in ('sectors','mapping','slope_sampling','transects'):
            location.pop(field,None)
        location['slopes']=[.03,.05,.07]
    (root/'config/locations.json').write_text(json.dumps(fixture))
    locations, impacts = p.load_configuration(root)
    loc = locations['locations']['venezia']
    loc['transects'] = [{'transect_id': 'a', 'slope': .03, 'status': 'valid'}, {'transect_id': 'b', 'slope': .09, 'status': 'valid'}]
    loc['slopes'] = [.03, .09]
    loc['sectors'] = {'ovest': {'name': 'Ovest', 'transect_ids': ['a']}, 'est': {'name': 'Est', 'transect_ids': ['b']}}
    (root/'config/locations.json').write_text(json.dumps(locations))
    return locations, impacts


def grid(root, unit='whole'):
    folder = root/f'config/study_sites/venezia/cartography/{unit}'
    folder.mkdir(parents=True, exist_ok=True)
    # An enclosed depression behind a wall must stay dry.
    z = np.array([[-1, 0, 3, 0], [-1, 0, 3, 0], [-1, 0, 3, 0]], dtype=np.float32)
    seeds = np.zeros(z.shape, dtype=bool); seeds[1, 0] = True
    display = np.ones(z.shape, dtype=bool)
    np.savez_compressed(folder/'grid.npz', z=z, seeds=seeds, display_mask=display, bounds=np.array([12., 45., 12.01, 45.01]))
    mapping = dict(grid_file=str((folder/'grid.npz').relative_to(root)), orthophoto_file=None,
                   survey_credit='Rilievo dimostrativo Autore', survey_date='2026-01-01', license='CC BY 4.0',
                   vertical_reference='Zero di prova comune a DEM e TWL', dem_offset_m=0., vertical_alignment_confirmed=True)
    return mapping, folder


class SectorTests(unittest.TestCase):
    def test_legacy_location_and_empty_sectors_have_same_results(self):
        locations, impacts = p.load_configuration()
        loc = locations['locations']['venezia']
        self.assertEqual(resolve_sectors(loc, impacts['locations']['venezia']['thresholds']), {})
        self.assertEqual(resolve_sectors(dict(loc, sectors={}), impacts['locations']['venezia']['thresholds']), {})

    def test_forcing_is_reused_but_slopes_thresholds_and_statistics_are_local(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); locations, impacts = config(root)
            with patch.object(p, 'demonstration_waves', wraps=p.demonstration_waves) as fetch:
                bulletin, csvs = p.build_bulletin(root=root, demo=True, now=NOW)
            self.assertEqual(fetch.call_count, len(locations['locations']))
            beach = bulletin['locations']['venezia']; a = beach['sectors']['ovest']; b = beach['sectors']['est']
            self.assertEqual(a['slopes'], [.03]); self.assertEqual(b['slopes'], [.09])
            for key in ('time', 'hs_m', 'tp_s', 'water_level_m'):
                self.assertEqual(a['hourly'][0][key], b['hourly'][0][key])
            self.assertNotEqual(a['hourly'][0]['twl_p95_m'], b['hourly'][0]['twl_p95_m'])
            expected, _ = p.summarize_records(beach['hourly'], a, a['thresholds'], a['summer_season'], 0)
            self.assertEqual(a['hourly'][0]['twl_p95_m'], expected[0]['twl_p95_m'])
            self.assertIn('venezia--ovest.csv', csvs)
            self.assertIn('included_in_summary', csvs['venezia--ovest.csv'].splitlines()[0])

    def test_missing_duplicate_unknown_and_unassigned_transects_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            locations, impacts = config(Path(folder)); loc = locations['locations']['venezia']; thresholds = impacts['locations']['venezia']['thresholds']
            for change in ({'est': {'name': 'Est', 'transect_ids': ['a']}}, {'est': {'name': 'Est', 'transect_ids': ['x']}}, {'est': {'name': 'Est', 'transect_ids': []}}):
                broken = copy.deepcopy(loc); broken['sectors'].update(change)
                with self.assertRaises(ValueError):
                    resolve_sectors(broken, thresholds)
            broken = copy.deepcopy(loc); del broken['sectors']['est']
            with self.assertRaisesRegex(ValueError, 'Ogni transetto'):
                resolve_sectors(broken, thresholds)

    def test_only_structures_change_and_exposure_is_common_to_area(self):
        with tempfile.TemporaryDirectory() as folder:
            locations, impacts = config(Path(folder)); loc = locations['locations']['venezia']; thresholds = impacts['locations']['venezia']['thresholds']
            custom = copy.deepcopy(thresholds); custom[2]['elevation_m'] = 1.2
            loc['wave_exposure']={'sectors_deg': [[70, 130]]}
            loc['sectors']['est'].update(thresholds=custom)
            units = resolve_sectors(loc, thresholds)
            self.assertEqual(units['est']['thresholds'][2]['elevation_m'], 1.2)
            self.assertEqual(units['ovest']['thresholds'][2]['elevation_m'], 1.1)
            self.assertEqual(units['est']['wave_exposure'], units['ovest']['wave_exposure'])
            loc['sectors']['est']['wave_exposure']={'sectors_deg': [[140, 200]]}
            with self.assertRaisesRegex(ValueError,'comune all’area'):
                resolve_sectors(loc,thresholds)


class MapTests(unittest.TestCase):
    def test_connectivity_does_not_fill_isolated_depressions_or_nodata(self):
        z = np.array([[-1, 0, 3, .2], [-1, np.nan, 3, .2], [-1, 0, 3, .2]])
        seeds = np.zeros(z.shape, dtype=bool); seeds[0, 0] = True
        mask = connected_mask(z, seeds, 1.)
        self.assertTrue(mask[:, 0].all()); self.assertFalse(mask[:, 3].any()); self.assertFalse(mask[1, 1])
        self.assertTrue(connected_mask(z, seeds, 4.)[:, 3].all())

    def test_flood_is_computed_before_display_clipping(self):
        z = np.array([[0., 0., 0.], [0., 5., 0.], [0., 0., 0.]])
        seed = np.zeros((3, 3), dtype=bool); seed[0, 0] = True
        display = np.zeros((3, 3), dtype=bool); display[2, 2] = True
        self.assertTrue((connected_mask(z, seed, 1.) & display)[2, 2])

    def test_maps_use_fixed_96h_filtered_percentiles_not_raw_maximum(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); mapping, _ = grid(root)
            rows = [dict(time=p.iso(NOW+timedelta(hours=i)), twl_mean_m=.4,twl_p75_m=.5, twl_p95_m=1., twl_max_m=100.,
                         statistics_method=p.STATISTICS_METHOD, hs_m=1., direction_deg=90) for i in range(120)]
            rows[12]['twl_mean_m'] = .6; rows[95]['twl_p75_m'] = 2.; rows[96]['twl_p75_m'] = 99.; rows[96]['twl_mean_m']=99.
            bulletin = {'mode': 'demo', 'processing_started_at': p.iso(NOW), 'display_hours': 96}
            data, assets = build_map({'hourly': rows, 'wave_exposure': {'sectors_deg': [[70, 130]]}}, bulletin, mapping, root, 'venezia', 'whole')
            self.assertEqual([layer['level_m'] for layer in data['layers']], [.6, 2.])
            self.assertEqual(data['layers'][1]['peak_time'], rows[95]['time'])
            self.assertEqual(data['layers'][1]['cells'], 6)
            self.assertEqual(data['survey_credit'], mapping['survey_credit'])
            self.assertEqual(data['hours_non_frontal'], 0)
            self.assertEqual(data['hours_direction_unknown'], 0)
            self.assertTrue(all(raw.startswith(b'\x89PNG') for name,raw in assets.items() if name.endswith('.png')))
            self.assertEqual(data['geojson_export']['status'],'available')
            rows.pop(10)
            with self.assertRaisesRegex(ValueError, '96 ore'):
                build_map({'hourly': rows}, bulletin, mapping, root, 'venezia', 'whole')

    def test_optional_bad_map_does_not_stop_bulletin_and_no_map_is_default(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config(root)
            bulletin, csvs = p.build_bulletin(root=root, demo=True, now=NOW)
            loc = bulletin['locations']['venezia']; loc['mapping'], _ = grid(root)
            (root/loc['mapping']['grid_file']).unlink()
            p.write_bulletin(bulletin, csvs, root/'out', root=root)
            published = json.loads((root/'out/forecast.json').read_text())
            self.assertEqual(published['locations']['venezia']['inundation_map']['status'], 'unavailable')
            self.assertNotIn('inundation_map', published['locations']['borghetto-santo-spirito'])

    def test_vertical_alignment_and_credits_required(self):
        with tempfile.TemporaryDirectory() as folder:
            mapping, _ = grid(Path(folder))
            for field, value in [('vertical_alignment_confirmed', False), ('survey_credit', ''), ('grid_file', '../../bad.npz')]:
                bad = dict(mapping, **{field: value})
                with self.assertRaises(ValueError):
                    validate_mappings({'mapping': bad}, 'venezia')

    def test_package_roundtrip_keeps_sector_grid_orthophoto_and_credits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'source'; locations, impacts = config(root)
            loc = locations['locations']['venezia']; mapping, directory = grid(root, 'est')
            mapping['orthophoto_file'] = str((directory/'orthophoto.png').relative_to(root))
            (directory/'orthophoto.png').write_bytes(png_bytes(np.full((3, 4, 4), 255, dtype=np.uint8)))
            loc['sectors']['est']['mapping'] = mapping
            payload = dict(schema_version=1, slug='venezia', data_mode='study', location=loc, thresholds=impacts['locations']['venezia']['thresholds'])
            assets = {f'cartography/est/{name}': directory/name for name in ('grid.npz', 'orthophoto.png')}
            archive = write_site_package(Path(folder)/'site.zip', payload, cartography=assets)
            target = Path(folder)/'target'; config(target)
            import_site_package(archive, target, replace=True)
            result, _ = p.load_configuration(target)
            self.assertEqual(result['locations']['venezia']['sectors']['est']['mapping'], mapping)
            self.assertEqual((target/mapping['grid_file']).read_bytes(), (root/mapping['grid_file']).read_bytes())
            with self.assertRaisesRegex(ValueError, 'Allegati cartografici'):
                write_site_package(Path(folder)/'bad.zip', payload)


class RasterPreparationTests(unittest.TestCase):
    def test_prepare_geotiffs_applies_offset_once_and_preserves_nodata(self):
        try:
            import rasterio
        except ImportError:
            self.skipTest('Rasterio è richiesto soltanto dal setup opzionale.')
        from rasterio.transform import from_bounds
        from forecast_service.mapping_setup import prepare_mapping
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); dem = root/'dem.tif'; ortho = root/'ortho.tif'
            transform = from_bounds(12, 45, 12.01, 45.01, 32, 32)
            z = np.zeros((32, 32), dtype=np.float32); z[0, 0] = -9999
            with rasterio.open(dem, 'w', driver='GTiff', height=32, width=32, count=1, dtype='float32', crs='EPSG:4326', transform=transform, nodata=-9999) as dst:
                dst.write(z, 1)
            with rasterio.open(ortho, 'w', driver='GTiff', height=32, width=32, count=3, dtype='uint8', crs='EPSG:4326', transform=transform) as dst:
                dst.write(np.full((3, 32, 32), 140, dtype=np.uint8))
            metadata, assets = prepare_mapping(dem, root/'prepared', slug='venezia', orthophoto_path=ortho,
                display_polygon={'type': 'Polygon', 'coordinates': [[[12, 45], [12.01, 45], [12.01, 45.01], [12, 45.01], [12, 45]]]},
                seed_points=[[12.005, 45.005]], survey_credit='Autore DEM e ortofoto', survey_date='2026-01-01', license='CC BY 4.0',
                vertical_reference='Zero comune confermato', dem_offset_m=.2, vertical_alignment_confirmed=True, max_dimension=32)
            prepared, seeds, display, bounds = load_grid(assets['cartography/whole/grid.npz'])
            self.assertTrue(np.isnan(prepared[0, 0])); self.assertAlmostEqual(float(prepared[10, 10]), .2, places=6)
            self.assertTrue(seeds.any()); self.assertTrue(display.all())
            self.assertIn('cartography/whole/orthophoto.png', assets)


if __name__ == '__main__':
    unittest.main()
