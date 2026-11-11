import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from forecast_service.structure_points import thresholds_from_structure_points

HAS_GEO = all(importlib.util.find_spec(name) for name in ('rasterio', 'pyproj', 'shapely'))


@unittest.skipUnless(HAS_GEO, 'Librerie GIS richieste dal setup opzionale.')
class StructurePointTests(unittest.TestCase):
    def inputs(self, directory, *, scale=1., offset=0.):
        import rasterio
        from rasterio.transform import from_origin
        from pyproj import Transformer
        from shapely.geometry import box, mapping
        from forecast_service.geospatial_setup import reproject_geometry
        root=Path(directory); dem=root/'full-dem.tif'
        z=np.tile(np.array([.2,.4,.6,.8,1.,1.2,1.4,1.6,1.8,2.],dtype='float32'),(6,1));z[0,0]=-9999
        with rasterio.open(dem,'w',driver='GTiff',height=6,width=10,count=1,dtype='float32',crs='EPSG:32632',transform=from_origin(500000,4880000,1,1),nodata=-9999) as dst:
            dst.write(z,1);dst.scales=[scale];dst.offsets=[offset]
        polygons={key:mapping(reproject_geometry(geom,32632,4326)) for key,geom in {
            'ponente':box(500000,4879994,500005,4880000),
            'levante':box(500005,4879994,500010,4880000)}.items()}
        to_wgs=Transformer.from_crs(32632,4326,always_xy=True)
        def point(name,col,row=2,**properties):
            x,y=to_wgs.transform(500000+col+.5,4880000-row-.5)
            return dict(type='Feature',properties=dict(struttura=name,**properties),geometry=dict(type='Point',coordinates=[x,y,999.]))
        path=root/'strutture.geojson'
        return dem,polygons,path,point

    def write_points(self,path,features):
        path.write_text(json.dumps(dict(type='FeatureCollection',features=features)))

    def test_means_group_by_sector_and_structure_not_whole_dem(self):
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            self.write_points(path,[point(' Chiosco ',1),point('chiosco',3),point('Chiosco',6),point('Accesso',7)])
            proposals,report,summary,meta=thresholds_from_structure_points(dem,path,polys)
            self.assertEqual([len(proposals[key]) for key in ('ponente','levante')],[1,2])
            west=proposals['ponente'][0]
            self.assertAlmostEqual(west['elevation_m'],.6,places=6)
            self.assertAlmostEqual(west['survey_statistics']['min_elevation_m'],.4,places=6)
            self.assertAlmostEqual(west['survey_statistics']['max_elevation_m'],.8,places=6)
            self.assertEqual(west['survey_statistics']['n_valid'],2)
            self.assertEqual(meta['n_valid'],4)
            east=next(t for t in proposals['levante'] if t['short_label']=='Chiosco')
            self.assertAlmostEqual(east['elevation_m'],1.4,places=6)
            self.assertEqual(east['id'],west['id'])
            self.assertEqual(len(summary),3)

    def test_nodata_is_reported_and_not_averaged_as_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            self.write_points(path,[point('Accesso',0,row=0),point('Accesso',2)])
            proposals,report,summary,meta=thresholds_from_structure_points(dem,path,polys)
            self.assertEqual(report.status.tolist(),['nodata','valid'])
            self.assertAlmostEqual(proposals['ponente'][0]['elevation_m'],.6,places=6)
            self.assertEqual(proposals['ponente'][0]['survey_statistics']['n_excluded'],1)
            self.assertEqual(meta['n_excluded'],1)
            self.assertEqual(proposals['levante'],[])

    def test_boundary_requires_a_choice_and_no_point_is_assigned_twice(self):
        from shapely.geometry import box,mapping
        from forecast_service.geospatial_setup import reproject_geometry
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            # Intentional overlap gives an unambiguous numerical test of the same covers rule as boundaries.
            polys['ponente']=mapping(reproject_geometry(box(500000,4879994,500007,4880000),32632,4326))
            a=point('Chiosco',5)
            self.write_points(path,[a])
            proposals,report,_,_=thresholds_from_structure_points(dem,path,polys)
            self.assertEqual(report.status.iloc[0],'ambiguous_sector')
            self.assertTrue(all(not rows for rows in proposals.values()))
            a['properties']['settore_costiero']='levante';self.write_points(path,[a])
            proposals,report,_,_=thresholds_from_structure_points(dem,path,polys)
            self.assertEqual(len(proposals['levante']),1);self.assertFalse(proposals['ponente'])
            a['properties']['settore_costiero']='inesistente';self.write_points(path,[a])
            self.assertEqual(thresholds_from_structure_points(dem,path,polys)[1].status.iloc[0],'invalid_sector')

    def test_dem_scale_offset_and_area_vertical_correction_are_applied_once(self):
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder,scale=2.,offset=1.)
            self.write_points(path,[point('Passeggiata',1)])
            proposals,report,_,meta=thresholds_from_structure_points(dem,path,polys,elevation_correction_m=.1)
            self.assertAlmostEqual(proposals['ponente'][0]['elevation_m'],1.9,places=6)
            self.assertAlmostEqual(report.dem_elevation_m.iloc[0],1.8,places=6)
            self.assertEqual(meta['elevation_correction_m'],.1)

    def test_undivided_area_and_non_wgs84_inputs(self):
        from shapely.geometry import box,mapping
        from forecast_service.geospatial_setup import reproject_geometry
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            whole={'whole':mapping(reproject_geometry(box(500000,4879994,500010,4880000),32632,4326))}
            self.write_points(path,[dict(type='Feature',properties={'struttura':'Ingresso','stagione':'estiva'},geometry={'type':'Point','coordinates':[500001.5,4879997.5]})])
            proposals,report,_,_=thresholds_from_structure_points(dem,path,whole,geojson_crs='EPSG:32632')
            self.assertEqual(len(proposals['whole']),1)
            self.assertEqual(proposals['whole'][0]['season'],'summer')
            self.assertFalse(proposals['whole'][0]['survey_statistics']['season_assumed'])

    def test_missing_labels_bad_geometry_and_seasons_are_not_silent_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            bad=point('Accesso',1);bad['geometry']={'type':'LineString','coordinates':[[9,44],[9.01,44.01]]}
            self.write_points(path,[point('',1),bad,point('Accesso',1,stagione='forse')])
            proposals,report,summary,meta=thresholds_from_structure_points(dem,path,polys)
            self.assertEqual(report.status.tolist(),['missing_label','invalid_geometry','invalid_season'])
            self.assertTrue(all(not rows for rows in proposals.values()))
            self.assertEqual(meta['n_valid'],0)

    def test_conflicting_activity_for_same_group_requires_review(self):
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            self.write_points(path,[point('Chiosco',1,stagione='estiva'),point('Chiosco',2,stagione='annuale')])
            with self.assertRaisesRegex(ValueError,'Stagioni discordanti'):
                thresholds_from_structure_points(dem,path,polys)

    def test_group_without_any_valid_height_has_no_invented_threshold(self):
        from shapely.geometry import box,mapping
        from forecast_service.geospatial_setup import reproject_geometry
        with tempfile.TemporaryDirectory() as folder:
            dem,_,path,point=self.inputs(folder)
            polys={'whole':mapping(reproject_geometry(box(500000,4879994,500030,4880000),32632,4326))}
            empty=point('Ingresso',1);empty['geometry']=None
            self.write_points(path,[point('Ingresso',0,row=0),empty,point('Ingresso',20)])
            proposals,report,summary,meta=thresholds_from_structure_points(dem,path,polys)
            self.assertEqual(report.status.tolist(),['nodata','invalid_geometry','outside_dem'])
            self.assertEqual(proposals,{'whole':[]})
            self.assertTrue(summary.mean_elevation_m.isna().all())
            self.assertEqual(meta['n_excluded'],3)

    @unittest.skipUnless(importlib.util.find_spec('ipywidgets'),'Modulo interattivo del notebook.')
    def test_proposed_lists_seed_only_mapped_structures_and_keep_manual_override_audit(self):
        from forecast_service.structure_forms import StructureEditor
        with tempfile.TemporaryDirectory() as folder:
            dem,polys,path,point=self.inputs(folder)
            self.write_points(path,[point('Chiosco',1),point('Chiosco',3)])
            proposals,_,_,_=thresholds_from_structure_points(dem,path,polys)
            defaults=[dict(id='default',short_label='Esempio',elevation_m=10.,season='all_year')]
            editor=StructureEditor({'ponente':'Ponente','levante':'Levante'},defaults,by_unit=proposals)
            result=editor.read()
            self.assertEqual(result['levante'],[])
            self.assertEqual(len(result['ponente']),1)
            self.assertEqual(result['ponente'][0]['survey_statistics']['selected_elevation_source'],'dem_point_mean')
            editor.rows['ponente'][0]['elevation'].value=1.5
            result=editor.read()
            self.assertEqual(result['ponente'][0]['elevation_m'],1.5)
            self.assertAlmostEqual(result['ponente'][0]['survey_statistics']['mean_elevation_m'],.6,places=6)
            self.assertEqual(result['ponente'][0]['survey_statistics']['selected_elevation_source'],'manual_override')


if __name__=='__main__':unittest.main()
