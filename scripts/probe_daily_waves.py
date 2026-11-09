#!/usr/bin/env python3
"""Isolated 72-hour daily wave download trial. Never writes a site bulletin."""
import argparse
import csv
import copy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys

import requests

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://gribstream.com/api/v2/ifswaef/timeseries'
# Wet ECMWF cells verified in the earlier native GRIB experiment.
SEA_CELLS = {'borghetto-santo-spirito': (44.0, 8.5), 'venezia': (45.25, 12.5)}


def iso(value):
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Specificare un orario con fuso UTC.')
    return result.astimezone(UTC)


def make_plan(at, smoke=False, member_count=None):
    """Bracket all 72 future hours, not just 72 hours from the model cycle."""
    at = at.astimezone(UTC)
    cycle = at.replace(hour=0, minute=0, second=0, microsecond=0)
    if not smoke and at < cycle + timedelta(hours=9):
        raise ValueError('La prova della corsa 00 UTC si esegue dalle 09 UTC; disponibilità da verificare.')
    elapsed = (at-cycle).total_seconds()/3600
    first = math.floor(elapsed/3)*3
    last = math.ceil((elapsed+72)/3)*3
    steps = [24] if smoke else list(range(first, last+1, 3))
    count = member_count if member_count is not None else (1 if smoke else 51)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 51:
        raise ValueError('Scegliere da 1 a 51 membri.')
    members = list(range(51)) if count == 51 else list(range(1, count+1))
    cells = {'borghetto-santo-spirito': SEA_CELLS['borghetto-santo-spirito']} if smoke else SEA_CELLS.copy()
    credits = len(steps)*len(members)*3*math.ceil(len(cells)/500)
    return {'schema_version': 1, 'experimental': True, 'cycle_utc': iso(cycle),
            'reference_at': iso(at), 'forecast_until': iso(at+timedelta(hours=72)),
            'forecast_hours': 72, 'interval_hours': 3, 'nominal_schedule_utc': '09:37',
            'smoke': smoke, 'steps': steps, 'members': members, 'sea_cells': cells,
            'estimated_gribstream_credits': credits,
            'noaa_members': 3 if smoke else 31,
            'noaa_requests': len(steps)*(3 if smoke else 31),
            'noaa_minimum_spacing_seconds': 2,
            'note': 'Solo dati di onda: nessun runup/TWL o modifica del bollettino pubblico. Copernicus resta nel servizio esistente.'}


def gribstream_payload(plan):
    cycle = parse_time(plan['cycle_utc'])
    payload = {'asOf': plan['cycle_utc'],
            'timesList': [iso(cycle+timedelta(hours=h)) for h in plan['steps']],
            'minLeadTime': f"{min(plan['steps'])}h", 'maxLeadTime': f"{max(plan['steps'])}h",
            'coordinates': [{'name': slug, 'lat': cell[0], 'lon': cell[1]}
                            for slug, cell in plan['sea_cells'].items()],
            'members': plan['members'], 'includeMetadata': ['native_coordinate'],
            'variables': [{'name': name, 'level': 'sfc', 'info': '', 'alias': alias}
                          for name, alias in [('swh', 'hs_m'), ('pp1d', 'tp_s'), ('mwd', 'direction_deg')]]}
    if plan['members'] == [0]:
        payload.pop('members')  # The control is a separate deterministic dataset.
    return payload


def validate_rows(rows, plan):
    """Reject old/mixed runs, missing members/times, land cells and null fields."""
    cycle = parse_time(plan['cycle_utc'])
    expected = {(slug, member, iso(cycle+timedelta(hours=h)))
                for slug in plan['sea_cells'] for member in plan['members'] for h in plan['steps']}
    seen = set()
    if not isinstance(rows, list):
        raise ValueError('La risposta non è un elenco di dati.')
    for row in rows:
        if parse_time(row['forecasted_at']) != cycle:
            raise ValueError('Corsa diversa dalla 00 UTC richiesta: dati rifiutati.')
        # The API includes member for ensemble responses; never infer it from row order.
        member_value = row['member']
        member = int(member_value)
        if isinstance(member_value, bool) or str(member) != str(member_value):
            raise ValueError('Identificativo membro non valido.')
        key = (row['name'], member, iso(parse_time(row['forecasted_time'])))
        if key not in expected or key in seen:
            raise ValueError('Località, membro o scadenza inattesi/duplicati.')
        seen.add(key)
        lat, lon = plan['sea_cells'][row['name']]
        if abs(float(row['native_lat'])-lat)>1e-5 or abs((float(row['native_lon'])-lon+180)%360-180)>1e-5:
            raise ValueError('La cella scelta non coincide con la cella marina verificata.')
        for field in ['hs_m', 'tp_s', 'direction_deg']:
            if row[field] is None or not math.isfinite(float(row[field])):
                raise ValueError('Variabile di onda mancante o non finita.')
        if not 0 <= float(row['hs_m']) < 100 or not 0 < float(row['tp_s']) < 100 or not -1 <= float(row['direction_deg']) <= 361:
            raise ValueError('Variabile di onda fuori dai limiti fisici.')
    if seen != expected:
        raise ValueError(f'Copertura incompleta: {len(seen)} righe su {len(expected)} attese.')
    return sorted(rows, key=lambda row: (row['name'], int(row['member']), row['forecasted_time']))


class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, request):
        request.headers['Authorization'] = 'Bearer '+self.token
        return request


def response_json(session, method, url, **kwargs):
    # Fixed HTTPS host, no redirect forwarding, no automatic retry or raw error logging.
    with session.request(method, url, timeout=(15, 90), allow_redirects=False,
                         stream=True, **kwargs) as response:
        if response.status_code != 200:
            raise ValueError(f'GribStream HTTP {response.status_code}: richiesta interrotta, nessun tentativo automatico.')
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 2_000_000:
                raise ValueError('Risposta oltre il limite di 2 MB.')
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise ValueError('Risposta GribStream non JSON.') from None


def safe_quota(quota, daily_cap=1200):
    fields = ['as_of', 'plan_name', 'token_status', 'credits_used', 'plan_daily_limit', 'effective_daily_limit', 'credits_remaining', 'quota_resets_at']
    result = {key: quota.get(key) for key in fields}
    result['remaining_within_local_daily_cap'] = quota_remaining(quota, daily_cap)
    return result


def quota_remaining(quota, daily_cap=1200):
    """Above 1200, require an explicitly selected cap and a verified Free Plan."""
    limit, used, remaining = (quota.get(k) for k in ['plan_daily_limit', 'credits_used', 'credits_remaining'])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
           for v in [limit, used, remaining]):
        raise ValueError('Quota non verificabile: nessun download di dati.')
    if not isinstance(daily_cap, int) or not 1 <= daily_cap <= 5000:
        raise ValueError('Il limite locale giornaliero deve essere tra 1 e 5000 crediti.')
    if daily_cap > 1200:
        effective = quota.get('effective_daily_limit')
        if quota.get('plan_name') != 'Free Plan' or isinstance(effective, bool) or not isinstance(effective, (int, float)) or not math.isfinite(effective) or effective < 0:
            raise ValueError('La quota effettiva del piano gratuito non è verificabile.')
        limit = effective
    return max(0, min(remaining, min(daily_cap, limit)-used))


def download_gribstream(plan, output, token_file, daily_cap=1200):
    if 0 in plan['members'] and len(plan['members']) > 1:
        return download_complete_ensemble(plan, output, token_file, daily_cap)
    output.mkdir(parents=True, exist_ok=True)
    dataset = 'ifswave' if plan['members'] == [0] else 'ifswaef'
    endpoint = f'https://gribstream.com/api/v2/{dataset}/timeseries'
    payload = gribstream_payload(plan)
    key = sha256(json.dumps([dataset, payload], sort_keys=True).encode()).hexdigest()
    cache = output/('gribstream-'+key+'.json')
    if cache.exists():
        rows = validate_rows(json.loads(cache.read_text()), plan)
        return {'status': 'passed', 'records': len(rows), 'cache_hit': True, 'data_file': str(cache), 'dataset': dataset}
    token = os.environ.get('GRIBSTREAM_TOKEN')
    if not token and token_file:
        if token_file.stat().st_mode & 0o077:
            raise ValueError('Il file del token deve avere permessi 600.')
        token = token_file.read_text().strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError('Configurare GRIBSTREAM_TOKEN oppure --token-file; non passare il token sulla riga di comando.')
    credits = plan['estimated_gribstream_credits']
    if credits > daily_cap-30:
        raise ValueError('Il costo stimato supera il limite locale selezionato, incluso il margine di 30 crediti.')
    with requests.Session() as session:
        session.auth = BearerAuth(token)
        session.headers.update({'Accept': 'application/json', 'Accept-Encoding': 'gzip',
                                'User-Agent': 'Runup-GUI-daily-wave-trial/1.0'})
        before = response_json(session, 'GET', 'https://gribstream.com/api/v2/quota')
        if before.get('token_status') != 'active' or before.get('quota_exhausted'):
            raise ValueError('Token non attivo oppure quota esaurita.')
        remaining = quota_remaining(before, daily_cap)
        if remaining < credits+30:
            raise ValueError('Crediti residui insufficienti: manteniamo almeno 30 crediti di margine.')
        # Marker survives an ambiguous timeout: reruns cannot silently spend again.
        marker = output/('attempted-'+key)
        with marker.open('x') as stream:
            stream.write('Richiesta inviata; controllare la quota prima di ripetere.\n')
        raw = response_json(session, 'POST', endpoint, json=payload)
        if not isinstance(raw, list):
            raise ValueError('La risposta non è un elenco di dati.')
        if dataset == 'ifswave':
            for row in raw:
                if row.get('member') not in (None, 0, '0') or isinstance(row.get('member'), bool):
                    raise ValueError('Il dataset di controllo contiene un membro inatteso.')
                row['member'] = 0
                row['member_kind'] = 'control_from_ifswave'
        for row in raw:
            row['source_dataset'] = dataset
        cache.write_text(json.dumps(raw, indent=2))
        rows = validate_rows(raw, plan)
        after = response_json(session, 'GET', 'https://gribstream.com/api/v2/quota')
    return {'status': 'passed', 'records': len(rows), 'cache_hit': False,
            'downloaded_at': iso(datetime.now(UTC)),
            'estimated_credits': credits, 'daily_credit_cap': daily_cap,
            'dataset': dataset, 'data_file': str(cache),
            'quota_before': safe_quota(before, daily_cap),
            'quota_after': safe_quota(after, daily_cap), 'quota_note': 'Il conteggio del fornitore può aggiornarsi con ritardo.'}


def download_complete_ensemble(plan, output, token_file, daily_cap):
    """ECMWF control is in ifswave; never invent it or duplicate a perturbation."""
    reports = []
    rows = []
    for name, members in [('perturbed', [m for m in plan['members'] if m != 0]), ('control', [0])]:
        subplan = copy.deepcopy(plan)
        subplan['members'] = members
        subplan['estimated_gribstream_credits'] = len(plan['steps'])*len(members)*3*math.ceil(len(plan['sea_cells'])/500)
        report = download_gribstream(subplan, output/name, token_file, daily_cap)
        rows.extend(json.loads(Path(report['data_file']).read_text()))
        reports.append(report)
    rows = validate_rows(rows, plan)
    combined = output/'ecmwf-complete-points.json'
    combined.write_text(json.dumps(rows, indent=2))
    return {'status': 'passed', 'records': len(rows), 'members': len(plan['members']),
            'estimated_credits': plan['estimated_gribstream_credits'],
            'verified_at': iso(datetime.now(UTC)), 'daily_credit_cap': daily_cap,
            'cache_hit': all(report.get('cache_hit', False) for report in reports),
            'data_file': str(combined), 'datasets': reports,
            'note': '50 membri perturbati ifswaef e controllo ifswave; corsa, orari e celle verificati separatamente.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--at', help='Istante UTC di riferimento ISO 8601; default: adesso')
    parser.add_argument('--source', choices=['noaa', 'gribstream'], default='gribstream')
    parser.add_argument('--download', action='store_true', help='Senza questa opzione si stampa solo il piano, senza rete o credenziali')
    parser.add_argument('--smoke', action='store_true', help='Una scadenza (+24h); un membro ECMWF o tre NOAA; non copre 72h')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--members', type=int, choices=range(1, 52), help='Default: tutti i 51; con --smoke: 1. Un sottoinsieme non rappresenta l’ensemble completo.')
    parser.add_argument('--daily-credit-cap', type=int, default=1200, help='Limite locale giornaliero, massimo 5000. Sopra 1200 richiede quota effettiva verificata su Free Plan.')
    args = parser.parse_args()
    try:
        plan = make_plan(parse_time(args.at) if args.at else datetime.now(UTC), args.smoke, args.members)
        if not args.download:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        if not args.output:
            parser.error('--output è obbligatorio con --download')
        if (ROOT/'forecast_site').resolve() in [args.output.resolve(), *args.output.resolve().parents]:
            raise ValueError('Salvare gli output della prova fuori dal sito pubblico.')
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        if args.source == 'gribstream':
            report = download_gribstream(plan, args.output, args.token_file, args.daily_credit_cap)
        else:
            from probe_wave_ensembles import Downloads, noaa_probe
            config = json.loads((ROOT/'config/locations.json').read_text())['locations']
            locations = {slug: config[slug] for slug in plan['sea_cells']}
            downloads = Downloads(args.output, 30, 2)
            rows = noaa_probe(downloads, parse_time(plan['cycle_utc']), plan['steps'], locations, args.smoke)
            expected = len(plan['steps'])*plan['noaa_members']*len(locations)
            if len(rows) != expected:
                raise ValueError('Copertura NOAA incompleta.')
            with (args.output/'noaa-points.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            report = {'status': 'passed', 'records': len(rows), 'transferred_bytes': downloads.bytes}
        (args.output/(args.source+'-report.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as error:
        # Never print response bodies, headers, token values, or request exception details.
        print(f'Prova interrotta ({type(error).__name__}).' +
              (' '+str(error) if isinstance(error, ValueError) and not isinstance(error, requests.RequestException) else ''), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
