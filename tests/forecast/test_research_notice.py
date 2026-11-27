"""Research context must survive navigation, sharing and table filtering."""
from copy import deepcopy
import csv
from html.parser import HTMLParser
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from forecast_service import pipeline
from forecast_service import research_notice as n
from test_infographic import fixture
from forecast_service import infographic

ROOT = Path(__file__).resolve().parents[2]


class NoticeParser(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.details = 0
        self.heading = False
        self.heading_hidden = False
        self.heading_text = ''
        self.text = []
        self.disclaimer_links = 0
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'details': self.details += 1
        if attrs.get('id') == 'experimental-title':
            self.heading = True
            self.heading_hidden = self.details > 0 or 'hidden' in attrs
        if tag == 'a' and attrs.get('href') == 'disclaimer.html':
            self.disclaimer_links += 1

    def handle_endtag(self, tag):
        if tag == 'details': self.details -= 1
        if tag == 'h2': self.heading = False

    def handle_data(self, text):
        self.text.append(text)
        if self.heading: self.heading_text += text


class ResearchNoticeTests(unittest.TestCase):
    def test_every_public_page_has_visible_research_identity_and_complete_warning(self):
        pages = list((ROOT/'forecast_site').glob('*.html'))
        self.assertGreaterEqual(len(pages), 3)
        for page in pages:
            with self.subTest(page=page.name):
                parsed = NoticeParser(page.read_text())
                self.assertEqual(parsed.heading_text, n.RESEARCH_TITLE)
                self.assertFalse(parsed.heading_hidden)
                self.assertIn(n.RESEARCH_NOTICE, ''.join(parsed.text))
                self.assertGreater(parsed.disclaimer_links, 0)
        home = (ROOT/'forecast_site/index.html').read_text()
        self.assertNotIn('Quali strutture potrebbe raggiungere', home)

    def test_legal_contact_and_mandatory_liability_exception_remain(self):
        text = (ROOT/'forecast_site/disclaimer.html').read_text()
        self.assertIn('Prof. Alessio Rovere', text)
        self.assertIn('mailto:alessio.rovere@unive.it', text)
        self.assertIn('Restano ferme le responsabilità che non possono essere escluse o limitate per legge.', text)
        self.assertNotIn('Versione proposta', text)

    def test_csv_keeps_original_columns_values_and_rows_after_filtering(self):
        records = [dict(time='2026-11-27T06:00:00Z', model='A, B', twl_m=-.173,
                        surge_m=.1, surge_raw_m=.4, included_in_summary=True),
                   dict(time='2026-11-27T07:00:00Z', model='C', twl_m=2.5,
                        surge_m=.2, surge_raw_m=.6, included_in_summary=False)]
        before = deepcopy(records)
        exported = list(csv.DictReader(StringIO(pipeline.public_csv(records))))
        self.assertEqual(list(exported[0])[:len(records[0])], list(records[0]))
        for original, row in zip(records, exported):
            self.assertEqual({key:row[key] for key in original},
                             {key:str(value) for key,value in original.items()})
            self.assertEqual({key:row[key] for key in n.csv_notice()}, n.csv_notice())
        self.assertEqual(records, before)

    def test_demo_exports_for_whole_localities_and_sectors_carry_warning(self):
        from datetime import datetime, timezone
        with patch.object(pipeline, 'compute_runup', return_value={'Stockdon et al. (2006)': .8}):
            _, files = pipeline.build_bulletin(demo=True, now=datetime(2026,11,27,7,tzinfo=timezone.utc))
        self.assertTrue(any('--' in name for name in files))
        for name, contents in files.items():
            rows = list(csv.DictReader(StringIO(contents)))
            self.assertTrue(rows, name)
            self.assertTrue(all(row['data_mode']=='demo' for row in rows))
            self.assertTrue(all({k:row[k] for k in n.csv_notice()}==n.csv_notice() for row in rows))

    def test_png_warning_is_drawn_in_full_and_kept_in_embedded_metadata(self):
        bulletin, unit = fixture()
        calls = []
        warning_lines = []
        original = infographic.Canvas.text
        def record(canvas, text, *args, **kwargs):
            if text == n.PNG_NOTICE:
                draw_text = canvas.draw.text
                def draw_line(xy, line, *a, **kw):
                    warning_lines.append(line)
                    return draw_text(xy, line, *a, **kw)
                with patch.object(canvas.draw, 'text', draw_line):
                    result = original(canvas, text, *args, **kwargs)
            else:
                result = original(canvas, text, *args, **kwargs)
            calls.append((text, result))
            return result
        with tempfile.TemporaryDirectory() as folder, patch.object(infographic.Canvas, 'text', record):
            raw, metadata = infographic.render_card(bulletin, bulletin['locations']['borghetto'], unit,
                                                    folder, slug='borghetto', unit_id='uno')
        with Image.open(BytesIO(raw)) as image:
            embedded = json.loads(image.info['Onde-a-riva'])
            self.assertEqual(image.size, (1080,1350))
        for meta in (metadata, embedded):
            self.assertEqual(meta['research_status'], n.RESEARCH_STATUS)
            self.assertEqual(meta['disclaimer'], n.RESEARCH_NOTICE)
            self.assertEqual(meta['disclaimer_url'], n.DISCLAIMER_URL)
        self.assertIn('Prototipo di ricerca', [text for text,_ in calls])
        self.assertEqual(' '.join(warning_lines), ' '.join(n.PNG_NOTICE.split()))
        self.assertTrue(any(text==n.PNG_NOTICE and bottom<=128 for text,bottom in calls))
        self.assertIn(n.DISCLAIMER_URL.removeprefix('https://'), [text for text,_ in calls])
