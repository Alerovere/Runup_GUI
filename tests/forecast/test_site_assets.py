"""Check references and navigation in the pages shipped by the forecast workflow."""
import html
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import unittest
from src.runup_models import MODEL_CITATIONS

ROOT=Path(__file__).resolve().parents[2]

class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=[];self.links=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a' and 'href' in attrs:self.links.append(attrs['href'])

class SiteAssetsTests(unittest.TestCase):
    def test_scientific_citations_and_funding_survive_on_the_shared_method_page(self):
        method=html.unescape((ROOT/'forecast_site/metodo.html').read_text())
        for citation in MODEL_CITATIONS.values():self.assertIn(citation,method)
        for name in ('index.html','metodo.html','disclaimer.html'):
            page=(ROOT/'forecast_site'/name).read_text()
            self.assertIn('101334860',page)
            self.assertIn('assets/eu-erc-horizon-europe.png',page)
            self.assertIn('non devono essere utilizzati per alcun tipo di previsione',page)

    def test_page_anchors_and_shared_method_links_resolve(self):
        pages={name:Page((ROOT/'forecast_site'/name).read_text()) for name in ('index.html','metodo.html','disclaimer.html')}
        for name,page in pages.items():
            self.assertEqual(len(page.ids),len(set(page.ids)),name)
            for href in page.links:
                url=urlsplit(href)
                if url.scheme or url.netloc:continue
                target=url.path or name
                if target.endswith('.html'):
                    self.assertIn(target,pages,href)
                    if url.fragment:self.assertIn(url.fragment,pages[target].ids,href)
            self.assertIn('disclaimer.html',page.links,name)
        self.assertNotIn('climate-summary',pages['index.html'].ids)
        self.assertNotIn('direction-summary',pages['index.html'].ids)

    def test_forecast_artifact_includes_the_new_method_page(self):
        workflow=(ROOT/'.github/workflows/local-forecast.yml').read_text()
        self.assertIn('cp forecast_site/index.html forecast_site/metodo.html forecast_site/disclaimer.html',workflow)

if __name__=='__main__':unittest.main()
