import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from forecast_service.exposure import parse_exposure, validate_exposure
from forecast_service import pipeline


class ExposureTests(unittest.TestCase):
    def test_blank_means_unknown_and_multiple_arbitrary_sectors_are_supported(self):
        self.assertIsNone(parse_exposure('  '))
        self.assertEqual(parse_exposure('20,120;250,300','Scelta del sito'),
                         {'sectors_deg':[[20.,120.],[250.,300.]],'note':'Scelta del sito'})
        self.assertEqual(parse_exposure('315,45')['sectors_deg'],[[315.,45.]])
        self.assertEqual(parse_exposure('0,360')['sectors_deg'],[[0.,360.]])

    def test_invalid_or_ambiguous_sectors_are_rejected(self):
        for text in ('0,0','360,10','-1,90','0,361','nan,90','0,inf','90','90,180;','90,180,270','Est,Sud'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                parse_exposure(text)
        with self.assertRaises(ValueError):
            validate_exposure({'sectors_deg':[[False,90]]})

    def test_invalid_exposure_stops_configuration_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'config').mkdir()
            for name in ('locations.json','impact_thresholds.json'):
                shutil.copyfile(pipeline.ROOT/'config'/name,root/'config'/name)
            path=root/'config/locations.json'
            locations=json.loads(path.read_text())
            locations['locations']['venezia']['wave_exposure']={'sectors_deg':[[100,100]]}
            path.write_text(json.dumps(locations))
            with self.assertRaisesRegex(ValueError,'Settori'):
                pipeline.load_configuration(root)

    def test_exposure_caveat_does_not_filter_or_change_runup_and_twl(self):
        locations,impacts=pipeline.load_configuration()
        location=copy.deepcopy(locations['locations']['venezia'])
        waves=[{'time':'2026-11-05T06:00Z','hs_m':1.5,'tp_s':8.,'direction_deg':275.,'water_level_m':-.2}]
        thresholds=impacts['locations']['venezia']['thresholds']
        original=pipeline.summarize_records(waves,location,thresholds,impacts['summer_season'],0)
        location['wave_exposure']={'sectors_deg':[[20,120]]}
        self.assertEqual(original,pipeline.summarize_records(waves,location,thresholds,impacts['summer_season'],0))


if __name__=='__main__':
    unittest.main()
