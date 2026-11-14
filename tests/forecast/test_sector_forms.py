import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('ipywidgets'),'Moduli interattivi del setup opzionale.')
class SectorFormTests(unittest.TestCase):
    def test_ambiguous_choices_require_selection_and_return_only_overrides(self):
        from forecast_service.sector_forms import SectorAssignmentEditor
        editor=SectorAssignmentEditor([dict(transect_id='a',automatic='nord',allowed=['nord']),
            dict(transect_id='b',automatic=None,allowed=['nord','sud'])],dict(nord='Nord',sud='Sud'))
        with self.assertRaisesRegex(ValueError,'b'):editor.read()
        editor.rows['b'].value='sud'
        self.assertEqual(editor.read(),{'b':'sud'})

    def test_names_can_change_without_changing_ids_and_cannot_be_empty(self):
        from forecast_service.sector_forms import SectorNameEditor
        editor=SectorNameEditor({'nord':'Nord','sud':'Sud'})
        editor.rows['nord'].value='  Spiaggia del molo  '
        self.assertEqual(editor.read(),{'nord':'Spiaggia del molo','sud':'Sud'})
        editor.rows['sud'].value=' '
        with self.assertRaises(ValueError):editor.read()
