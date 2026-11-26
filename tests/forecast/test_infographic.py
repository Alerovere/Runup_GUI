from copy import deepcopy
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from forecast_service import infographic as g
from forecast_service import pipeline
from forecast_service.ensemble import STATISTICS_METHOD

START=datetime(2026,11,26,9,tzinfo=timezone.utc)


def fixture():
    rows=[dict(time=g.iso(START+timedelta(hours=i)),hs_m=1.,tp_s=8.,direction_deg=180.,
        water_level_m=.2,twl_mean_m=.8,twl_p25_m=.6,twl_p75_m=1.,twl_p95_m=1.2,
        n_estimates=10,statistics_method=STATISTICS_METHOD,
        thresholds=[dict(id='chioschi',active=True,fraction=.1)]) for i in range(96)]
    unit=dict(name='Settore Uno',hourly=rows,thresholds=[dict(id='chioschi',short_label='Chioschi',elevation_m=1.1,season='all_year')],wave_exposure={'sectors_deg':[[135,225]]})
    b=dict(mode='meteocean',generated_at=g.iso(START+timedelta(minutes=20)),processing_started_at=g.iso(START),
           display_from=g.iso(START),display_to=g.iso(START+timedelta(hours=96)),display_hours=96,
           locations={'borghetto':dict(name='Borghetto S. Spirito',sectors={'uno':unit})})
    return b,unit


class SocialCardTests(unittest.TestCase):
    def test_png_is_4_by_5_fixes_the_cycle_and_keeps_wave_parameters_from_the_same_hour(self):
        b,unit=fixture();rows=unit['hourly'];rows[5].update(hs_m=3.,tp_s=7.,direction_deg=202.5)
        rows[10].update(tp_s=19.)
        rows[20].update(twl_p95_m=2.,water_level_m=.3)
        before=deepcopy(rows)
        with tempfile.TemporaryDirectory() as folder:
            raw,meta=g.render_card(b,b['locations']['borghetto'],unit,folder,slug='borghetto',unit_id='uno')
            image=Image.open(BytesIO(raw))
            self.assertEqual(image.size,(1080,1350));self.assertEqual(image.format,'PNG')
            self.assertEqual(json.loads(image.info['Onde-a-riva'])['twl_peak_time'],rows[20]['time'])
        data=g.card_data(b,unit)
        self.assertEqual(data['wave']['tp_s'],7.);self.assertEqual(g.compass(data['wave']['direction_deg']),'SSW')
        self.assertEqual(meta['twl_statistic'],'twl_p95_m')
        self.assertEqual(meta['period_from'],b['display_from']);self.assertEqual(meta['period_to'],b['display_to'])
        self.assertEqual(rows,before)
        self.assertEqual(len(data['days']),5)
        self.assertEqual([d['partial'] for d in data['days']],[True,False,False,False,True])

    def test_daily_scale_keeps_strict_percentile_bounds_and_excludes_nonfrontal_rows(self):
        _,unit=fixture();row=deepcopy(unit['hourly'][0])
        for p75,p95,key in [(1.,1.1,'white'),(1.1,1.2,'yellow'),(1.2,1.3,'orange')]:
            row.update(twl_p75_m=p75,twl_p95_m=p95)
            self.assertEqual(g.day_summary(unit,[row])['key'],key)
        row.update(direction_deg=0.)
        summary=g.day_summary(unit,[row]);self.assertEqual(summary['key'],'gray');self.assertIsNone(summary['fraction'])
        row.update(direction_deg=None);self.assertEqual(g.day_summary(unit,[row])['key'],'unavailable')
        row.update(direction_deg=180.,statistics_method='old');self.assertEqual(g.day_summary(unit,[row])['key'],'unavailable')
        row.update(statistics_method=STATISTICS_METHOD);row['thresholds'][0]['active']=False
        self.assertTrue(g.day_summary(unit,[row])['inactive'])

    def test_graphs_use_filtered_twl_without_reading_map_assets(self):
        b,unit=fixture();rows=unit['hourly']
        rows[2].update(statistics_method='old',twl_mean_m=99.)
        rows[3].update(water_level_m=None)
        rows[4].update(twl_p25_m=2.,twl_p75_m=1.)
        data=g.card_data(b,unit);points=g.chart_points(data['rows'],g.parse_time(data['period_from']))
        self.assertEqual(points[0]['twl'],.8);self.assertNotIn('runup',points[0])
        self.assertIsNone(points[2]['twl'])
        self.assertEqual(points[2]['hs'],1.) # waves are independent of runup statistics
        self.assertEqual(points[3]['twl'],.8) # TWL is not reduced by the sea-level contribution
        self.assertIsNone(points[4]['low']);self.assertIsNone(points[4]['high'])
        unit['inundation_map']=dict(status='available',orthophoto='data/private-map.png')
        with tempfile.TemporaryDirectory() as folder,patch.object(g.Image,'open',wraps=Image.open) as opened:
            raw,meta=g.render_card(b,b['locations']['borghetto'],unit,folder,slug='borghetto',unit_id='uno')
            self.assertTrue(all(Path(call.args[0]).name=='eu-erc-horizon-europe.png' for call in opened.call_args_list))
        self.assertIsNone(meta['map_statistic']);self.assertEqual(meta['content'],'wave_twl_forecast')
        self.assertEqual(meta['charts']['twl_statistic'],'twl_mean_m');self.assertGreater(len(raw),1000)
        self.assertEqual(meta['charts']['layout'],'side_by_side')
        self.assertNotIn('runup_statistic',meta['charts'])

    def test_direction_keeps_nautical_samples_and_does_not_invent_calm_or_missing_directions(self):
        b,unit=fixture();rows=unit['hourly'][:8]
        for row,angle in zip(rows,[359.,1.,360.,-10.,None,float('nan'),90.,180.]):
            row['direction_deg']=angle
        rows[6]['hs_m']=0.;rows[7]['hs_m']=None
        before=[dict(r) for r in rows]
        points=g.chart_points(rows,g.parse_time(b['display_from']))
        self.assertEqual([p['direction'] for p in points],[359.,1.,0.,350.,None,None,None,None])
        self.assertEqual(rows,before)
        with tempfile.TemporaryDirectory() as folder:
            _,meta=g.render_card(b,b['locations']['borghetto'],unit,folder,slug='borghetto',unit_id='uno')
            self.assertEqual(meta['charts']['direction_interpolation'],'none')
            self.assertEqual(meta['charts']['direction_convention'],'nautical_from_north_clockwise')

    def test_daily_percentages_are_independent_for_kiosks_and_promenade(self):
        b,unit=fixture()
        unit['thresholds']=[dict(id='chioschi',short_label='Chioschi',elevation_m=1.1,season='all_year'),
                            dict(id='passeggiata',short_label='Passeggiata mare',elevation_m=1.8,season='all_year')]
        for row in unit['hourly']:
            row['thresholds'].append(dict(id='passeggiata',active=True,fraction=0.))
        unit['hourly'][0]['thresholds'][0]['fraction']=.4
        unit['hourly'][1]['thresholds'][1]['fraction']=.02
        unit['hourly'][2].update(direction_deg=0.)
        unit['hourly'][2]['thresholds'][1]['fraction']=.9
        data=g.card_data(b,unit)
        kiosks,promenade=data['days'][0]['structures']
        self.assertEqual([t['id'] for t in data['structures']],['chioschi','passeggiata'])
        self.assertEqual(kiosks['fraction'],.4);self.assertEqual(promenade['fraction'],.02)
        self.assertEqual(promenade['peak_time'],unit['hourly'][1]['time'])
        self.assertEqual(kiosks['key'],'yellow');self.assertEqual(promenade['key'],'white')

    def test_pchip_preserves_knots_extrema_and_gaps_and_keeps_band_order(self):
        runs=g.smooth_segments([(0,0.),(1,1.),(2,0.),(3,None),(4,.5),(6,1.)])
        self.assertEqual(len(runs),3)
        self.assertEqual([runs[0][i*6] for i in range(3)],[(0,0.),(1,1.),(2,0.)])
        self.assertTrue(all(0<=y<=1 for _,y in runs[0]))
        self.assertEqual(runs[1],[(4,.5)]);self.assertEqual(runs[2],[(6,1.)])
        # Separate shape-preserving curves can cross despite ordered knots.
        points=[dict(x=i,low=l,high=h) for i,(l,h) in enumerate([(0.,.1),(1.,1.1),(1.,2.),(0.,1.)])]
        bands=g.central_bands(points)
        self.assertTrue(all(low<=high for band in bands for _,low,high in band))
        self.assertEqual([(bands[0][i*6][1],bands[0][i*6][2]) for i in range(4)],[(0.,.1),(1.,1.1),(1.,2.),(0.,1.)])
        self.assertAlmostEqual(bands[0][3][1],.5) # crossed first interval becomes linear
        self.assertAlmostEqual(bands[0][3][2],.6)
        points[1].update(low=None,high=None)
        self.assertEqual([len(band) for band in g.central_bands(points)],[1,7])

    def test_no_data_and_single_samples_still_produce_a_card(self):
        b,unit=fixture();before=deepcopy(unit['hourly'])
        for row in unit['hourly']:
            row.update(hs_m=None,tp_s=None,water_level_m=None,n_estimates=0)
        with tempfile.TemporaryDirectory() as folder:
            raw,_=g.render_card(b,b['locations']['borghetto'],unit,folder,slug='borghetto',unit_id='uno')
            self.assertEqual(Image.open(BytesIO(raw)).size,(1080,1350))
            unit['hourly']=[before[0]]
            raw,_=g.render_card(b,b['locations']['borghetto'],unit,folder,slug='borghetto',unit_id='uno')
            self.assertEqual(Image.open(BytesIO(raw)).size,(1080,1350))

    def test_one_card_per_sector_and_legacy_location_with_no_maps_is_supported(self):
        b,unit=fixture();b['locations']['venezia']=dict(deepcopy(unit),name='Venezia')
        with tempfile.TemporaryDirectory() as folder:
            g.write_cards(b,folder)
            files=list((Path(folder)/'social').glob('*.png'));self.assertEqual(len(files),2)
            self.assertNotIn('social_card',b['locations']['borghetto'])
            for item in [unit,b['locations']['venezia']]:
                self.assertEqual(item['social_card']['status'],'available');self.assertIsNone(item['social_card']['map_statistic'])
                self.assertEqual(item['social_card']['generated_at'],b['generated_at'])

    def test_failed_optional_export_does_not_abort_the_bulletin(self):
        b,unit=fixture()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(g,'render_card',side_effect=OSError('test image failure')),self.assertLogs(g.__name__,level='WARNING'):
                g.write_cards(b,folder)
            self.assertEqual(unit['social_card']['status'],'unavailable')

    def test_export_happens_after_maps_before_forecast_json_publication(self):
        b,unit=fixture();calls=[]
        def maps(bulletin,output,root):calls.append('maps');unit['inundation_map']={'status':'unavailable'}
        def cards(bulletin,output,root):
            self.assertEqual(calls,['maps']);self.assertFalse((Path(output)/'forecast.json').exists());calls.append('cards')
        with tempfile.TemporaryDirectory() as folder,patch('forecast_service.inundation.write_maps',side_effect=maps),patch.object(g,'write_cards',side_effect=cards):
            pipeline.write_bulletin(b,{},folder)
            self.assertTrue((Path(folder)/'forecast.json').exists())
        self.assertEqual(calls,['maps','cards'])
