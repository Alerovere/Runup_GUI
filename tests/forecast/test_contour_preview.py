import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from forecast_service.contour_preview import reach_lines, preview_from_grid


class ContourPreviewTests(unittest.TestCase):
    def test_internal_island_has_no_outline_and_no_cells_are_filled(self):
        wet=np.zeros((12,12),bool);wet[2:10,2:10]=True;wet[5:7,5:7]=False
        original_wet=wet.copy();valid=np.ones_like(wet)
        line,regularized,meta=reach_lines(wet,valid,tolerance_m=0)
        self.assertEqual(line.length,32.)
        self.assertTrue(line.equals(regularized))
        self.assertEqual(meta['internal_components_not_drawn'],1)
        self.assertEqual(meta['filled_cells'],0)
        self.assertFalse(meta['mask_modified'])
        self.assertTrue(np.array_equal(wet,original_wet))

    def test_open_dry_channel_is_not_closed(self):
        wet=np.zeros((12,12),bool);wet[2:10,2:10]=True
        wet[2:7,5:7]=False
        line,_,meta=reach_lines(wet,np.ones_like(wet),tolerance_m=0)
        self.assertEqual(meta['internal_components_not_drawn'],0)
        self.assertGreater(line.length,32.)

    def test_all_wet_or_no_data_boundary_does_not_become_a_front(self):
        for wet in [np.ones((8,8),bool),np.zeros((8,8),bool)]:
            line,_,meta=reach_lines(wet,np.ones_like(wet))
            self.assertTrue(line.is_empty)
            self.assertTrue(meta['empty'])
        valid=np.zeros((8,8),bool);valid[2:6,2:6]=True
        line,_,_=reach_lines(valid,valid)
        self.assertTrue(line.is_empty)

    def test_display_crop_does_not_create_a_boundary(self):
        wet=np.zeros((8,10),bool);wet[:,:6]=True
        display=np.zeros_like(wet);display[:,2:5]=True
        line,_,_=reach_lines(wet,np.ones_like(wet),display_mask=display)
        self.assertTrue(line.is_empty)
        display[:,5:7]=True
        line,_,_=reach_lines(wet,np.ones_like(wet),display_mask=display,tolerance_m=0)
        self.assertEqual(line.length,8.)

    def test_simplification_reduces_steps_within_tolerance(self):
        wet=np.zeros((24,20),bool)
        for row in range(24):wet[row,:4+row//4]=True
        valid=np.ones_like(wet);before=wet.copy()
        original,simple,meta=reach_lines(wet,valid,tolerance_m=.8)
        self.assertLess(meta['simplified_vertices'],meta['original_vertices'])
        self.assertLessEqual(original.hausdorff_distance(simple),.8+1e-9)
        self.assertTrue(np.array_equal(wet,before))

    def test_ground_units_and_mask_validation(self):
        wet=np.zeros((6,8),bool);wet[:,:3]=True
        original,_,_=reach_lines(wet,np.ones_like(wet),pixel_size_m=(2.,3.),tolerance_m=0)
        self.assertEqual(original.length,18.)
        for kwargs in [dict(pixel_size_m=(0,1)),dict(pixel_size_m=(float('nan'),1)),dict(tolerance_m=-1)]:
            with self.assertRaises(ValueError):reach_lines(wet,np.ones_like(wet),**kwargs)
        with self.assertRaises(ValueError):reach_lines(wet,np.ones((2,2),bool))
        with self.assertRaises(ValueError):reach_lines(wet,np.zeros_like(wet))

    def test_grid_preview_is_read_only_and_geojson_is_geographic(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'grid.npz'
            z=np.tile(np.arange(20,dtype='float32')*.1,(16,1))
            seeds=np.zeros(z.shape,bool);seeds[:,0]=True
            display=np.ones(z.shape,bool)
            np.savez_compressed(path,z=z,seeds=seeds,display_mask=display,bounds=np.array([8.24,44.10,8.241,44.101]))
            digest=hashlib.sha256(path.read_bytes()).hexdigest();before=z.copy()
            a,b,meta=preview_from_grid(path,level_m=.8,tolerance_m=.5)
            self.assertEqual(a['type'],'FeatureCollection')
            self.assertTrue(a['features'])
            self.assertTrue(b['features'])
            self.assertTrue(meta['display_only'])
            self.assertEqual(meta['grid_sha256'],digest)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
            np.testing.assert_array_equal(np.load(path)['z'],before)
            self.assertIn('coordinates',a['features'][0]['geometry'])
            json.dumps([a,b,meta],allow_nan=False)
            a,b,meta=preview_from_grid(path,level_m=-1)
            self.assertFalse(a['features']);self.assertFalse(b['features'])
            self.assertEqual(meta['seeds_below_level'],0)


if __name__=='__main__':unittest.main()
