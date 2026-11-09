"""Offline checks for a bounded download probe; no live provider calls."""
import importlib.util
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('wave_download_probe',ROOT/'scripts/probe_wave_ensembles.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


def grib(payload=b'x'):
    length=20+len(payload)
    return b'GRIB\x00\x00\x0a\x02'+length.to_bytes(8,'big')+payload+b'7777'


class WaveDownloadProbeTests(unittest.TestCase):
    def test_provider_requests_do_not_pick_up_netrc_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads=probe.Downloads(Path(tmp),1,2)
            with patch('requests.sessions.get_netrc_auth') as netrc:
                request=downloads.session.prepare_request(probe.requests.Request('GET',probe.NOAA))
                netrc.assert_not_called()
            self.assertNotIn('Authorization',request.headers)

    def test_grib_split_rejects_html_and_truncated_messages(self):
        first,second=grib(),grib(b'abc')
        self.assertEqual(probe.split_grib(first+second),[first,second])
        for data in [b'<html>error</html>',first[:-1],b'',b'GRIB']:
            with self.assertRaises(ValueError):probe.split_grib(data)

    def test_multipart_validates_ranges_lengths_and_order(self):
        first,second=grib(),grib(b'abc')
        a=(100,100+len(first)-1);b=(200,200+len(second)-1)
        body=b''
        for bounds,data in [(b,second),(a,first)]:
            body+=b'--test\r\nContent-Type: application/octet-stream\r\nContent-Range: bytes '+f'{bounds[0]}-{bounds[1]}/500'.encode()+b'\r\n\r\n'+data+b'\r\n'
        body+=b'--test--\r\n'
        self.assertEqual(probe.unpack_ranges(body,'multipart/byteranges; boundary=test',[a,b]),[first,second])
        with self.assertRaises(ValueError):probe.unpack_ranges(body,'multipart/byteranges; boundary=test',[a])
        with self.assertRaises(ValueError):probe.unpack_ranges(first,'application/octet-stream',[(100,999)])

    def test_index_requires_all_three_fields_for_every_requested_member(self):
        index=[{'number':str(n),'step':'24','param':p,'_offset':n*100+i*20,'_length':20}
               for n in [1,2] for i,p in enumerate(probe.PARAMS['ecmwf'])]
        self.assertEqual(len(probe.select_fields(index,['1','2'],24)),6)
        for invalid in [index[:-1],index+[index[0]]]:
            with self.assertRaises(ValueError):probe.select_fields(invalid,['1','2'],24)
        with self.assertRaises(ValueError):probe.select_fields(index,['1','2'],96)

    def test_server_ignoring_range_is_stopped_before_the_global_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads=probe.Downloads(Path(tmp),1,2)
            response=Mock(status_code=200)
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            downloads.session.get=Mock(return_value=response)
            with self.assertRaisesRegex(ValueError,'ignora Range'):
                downloads.get('https://data.ecmwf.int/forecasts/test',headers={'Range':'bytes=0-20'},partial=True)
            response.iter_content.assert_not_called()
            self.assertEqual(downloads.bytes,0)

    def test_payload_budget_interrupts_and_does_not_cache_partial_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads=probe.Downloads(Path(tmp),1,2)
            response=Mock(status_code=200,headers={},url='https://example.test')
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.iter_content.return_value=iter([b'a'*100,b'b'*100])
            downloads.session.get=Mock(return_value=response)
            with self.assertRaisesRegex(ValueError,'budget'):
                downloads.get('https://example.test',cap=150)
            self.assertEqual(list(downloads.cache.iterdir()),[])

    def test_offline_cache_miss_never_makes_a_network_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads=probe.Downloads(Path(tmp),1,2,offline=True)
            downloads.session.get=Mock(side_effect=AssertionError('Network forbidden'))
            with self.assertRaisesRegex(ValueError,'offline'):
                downloads.get('https://data.ecmwf.int/forecasts/test')
            downloads.session.get.assert_not_called()

    def test_missing_values_never_become_extreme_wave_heights(self):
        self.assertFalse(probe.valid_value(9999,9999))
        self.assertFalse(probe.valid_value(float('nan'),9999))
        self.assertFalse(probe.valid_value(1e20,9999))
        self.assertTrue(probe.valid_value(0,9999))

    def test_period_and_direction_use_the_same_wet_cell_selected_from_height(self):
        cycle=datetime(2026,11,8,12,tzinfo=timezone.utc)
        metadata=dict(dataDate=20261108,dataTime=1200,endStep=24,missingValue=9999)
        handles={p:{**metadata,'shortName':p,'value':v} for p,v in [('swh',2),('perpw',7),('dirpw',180)]}
        calls=[]
        def nearest(handle,lat,lon,npoints):
            if npoints==4:
                return [dict(lat=44,lon=8.25,value=9999,distance=11),dict(lat=44,lon=8.5,value=2,distance=16)]
            calls.append((handle['shortName'],lat,lon))
            return [dict(lat=lat,lon=lon,value=handle['value'],distance=0)]
        fake=SimpleNamespace(codes_new_from_message=lambda blob:handles[blob],codes_get=lambda h,k:h[k],
                             codes_grib_find_nearest=nearest,codes_release=lambda h:None)
        with patch.dict('sys.modules',{'eccodes':fake}):
            rows=probe.extract(['swh','perpw','dirpw'],'noaa',cycle,24,
                {'site':{'wave_point':{'latitude':44.08,'longitude':8.33}}},'c00')
        self.assertEqual(rows[0]['selected_longitude'],8.5)
        self.assertEqual(rows[0]['period_native_s'],7)
        self.assertEqual({(lat,lon) for _,lat,lon in calls},{(44,8.5)})

    def test_a_different_grib_cycle_is_rejected_before_extracting_a_point(self):
        released=[]
        fake=SimpleNamespace(codes_new_from_message=lambda blob:blob,
            codes_get=lambda h,k:{'dataDate':20261107,'dataTime':1200,'endStep':24}[k],
            codes_release=released.append)
        with patch.dict('sys.modules',{'eccodes':fake}),self.assertRaisesRegex(ValueError,'Corsa'):
            probe.extract(['message'],'noaa',datetime(2026,11,8,12,tzinfo=timezone.utc),24,{},'c00')
        self.assertEqual(released,['message'])

    def test_direction_rounding_uses_grib_precision_without_accepting_arbitrary_angles(self):
        self.assertAlmostEqual(probe.wrap_direction(360.0002604085021,.25),.0002604085021)
        self.assertAlmostEqual(probe.wrap_direction(-.1,.25),359.9)
        self.assertEqual(probe.wrap_direction(360,0),0)
        for value,error in [(361,.25),(720,.25),(0,5),(0,float('nan'))]:
            with self.assertRaises(ValueError):probe.wrap_direction(value,error)


if __name__=='__main__':unittest.main()
