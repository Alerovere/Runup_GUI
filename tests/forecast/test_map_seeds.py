import unittest

import numpy as np
from pyproj import Transformer
from rasterio.transform import from_origin,xy

from forecast_service.mapping_setup import select_sea_seeds,SeedSelectionError


class SeaSeedTests(unittest.TestCase):
    def setUp(self):
        self.transform=from_origin(900000,5500000,1,1)
        self.to_wgs=Transformer.from_crs(3857,4326,always_xy=True)
        self.z=np.full((6,8),.1,dtype='float32')
        self.z[:,0]=np.nan

    def point(self,col,row=2):
        return list(self.to_wgs.transform(*xy(self.transform,row,col)))

    def profile(self):
        return {'T1':[[*self.point(0),0.,0.],[*self.point(1),1.,.1],[*self.point(2),2.,.2]]}

    def test_advance_is_on_the_same_profile_and_leaves_nodata_unchanged(self):
        before=self.z.copy()
        seeds,report=select_sea_seeds(self.z,self.transform,seed_profiles=self.profile())
        self.assertTrue(seeds[2,1]);self.assertEqual(seeds.sum(),1)
        self.assertEqual(report[0]['advance_m'],1.)
        np.testing.assert_array_equal(before,self.z)

    def test_manual_point_is_not_relocated(self):
        with self.assertRaisesRegex(ValueError,'manuale 1'):
            select_sea_seeds(self.z,self.transform,seed_points=[self.point(0)])

    def test_do_not_jump_past_source_crest(self):
        p=self.profile();p['T1'][1][3]=1.2
        with self.assertRaises(SeedSelectionError) as ctx:
            select_sea_seeds(self.z,self.transform,seed_profiles=p)
        self.assertEqual(ctx.exception.report[0]['transect_id'],'T1')

    def test_distance_limit_and_grid_height_limit_are_enforced(self):
        with self.assertRaises(SeedSelectionError):
            select_sea_seeds(self.z,self.transform,seed_profiles=self.profile(),max_advance_m=.5)
        self.z[:,1:]=2.
        with self.assertRaises(SeedSelectionError):
            select_sea_seeds(self.z,self.transform,seed_profiles=self.profile())

    def test_valid_initial_cell_is_preserved(self):
        self.z[2,0]=-.1
        seeds,report=select_sea_seeds(self.z,self.transform,seed_profiles=self.profile())
        self.assertTrue(seeds[2,0]);self.assertEqual(report[0]['status'],'iniziale')

    def test_unavailable_profile_is_not_silently_discarded(self):
        p=self.profile();p['T2']=[[*self.point(0,3),0.,0.]]
        with self.assertRaises(SeedSelectionError) as ctx:
            select_sea_seeds(self.z,self.transform,seed_profiles=p)
        self.assertEqual(len(ctx.exception.report),2)
        self.assertIsNone(ctx.exception.report[1]['selected_point'])

    def test_ambiguous_or_invalid_input_fails(self):
        with self.assertRaises(ValueError):
            select_sea_seeds(self.z,self.transform,seed_points=[self.point(1)],seed_profiles=self.profile())
        with self.assertRaises(ValueError):
            select_sea_seeds(self.z,self.transform,seed_profiles=self.profile(),max_rise_m=-1)
        with self.assertRaisesRegex(ValueError,'WGS84'):
            select_sea_seeds(self.z,self.transform,seed_points=[[439000,4880000]])


if __name__=='__main__':unittest.main()
