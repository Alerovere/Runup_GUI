import importlib.util
import ast
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

import numpy as np
import pandas as pd

from forecast_service.site_setup import prepare_profile,fit_beachface
from forecast_service.site_package import write_site_package,import_site_package
from forecast_service.pipeline import ROOT

spec=importlib.util.spec_from_file_location('reference_beachface',Path(__file__).parent/'fixtures/reference_beachface.py')
reference=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def profile(reverse=False):
    distance=np.arange(45)*2.0
    z=.045*distance-.3
    z[(distance>=40)&(distance<=56)]=.4
    x=500000+.6*distance; y=4880000+.8*distance
    if reverse:
        z=z[::-1]; x=x[::-1]; y=y[::-1]
    return pd.DataFrame({'TR_ID':1,'distance':distance,'SAMPLE_1':z,'X':x,'Y':y})


class SlopeReferenceTests(unittest.TestCase):
    def test_notebook_embeds_current_sources(self):
        notebook=json.loads((ROOT/'notebooks/Definisci_siti_studio.ipynb').read_text())
        found=False
        for cell in notebook['cells']:
            if cell['cell_type']!='code':
                continue
            self.assertEqual(cell['outputs'],[])
            self.assertIsNone(cell['execution_count'])
            tree=ast.parse(''.join(cell['source']))
            for node in tree.body:
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BUNDLED_SOURCES' for t in node.targets):
                    for name,source in ast.literal_eval(node.value).items():
                        self.assertEqual(source,(ROOT/name).read_text(),name)
                    found=True
        self.assertTrue(found)

    def compare_reference(self,frame):
        expected_profile=reference.prepara_profilo(frame)
        expected_beta,expected_mask=reference.pendenza_battigia(expected_profile)
        actual=prepare_profile(frame)
        result,mask=fit_beachface(actual,0,1)
        np.testing.assert_allclose(actual.x_mare,expected_profile.x_mare,rtol=0,atol=1e-12)
        np.testing.assert_array_equal(mask,expected_mask)
        self.assertAlmostEqual(result['slope'],expected_beta,places=12)
        return actual,result,mask

    def test_matches_reference_for_forward_profile(self):
        self.compare_reference(profile())

    def test_matches_reference_for_reversed_profile(self):
        _,result,_=self.compare_reference(profile(True))
        self.assertTrue(result['reversed'])

    def test_backshore_depression_is_excluded_after_first_crest(self):
        actual,result,mask=self.compare_reference(profile())
        self.assertFalse(mask[actual.x_mare>=40].any())
        self.assertAlmostEqual(result['slope'],.045,places=10)

    def test_missing_elevations_follow_reference_drop_rule(self):
        frame=profile()
        frame.loc[2,'SAMPLE_1']=np.nan
        _,result,_=self.compare_reference(frame)
        self.assertEqual(result['dropped_nan_z'],1)

    def test_xy_distance_is_used_instead_of_distance_field(self):
        frame=profile()
        frame['distance']*=7
        _,result,_=self.compare_reference(frame)
        self.assertAlmostEqual(result['slope'],.045,places=10)

    def test_invalid_negative_slope_is_not_made_positive(self):
        frame=profile(True).iloc[-5:].reset_index(drop=True)
        frame['SAMPLE_1']=[.8,.6,.4,.2,0]
        with self.assertRaisesRegex(ValueError,'Pendenza'):
            fit_beachface(prepare_profile(frame),0,1)

    def test_first_point_above_limit_gives_clear_error(self):
        frame=profile()
        frame['SAMPLE_1']=2
        with self.assertRaisesRegex(ValueError,'Meno di due'):
            fit_beachface(prepare_profile(frame),0,1)


class PackageTests(unittest.TestCase):
    def payload(self):
        locations=json.loads((ROOT/'config/locations.json').read_text())
        impacts=json.loads((ROOT/'config/impact_thresholds.json').read_text())
        slug='borghetto-santo-spirito'
        locations['locations'][slug]['climatology_file']=None
        return {'schema_version':1,'slug':slug,'data_mode':'study','location':locations['locations'][slug],
                'thresholds':impacts['locations'][slug]['thresholds']}

    def copy_config(self,directory):
        root=Path(directory)/'repo'; (root/'config').mkdir(parents=True)
        for name in ['locations.json','impact_thresholds.json']:
            shutil.copyfile(ROOT/'config'/name,root/'config'/name)
        return root

    def test_replace_existing_site_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.copy_config(directory)
            payload=self.payload(); payload['location']['slopes']=[.045]
            archive=write_site_package(Path(directory)/'site.zip',payload)
            before=(root/'config/locations.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'--replace'):
                import_site_package(archive,root)
            self.assertEqual((root/'config/locations.json').read_bytes(),before)
            import_site_package(archive,root,replace=True)
            result=json.loads((root/'config/locations.json').read_text())
            self.assertEqual(result['locations'][payload['slug']]['slopes'],[.045])

    def test_demo_package_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.copy_config(directory)
            payload=self.payload(); payload['data_mode']='demo'
            archive=write_site_package(Path(directory)/'site.zip',payload)
            with self.assertRaisesRegex(ValueError,'dimostrativo'):
                import_site_package(archive,root,replace=True)

    def test_zip_traversal_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.copy_config(directory)
            archive=Path(directory)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as handle:
                handle.writestr('site.json',json.dumps(self.payload()))
                handle.writestr('../outside.txt','untrusted')
            with self.assertRaisesRegex(ValueError,'Percorso'):
                import_site_package(archive,root,replace=True)
            self.assertFalse((root/'outside.txt').exists())
