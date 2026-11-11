import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from forecast_service import pipeline as p
from test_sectors_and_maps import config, NOW


class AreaFlowTests(unittest.TestCase):
    def test_notebook_has_one_input_stage_and_coastal_structures(self):
        nb=json.loads((p.ROOT/'notebooks/Definisci_siti_studio.ipynb').read_text())
        tags=[tag for cell in nb['cells'] for tag in cell.get('metadata',{}).get('tags',[])]
        self.assertEqual(tags.count('area-inputs'),1)
        self.assertIn('coastal-sectors',tags)
        self.assertIn('exposed-structures',tags)
        all_code='\n'.join(''.join(cell['source']) for cell in nb['cells'] if cell['cell_type']=='code' and 'bundled-library' not in cell.get('metadata',{}).get('tags',[]))
        self.assertNotIn('PREPARA_MAPPE_DA_AREE',all_code)
        self.assertNotIn('ORIGINE_PROFILI',all_code)
        self.assertIn('ORTHO_SOURCE',all_code)
        for cell in nb['cells']:
            if cell['cell_type']=='code': ast.parse(''.join(cell['source']))

    def test_different_structure_lists_or_no_structures_keep_same_area_forcing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); locations,impacts=config(root)
            loc=locations['locations']['venezia']
            loc['wave_exposure']={'sectors_deg':[[70,130]]}
            loc['sectors']['ovest']['thresholds']=[]
            loc['sectors']['est']['thresholds']=[dict(id='parcheggio',short_label='Parcheggio',description='Parcheggio',elevation_m=1.2,season='all_year')]
            (root/'config/locations.json').write_text(json.dumps(locations))
            bulletin,_=p.build_bulletin(root=root,demo=True,now=NOW)
            units=bulletin['locations']['venezia']['sectors']; a,b=units['ovest'],units['est']
            self.assertEqual(a['thresholds'],[])
            self.assertEqual(b['thresholds'][0]['id'],'parcheggio')
            self.assertEqual(a['hourly'][0]['thresholds'],[])
            self.assertEqual(len(b['hourly'][0]['thresholds']),1)
            self.assertEqual(a['wave_exposure'],b['wave_exposure'])
            self.assertEqual(a['source'],b['source'])
            self.assertEqual(a['climatology'],b['climatology'])
            self.assertEqual(a['hourly'][0]['water_level_m'],b['hourly'][0]['water_level_m'])

    @unittest.skipUnless(importlib.util.find_spec('ipywidgets'),'Moduli interattivi del setup opzionale.')
    def test_editable_structures_can_vary_and_have_same_elevation(self):
        from forecast_service.structure_forms import StructureEditor
        defaults=[dict(id='ombrelloni',short_label='Ombrelloni',elevation_m=.7,season='summer'),dict(id='chiosco',short_label='Chiosco',elevation_m=1.1,season='all_year')]
        editor=StructureEditor({'ponente':'Ponente','levante':'Levante'},defaults)
        editor.rows['ponente'][0]['present'].value=False
        editor.rows['levante'][0]['name'].value='Accesso al mare'
        editor.rows['levante'][0]['elevation'].value=1.1
        result=editor.read()
        self.assertEqual(len(result['ponente']),1)
        self.assertEqual(len(result['levante']),2)
        self.assertEqual(result['levante'][0]['short_label'],'Accesso al mare')
        editor.rows['ponente'][1]['present'].value=False
        self.assertEqual(editor.read()['ponente'],[])


if __name__=='__main__': unittest.main()
