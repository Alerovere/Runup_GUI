from datetime import timedelta
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import numpy as np

from forecast_service.terrain_background import terrain_background
from forecast_service.inundation import build_map
from forecast_service import pipeline as p
from test_sectors_and_maps import grid,NOW


def decode(raw):
    w,h=struct.unpack('>II',raw[16:24]);data=b'';pos=8
    while pos<len(raw):
        size=struct.unpack('>I',raw[pos:pos+4])[0]
        if raw[pos+4:pos+8]==b'IDAT':data+=raw[pos+8:pos+8+size]
        pos+=12+size
    rows=np.frombuffer(zlib.decompress(data),dtype=np.uint8).reshape(h,1+4*w)
    return rows[:,1:].reshape(h,w,4)


class TerrainTests(unittest.TestCase):
    def test_nodata_and_outside_sector_are_transparent_without_altering_heights(self):
        z=np.array([[0.,1.,np.nan],[2.,3.,4.]])
        display=np.array([[True,True,True],[True,False,False]])
        before=z.copy();raw,scale=terrain_background(z,display)
        rgba=decode(raw)
        np.testing.assert_array_equal(rgba[:,:,3],[[255,255,0],[255,0,0]])
        np.testing.assert_equal(before,z)
        self.assertLess(scale['min_m'],scale['max_m'])
        self.assertFalse(np.array_equal(rgba[0,0,:3],rgba[1,0,:3]))

    def test_flat_dem_has_a_valid_single_colour_scale(self):
        raw,scale=terrain_background(np.ones((3,3)),np.ones((3,3),dtype=bool))
        self.assertEqual(scale['min_m'],1.);self.assertEqual(scale['max_m'],1.)
        self.assertTrue((decode(raw)[:,:,3]==255).all())

    def test_map_without_orthophoto_includes_background_and_legend(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mapping,_=grid(root)
            rows=[dict(time=p.iso(NOW+timedelta(hours=i)),twl_mean_m=.4,twl_p75_m=.5,twl_p95_m=1.,statistics_method=p.STATISTICS_METHOD) for i in range(96)]
            data,assets=build_map({'hourly':rows},{'mode':'demo','processing_started_at':p.iso(NOW),'display_hours':96},mapping,root,'venezia','whole')
            self.assertIsNone(data['orthophoto'])
            self.assertTrue(data['terrain'].endswith('-terrain.png'))
            self.assertEqual(len(data['terrain_scale']['colors']),5)
            self.assertIn(data['terrain'].removeprefix('data/'),assets)
