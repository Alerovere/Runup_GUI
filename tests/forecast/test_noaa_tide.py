from datetime import datetime,timedelta,timezone
import io
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock,patch
from scipy.io import netcdf_file
import numpy as np
from forecast_service.noaa_tide import Header,RangeReader,fetch_tides,validate_header

UTC=timezone.utc
CYCLE=datetime(2026,11,9,0,tzinfo=UTC)


def fixture():
    class Bytes(io.BytesIO):
        def close(self): pass
    memory=Bytes()
    with netcdf_file(memory,'w',version=1) as file:
        file.createDimension('time',None);file.createDimension('node',2)
        file.title='test-grid';file.rundes='2026110900 :test';file.nws=0
        time=file.createVariable('time','d',('time',));time.units='seconds since 2026-11-09 00:00:00';time.base_date='2026-11-09 00:00:00'
        x=file.createVariable('x','d',('node',));y=file.createVariable('y','d',('node',))
        x[:]=[8.3,12.5];y[:]=[44,45.3]
        z=file.createVariable('zeta','d',('time','node'));z.units='m'
        time[:]=np.arange(121)*3600;z[:]=np.column_stack([np.arange(121)*.001,np.arange(121)*-.001])
    data=memory.getvalue()
    io.BytesIO.close(memory)
    return data


class NoaaTideTests(unittest.TestCase):
    def setUp(self):
        self.data=fixture()
        self.grid={'grid_title_prefix':'test-grid','node_count':2,'locations':{
            'b':{'node_index_zero_based':0,'latitude':44.,'longitude':8.3},
            'v':{'node_index_zero_based':1,'latitude':45.3,'longitude':12.5}}}

    def test_classic_header_is_read_without_allocating_global_fields(self):
        h=Header(self.data).parse()
        self.assertEqual(h['records'],121)
        self.assertEqual(h['variables']['zeta']['shape'],[121,2])
        validate_header(h,self.grid,CYCLE)
        with self.assertRaises(ValueError): Header(b'not a NetCDF').parse()

    def test_http_server_ignoring_range_is_not_read(self):
        response=Mock(status=200,headers={})
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('forecast_service.noaa_tide.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'Range'): RangeReader('https://example.test').read(0,8)
        response.read.assert_not_called()

    def test_coordinate_drift_and_wrong_cycle_require_new_setup(self):
        h=Header(self.data).parse()
        with self.assertRaises(ValueError):validate_header(h,{**self.grid,'node_count':3},CYCLE)
        with self.assertRaises(ValueError):validate_header(h,self.grid,CYCLE+timedelta(hours=6))
        h["attributes"]["nws"]=[12]
        with self.assertRaisesRegex(ValueError,"meteorologiche"):validate_header(h,self.grid,CYCLE)

    def test_point_ranges_preserve_times_and_negative_tide_without_forecast_mean_removal(self):
        data=self.data
        class MemoryReader:
            def __init__(self,url):self.url=url;self.bytes=0;self.requests=0
            def read(self,start,length):self.bytes+=length;self.requests+=1;return data[start:start+length]
        records,meta=fetch_tides(self.grid,datetime(2026,11,9,tzinfo=UTC),96,now=CYCLE+timedelta(hours=1),reader_factory=MemoryReader)
        self.assertEqual(len(records['b']),96)
        self.assertEqual(records['b'][0]['tide_m'],0)
        self.assertAlmostEqual(records['b'][-1]['tide_m'],.095)
        self.assertAlmostEqual(records['v'][-1]['tide_m'],-.095)
        self.assertEqual(meta['product'],'HTP')
        self.assertLess(meta['transferred_bytes'],20000)
        bad={**self.grid,'locations':{'b':{**self.grid['locations']['b'],'longitude':8.4}}}
        with self.assertRaisesRegex(ValueError,'nodo'):
            fetch_tides(bad,datetime(2026,11,9,tzinfo=UTC),96,now=CYCLE+timedelta(hours=1),reader_factory=MemoryReader)
