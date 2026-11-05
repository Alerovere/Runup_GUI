from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from forecast_service import wave_cycle as w

UTC = timezone.utc
CYCLE = datetime(2026, 11, 5, 0, tzinfo=UTC)
POINT = {'latitude': 44.0625, 'longitude': 8.333333}


def fixture():
    records = [dict(time=(CYCLE + timedelta(hours=i)).isoformat(), hs_m=1.2, tp_s=6.3, direction_deg=360.)
               for i in range(24)]
    files = [dict(url=f'https://example.org/{i}.nc', etag='"version1"',
                  valid=CYCLE + timedelta(hours=i), cycle=CYCLE) for i in (0, 12)]
    def reader(entry, point):
        rows = [dict(row, time=w.utc_time(row['time']), direction_deg=0.) for row in records
                if entry['valid'] <= w.utc_time(row['time']) < entry['valid'] + timedelta(hours=12)]
        return CYCLE, POINT, rows
    return files, records, reader


class NativeWaveCycleTests(unittest.TestCase):
    def test_all_hours_and_variables_must_match_with_circular_directions(self):
        files, records, reader = fixture()
        result = w.verify_run(files, records, POINT, reader)
        self.assertEqual(result['forecast_reference_time'], '2026-11-05T00:00:00Z')
        self.assertEqual(result['forecast_reference_verified_hours'], 24)
        self.assertEqual(len(result['forecast_reference_files']), 2)
        records[-1]['hs_m'] = 1.3
        with self.assertRaisesRegex(ValueError, 'diversi'):
            w.verify_run(files, records, POINT, reader=lambda e, p: (
                CYCLE, POINT, [dict(row, hs_m=1.2) for row in reader(e, p)[2]]))

    def test_missing_hour_changed_cell_or_cycle_refuse_a_run_label(self):
        files, records, reader = fixture()
        for changed in (
            lambda e, p: (CYCLE, POINT, reader(e, p)[2][:-1]),
            lambda e, p: (CYCLE, dict(POINT, longitude=9), reader(e, p)[2]),
            lambda e, p: (CYCLE + timedelta(hours=12), POINT, reader(e, p)[2]),
        ):
            with self.assertRaises(ValueError):
                w.verify_run(files, records, POINT, reader=changed)
        with self.assertRaises(ValueError):
            w.select_run(files[:-1], records)
        # An upload halfway through cannot combine different native runs.
        files[-1] = dict(files[-1], cycle=CYCLE + timedelta(hours=12))
        with self.assertRaises(ValueError):
            w.select_run(files, records)

    def test_nonfinite_values_and_duplicate_hours_refuse_a_run_label(self):
        files, records, reader = fixture()
        for changed in (
            lambda e, p: (CYCLE, POINT, reader(e, p)[2] * 2),
            lambda e, p: (CYCLE, POINT, [dict(row, tp_s=float('nan')) for row in reader(e, p)[2]]),
        ):
            with self.assertRaises(ValueError):
                w.verify_run(files, records, POINT, reader=changed)

    def test_metadata_failure_is_nonfatal_and_never_guesses_a_date(self):
        with patch.object(w, 'original_service', side_effect=TimeoutError), self.assertLogs(w.logger, level='WARNING'):
            self.assertEqual(w.verified_native_cycle('dataset', [], POINT), {'forecast_reference_status': 'unverified'})

    def test_native_listing_crosses_months_filters_analysis_and_follows_pagination(self):
        from types import SimpleNamespace
        records = [{'time': '2026-10-31T23:00Z'}, {'time': '2026-11-01T00:00Z'}]
        names = ['2026103112_h-HCMR--WAVE-MEDWAM4-MEDATL-b20261031_fc00-sv09.00.nc',
                 '2026103012_h-HCMR--WAVE-MEDWAM4-MEDATL-b20261031_an00-sv09.00.nc',
                 '2026110100_h-HCMR--WAVE-MEDWAM4-MEDATL-b20261031_fc00-sv09.00.nc']
        def response(names, token=None):
            xml = '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            xml += f'<IsTruncated>{"true" if token else "false"}</IsTruncated>'
            for name in names:
                xml += f'<Contents><Key>prefix/{name}</Key><ETag>"abc"</ETag></Contents>'
            if token: xml += f'<NextContinuationToken>{token}</NextContinuationToken>'
            return SimpleNamespace(content=(xml + '</ListBucketResult>').encode(), raise_for_status=lambda: None)
        with patch('requests.get', side_effect=[response(names[:1], 'next'), response(names[1:2]), response(names[2:])]) as get:
            result = w.list_native_files('https://example.org/bucket/prefix', records)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['cycle'], CYCLE - timedelta(days=5))
        self.assertEqual(get.call_count, 3)


if __name__ == '__main__': unittest.main()
