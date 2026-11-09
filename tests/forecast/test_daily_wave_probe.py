"""Offline checks for the isolated daily trial; never consumes API credits."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('daily_wave_probe', ROOT/'scripts/probe_daily_waves.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class DailyWaveProbeTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 11, 9, 9, 37, tzinfo=timezone.utc)
        self.plan = probe.make_plan(self.at, member_count=8)

    def rows(self, plan):
        payload = probe.gribstream_payload(plan)
        return [dict(forecasted_at=plan['cycle_utc'], forecasted_time=time,
                     name=slug, member=member, native_lat=cell[0], native_lon=cell[1],
                     hs_m=2, tp_s=7, direction_deg=180)
                for slug, cell in plan['sea_cells'].items() for member in plan['members']
                for time in payload['timesList']]

    def test_three_days_are_counted_from_update_not_midnight(self):
        self.assertEqual(self.plan['cycle_utc'], '2026-11-09T00:00:00Z')
        self.assertEqual(self.plan['steps'][0], 9)
        self.assertEqual(self.plan['steps'][-1], 84)
        self.assertEqual(len(self.plan['steps']), 26)
        self.assertEqual(self.plan['estimated_gribstream_credits'], 624)
        for hour in [9, 10, 13, 22, 23]:
            at = self.at.replace(hour=hour)
            plan = probe.make_plan(at, member_count=8)
            cycle = probe.parse_time(plan['cycle_utc'])
            self.assertLessEqual(cycle+timedelta(hours=min(plan['steps'])), at)
            self.assertGreaterEqual(cycle+timedelta(hours=max(plan['steps'])), at+timedelta(hours=72))
            self.assertLessEqual(plan['estimated_gribstream_credits'], 624)

    def test_sparse_valid_times_and_cutoff_are_explicit(self):
        payload = probe.gribstream_payload(self.plan)
        self.assertEqual(len(payload['timesList']), 26)
        self.assertEqual(payload['asOf'], self.plan['cycle_utc'])
        self.assertNotIn('fromTime', payload)
        self.assertEqual(len(payload['coordinates']), 2)
        self.assertEqual([v['name'] for v in payload['variables']], ['swh', 'pp1d', 'mwd'])
        self.assertEqual(probe.make_plan(self.at, True)['estimated_gribstream_credits'], 3)

    def test_old_mixed_runs_or_partial_ensemble_are_rejected(self):
        rows = self.rows(self.plan)
        self.assertEqual(len(probe.validate_rows(rows, self.plan)), 416)
        variants = [rows[:-1], rows+[rows[0]]]
        wrong_cycle = copy.deepcopy(rows)
        wrong_cycle[0]['forecasted_at'] = '2026-11-08T12:00:00Z'
        variants.append(wrong_cycle)
        for invalid in variants:
            with self.assertRaises(ValueError): probe.validate_rows(invalid, self.plan)

    def test_wrong_cell_missing_values_and_land_sentinels_are_rejected(self):
        for field, value in [('native_lon', 9), ('hs_m', None), ('hs_m', 9999), ('tp_s', 0), ('member', 2.5)]:
            rows = self.rows(self.plan)
            rows[0][field] = value
            with self.assertRaises(ValueError): probe.validate_rows(rows, self.plan)

    def test_denied_or_redirected_requests_never_read_body_or_retry(self):
        for status in [301, 400, 401, 429, 500]:
            session = Mock()
            response = Mock(status_code=status)
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            session.request.return_value = response
            with self.assertRaises(ValueError):
                probe.response_json(session, 'POST', probe.ENDPOINT, json={})
            self.assertEqual(session.request.call_count, 1)
            response.iter_content.assert_not_called()
            self.assertFalse(session.request.call_args.kwargs['allow_redirects'])

    def test_auth_is_explicit_and_does_not_use_netrc(self):
        import requests
        with requests.Session() as session:
            session.auth = probe.BearerAuth('test-secret')
            with patch('requests.sessions.get_netrc_auth') as netrc:
                request = session.prepare_request(requests.Request('POST', probe.ENDPOINT))
            netrc.assert_not_called()
            self.assertEqual(request.headers['Authorization'], 'Bearer test-secret')

    def test_quota_failure_prevents_weather_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(probe.os.environ, {'GRIBSTREAM_TOKEN': 'test-secret'}):
            with patch.object(probe, 'response_json', return_value={'token_status': 'active', 'credits_remaining': 10}) as call:
                with self.assertRaises(ValueError):
                    probe.download_gribstream(self.plan, Path(tmp), None)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[1], 'GET')

    def test_provider_overage_is_never_treated_as_the_daily_free_budget(self):
        quota = {'plan_daily_limit': 1200, 'credits_used': 1000, 'credits_remaining': 5000}
        self.assertEqual(probe.quota_remaining(quota), 200)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(probe.os.environ, {'GRIBSTREAM_TOKEN': 'test-secret'}):
            with patch.object(probe, 'response_json', return_value={**quota, 'token_status': 'active'}) as call:
                with self.assertRaises(ValueError):
                    probe.download_gribstream(self.plan, Path(tmp), None)
                self.assertEqual(call.call_count, 1)

    def test_full_ensemble_has_51_members_and_uses_effective_free_quota_only_when_selected(self):
        plan = probe.make_plan(self.at)
        self.assertEqual(plan['members'], list(range(51)))
        self.assertEqual(plan['estimated_gribstream_credits'], 3978)
        quota = {'plan_daily_limit': 1200, 'credits_used': 627, 'credits_remaining': 5373,
                 'plan_name': 'Free Plan', 'effective_daily_limit': 6000}
        self.assertEqual(probe.quota_remaining(quota), 573)
        self.assertEqual(probe.quota_remaining(quota, 5000), 4373)
        self.assertEqual(probe.make_plan(self.at, True, 51)['estimated_gribstream_credits'], 153)
        for changes in [{'plan_name': 'Paid Plan'}, {'effective_daily_limit': None}]:
            with self.assertRaises(ValueError): probe.quota_remaining({**quota, **changes}, 5000)
        reduced = {**quota, 'effective_daily_limit': 1200, 'credits_remaining': 573}
        self.assertEqual(probe.quota_remaining(reduced, 5000), 573)

    def test_ambiguous_failed_download_is_not_sent_again(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(probe.os.environ, {'GRIBSTREAM_TOKEN': 'test-secret'}):
            quota = {'plan_daily_limit': 1200, 'credits_used': 0, 'credits_remaining': 6000, 'token_status': 'active'}
            with patch.object(probe, 'response_json', side_effect=[quota, ValueError('timeout')]):
                with self.assertRaises(ValueError):
                    probe.download_gribstream(self.plan, Path(tmp), None)
            with patch.object(probe, 'response_json', return_value=quota) as call:
                with self.assertRaises(FileExistsError):
                    probe.download_gribstream(self.plan, Path(tmp), None)
                self.assertEqual(call.call_count, 1)

    def test_valid_cache_never_reads_token_or_calls_network(self):
        plan = probe.make_plan(self.at, True)
        payload = probe.gribstream_payload(plan)
        key = probe.sha256(json.dumps(['ifswaef', payload], sort_keys=True).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/('gribstream-'+key+'.json')).write_text(json.dumps(self.rows(plan)))
            with patch.object(probe, 'response_json', side_effect=AssertionError('Network forbidden')):
                report = probe.download_gribstream(plan, Path(tmp), Path(tmp)/'missing-token')
            self.assertTrue(report['cache_hit'])

    def test_complete_ensemble_uses_a_separate_control_with_the_same_cycle_times_and_cells(self):
        plan = probe.make_plan(self.at, True, 51)
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            def fetch(subplan, output, token_file, daily_cap):
                calls.append((subplan['members'], probe.gribstream_payload(subplan)))
                output.mkdir(parents=True)
                rows = self.rows(subplan)
                for row in rows: row['source_dataset'] = 'ifswave' if subplan['members'] == [0] else 'ifswaef'
                data = output/'points.json'
                data.write_text(json.dumps(rows))
                return {'records': len(rows), 'data_file': str(data)}
            with patch.object(probe, 'download_gribstream', side_effect=fetch):
                report = probe.download_complete_ensemble(plan, Path(tmp), None, 5000)
            self.assertEqual(report['members'], 51)
            self.assertEqual(report['records'], 51)
            self.assertEqual(calls[0][0], list(range(1, 51)))
            self.assertEqual(calls[1][0], [0])
            self.assertNotIn('members', calls[1][1])
            for _, payload in calls: self.assertEqual(payload['asOf'], plan['cycle_utc'])


if __name__ == '__main__': unittest.main()
