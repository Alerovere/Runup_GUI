#!/usr/bin/env python3
"""Bounded, anonymous download experiment; never updates the forecast bulletin.

Two lead times are sampled, not a continuous forecast. Native period/direction
definitions are preserved; these results are deliberately not inputs to runup.
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import time

import requests

NOAA = 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_wave_0p25.pl'
ECMWF = 'https://data.ecmwf.int/forecasts'
PARAMS = {'noaa': ('swh', 'perpw', 'dirpw'), 'ecmwf': ('swh', 'pp1d', 'mwd')}


def unpack_ranges(body, content_type, expected):
    """Accept only the exact requested GRIB byte ranges, including multipart."""
    if content_type.lower().startswith('multipart/byteranges'):
        msg = BytesParser(policy=policy.default).parsebytes(
            b'Content-Type: '+content_type.encode()+b'\r\nMIME-Version: 1.0\r\n\r\n'+body)
        parts = {}
        for part in msg.iter_parts():
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(?:\d+|\*)', part['Content-Range'] or '')
            if not match:
                raise ValueError('Content-Range multipart mancante o non valido')
            bounds = tuple(map(int, match.groups()))
            if bounds in parts:
                raise ValueError('Range duplicato')
            parts[bounds] = part.get_payload(decode=True)
    elif len(expected) == 1:
        parts = {expected[0]: body}
    else:
        raise ValueError('Il server non ha restituito i range multipli richiesti')
    if set(parts) != set(expected):
        raise ValueError('I range ricevuti non corrispondono alla richiesta')
    for (start, end), blob in parts.items():
        if len(blob) != end-start+1 or not blob.startswith(b'GRIB') or not blob.endswith(b'7777'):
            raise ValueError('Messaggio GRIB incompleto o lunghezza inattesa')
    return [parts[bounds] for bounds in expected]


def select_fields(index, members, step):
    fields = [r for r in index if r.get('param') in PARAMS['ecmwf']
              and str(r.get('number', 'control')) in members]
    keys = [(str(r.get('number', 'control')), r['param']) for r in fields]
    expected = {(member, param) for member in members for param in PARAMS['ecmwf']}
    if set(keys) != expected or len(keys) != len(expected):
        raise ValueError('Campi o membri ECMWF mancanti/duplicati')
    if any(int(r['step']) != step for r in fields):
        raise ValueError('Scadenza dell’indice inattesa')
    return sorted(fields, key=lambda r: r['_offset'])


def valid_value(value, missing):
    return math.isfinite(value) and value != missing and abs(value) < 1e10


def wrap_direction(value, packing_error):
    if not math.isfinite(packing_error) or not 0 <= packing_error <= 1:
        raise ValueError('Precisione angolare GRIB inattesa')
    tolerance=max(packing_error, 1e-6)
    if not math.isfinite(value) or not -tolerance <= value <= 360+tolerance:
        raise ValueError('Direzione fuori dai limiti, anche considerando la precisione GRIB')
    return value % 360


def split_grib(body):
    blobs = []; offset = 0
    while offset < len(body):
        if body[offset:offset+4] != b'GRIB' or body[offset+7:offset+8] != b'\x02':
            raise ValueError('Risposta non GRIB2')
        length = int.from_bytes(body[offset+8:offset+16], 'big')
        if length < 20 or offset+length > len(body):
            raise ValueError('GRIB2 troncato')
        blob = body[offset:offset+length]
        if not blob.endswith(b'7777'): raise ValueError('Fine GRIB2 mancante')
        blobs.append(blob); offset += length
    if not blobs: raise ValueError('Risposta GRIB vuota')
    return blobs


def extract(blobs, source, cycle, step, locations, forced_member=None):
    import eccodes as ec
    groups = {}
    expected_date, expected_time = int(cycle.strftime('%Y%m%d')), cycle.hour*100
    try:
        for blob in blobs:
            gid = ec.codes_new_from_message(blob)
            try:
                if (ec.codes_get(gid, 'dataDate'), ec.codes_get(gid, 'dataTime'), int(ec.codes_get(gid, 'endStep'))) != (expected_date, expected_time, step):
                    raise ValueError('Corsa o scadenza GRIB non corrispondente')
                if source == 'noaa':
                    member = forced_member
                else:
                    member = str(ec.codes_get(gid, 'perturbationNumber')) if ec.codes_is_defined(gid, 'perturbationNumber') else 'control'
                param = ec.codes_get(gid, 'shortName')
                if param not in PARAMS[source] or param in groups.get(member, {}):
                    raise ValueError('Parametro inatteso o duplicato')
                groups.setdefault(member, {})[param] = gid
            except Exception:
                ec.codes_release(gid)
                raise
        rows = []
        for member, fields in groups.items():
            if set(fields) != set(PARAMS[source]):
                raise ValueError('Terna altezza/periodo/direzione incompleta')
            hs_handle = fields['swh']
            missing = ec.codes_get(hs_handle, 'missingValue')
            for slug, loc in locations.items():
                lat, lon = loc['wave_point']['latitude'], loc['wave_point']['longitude']
                candidates = ec.codes_grib_find_nearest(hs_handle, lat, lon, npoints=4)
                wet = [p for p in candidates if valid_value(p['value'], missing) and p['value'] >= 0]
                if not wet:
                    raise ValueError(f'{slug}: nessuna cella marina tra le quattro più vicine')
                point = min(wet, key=lambda p: p['distance'])
                if point['distance'] > 40:
                    raise ValueError(f'{slug}: cella marina oltre 40 km dal punto richiesto')
                values = {}
                for param, handle in fields.items():
                    # Same sea cell for all parameters; never choose period over land.
                    sample = ec.codes_grib_find_nearest(handle, point['lat'], point['lon'], npoints=1)[0]
                    if abs(sample['lat']-point['lat']) > 1e-6 or abs(sample['lon']-point['lon']) > 1e-6:
                        raise ValueError('Griglie dei parametri non coincidenti')
                    if not valid_value(sample['value'], ec.codes_get(handle, 'missingValue')):
                        raise ValueError(f'{slug}: {param} mancante nella cella marina scelta')
                    values[param] = sample['value']
                period, direction = (values[p] for p in PARAMS[source][1:])
                if period <= 0:
                    raise ValueError('Periodo fuori dai limiti fisici')
                try:
                    packing_error=float(ec.codes_get(fields[PARAMS[source][2]], 'packingError'))
                except Exception:
                    packing_error=0.0
                wrapped=wrap_direction(direction, packing_error)
                rows.append(dict(source=source, location=slug, member=member,
                    cycle_utc=cycle.isoformat(), lead_hours=step,
                    valid_time_utc=(cycle+timedelta(hours=step)).isoformat(),
                    requested_latitude=lat, requested_longitude=lon,
                    selected_latitude=point['lat'], selected_longitude=point['lon'],
                    distance_km=point['distance'], hs_m=values['swh'],
                    period_native_s=period, period_parameter=PARAMS[source][1],
                    direction_native_deg=direction, direction_wrapped_deg=wrapped,
                    direction_packing_error_deg=packing_error, direction_parameter=PARAMS[source][2]))
        return rows
    finally:
        for fields in groups.values():
            for gid in fields.values():
                ec.codes_release(gid)


class AnonymousAuth(requests.auth.AuthBase):
    """Do not pick up an unrelated login from ~/.netrc; keep proxy support."""
    def __call__(self, request):
        return request


class Downloads:
    def __init__(self, output, budget_mb, pause, offline=False):
        self.cache = output/'cache'; self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.auth = AnonymousAuth()
        self.session.headers['User-Agent'] = 'Runup-GUI-research-download-probe/1.0'
        self.limit = int(budget_mb*1_000_000); self.bytes = 0
        self.log = []; self.pause = pause; self.last_noaa = 0; self.offline = offline

    def get(self, url, params=None, headers=None, cap=5_000_000, partial=False):
        key = sha256(json.dumps([url, params, headers], sort_keys=True).encode()).hexdigest()
        path = self.cache/(key+'.bin'); meta_path = self.cache/(key+'.json')
        if path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text()); data = path.read_bytes()
            if sha256(data).hexdigest() != meta['sha256']:
                raise ValueError('Cache alterata')
            self.log.append({**meta, 'cache_hit': True, 'transferred_bytes': 0})
            return data, meta
        if self.offline:
            raise ValueError('Risposta assente dalla cache in modalità offline')
        if 'nomads.ncep.noaa.gov' in url:
            time.sleep(max(0, self.pause-(time.monotonic()-self.last_noaa)))
            self.last_noaa = time.monotonic()
        started = time.monotonic()
        with self.session.get(url, params=params, headers=headers, timeout=(15, 90), stream=True) as response:
            response.raise_for_status()
            if partial and response.status_code != 206:
                raise ValueError('Il server ignora Range: interrotto prima del file globale')
            chunks = []; size = 0
            for chunk in response.iter_content(131072):
                size += len(chunk); self.bytes += len(chunk)
                if size > cap or self.bytes > self.limit:
                    raise ValueError('Superato il budget di download: prova interrotta')
                chunks.append(chunk)
            data = b''.join(chunks)
            meta = dict(url=response.url, request_headers=headers or {}, http_status=response.status_code,
                content_type=response.headers.get('Content-Type', ''),
                content_range=response.headers.get('Content-Range'),
                etag=response.headers.get('ETag'), downloaded_at=datetime.now(timezone.utc).isoformat(),
                seconds=round(time.monotonic()-started, 3), size_bytes=size,
                sha256=sha256(data).hexdigest(), cache_hit=False, transferred_bytes=size)
        path.write_bytes(data); meta_path.write_text(json.dumps(meta, indent=2))
        self.log.append(meta)
        return data, meta


def noaa_probe(downloads, cycle, steps, locations, smoke):
    members = ['c00']+[f'p{i:02d}' for i in range(1, 3 if smoke else 31)]
    points = [loc['wave_point'] for loc in locations.values()]
    bbox = dict(leftlon=min(p['longitude'] for p in points)-.75,
        rightlon=max(p['longitude'] for p in points)+.75,
        bottomlat=min(p['latitude'] for p in points)-.75,
        toplat=max(p['latitude'] for p in points)+.75)
    rows = []
    for step in steps:
        for member in members:
            params = dict(dir=f'/gefs.{cycle:%Y%m%d}/{cycle:%H}/wave/gridded',
                file=f'gefs.wave.t{cycle:%H}z.{member}.global.0p25.f{step:03d}.grib2',
                var_HTSGW='on', var_PERPW='on', var_DIRPW='on', lev_surface='on', subregion='', **bbox)
            body, meta = downloads.get(NOAA, params=params)
            blobs = split_grib(body)
            extracted = extract(blobs, 'noaa', cycle, step, locations, member)
            rows.extend(extracted)
        print(f'NOAA +{step}h: {len(members)} membri, entrambe le località verificate', flush=True)
    return rows


def ecmwf_probe(downloads, cycle, steps, locations, smoke):
    members = [str(i) for i in range(1, 3 if smoke else 51)]
    rows = []
    for step in steps:
        for stream, kind, selected in [('waef', 'ef', members), ('wave', 'fc', ['control'])]:
            base = f'{ECMWF}/{cycle:%Y%m%d}/{cycle:%H}z/ifs/0p25/{stream}/{cycle:%Y%m%d%H}0000-{step}h-{stream}-{kind}'
            body, _ = downloads.get(base+'.index')
            index = [json.loads(line) for line in body.splitlines() if line.strip()]
            for offset in range(0, len(selected), 10):
                batch = selected[offset:offset+10]
                fields = select_fields(index, batch, step)
                bounds = [(r['_offset'], r['_offset']+r['_length']-1) for r in fields]
                headers = {'Range': 'bytes='+','.join(f'{a}-{b}' for a,b in bounds)}
                expected_size = sum(b-a+1 for a,b in bounds)
                body, meta = downloads.get(base+'.grib2', headers=headers,
                    cap=expected_size+100_000, partial=True)
                blobs = unpack_ranges(body, meta['content_type'], bounds)
                extracted = extract(blobs, 'ecmwf', cycle, step, locations)
                if {r['member'] for r in extracted} != set(batch):
                    raise ValueError('Identificativi dei membri GRIB non corrispondenti all’indice')
                rows.extend(extracted)
                print(f'ECMWF {stream} +{step}h: gruppo {offset+1}–{offset+len(batch)} di {len(selected)} letto', flush=True)
            print(f'ECMWF {stream} +{step}h: {len(selected)} membri verificati', flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description='Prova anonima e isolata degli ensemble di onda; non modifica il bollettino.')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'config/locations.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cycle', required=True, help='Corsa UTC YYYYMMDDHH già disponibile presso entrambi i fornitori')
    parser.add_argument('--source', choices=['noaa', 'ecmwf', 'both'], default='both')
    parser.add_argument('--steps', nargs='+', type=int, default=[24, 96])
    parser.add_argument('--smoke', action='store_true', help='Solo controllo e primi due membri perturbati')
    parser.add_argument('--offline', action='store_true', help='Usa soltanto la cache; non effettua richieste HTTP')
    parser.add_argument('--max-download-mb', type=float, default=200)
    parser.add_argument('--noaa-pause', type=float, default=2)
    args = parser.parse_args()
    if any(step < 0 or step > 120 or step % 3 for step in args.steps):
        parser.error('Usare scadenze multiple di 3 tra 0 e 120 ore')
    if args.noaa_pause < 1 or not 0 < args.max_download_mb <= 500:
        parser.error('Pausa NOAA almeno 1 s; budget fra 0 e 500 MB')
    cycle = datetime.strptime(args.cycle, '%Y%m%d%H').replace(tzinfo=timezone.utc)
    if cycle.hour not in (0, 12): parser.error('Per questa prova usare le corse 00 o 12 UTC')
    locations = json.loads(args.config.read_text())['locations']
    locations = {k: locations[k] for k in ('borghetto-santo-spirito', 'venezia')}
    args.output.mkdir(parents=True, exist_ok=True)
    downloads = Downloads(args.output, args.max_download_mb, args.noaa_pause, args.offline)
    started = time.monotonic(); rows = []; errors = {}; sources = ['noaa', 'ecmwf'] if args.source == 'both' else [args.source]
    for source in sources:
        try:
            rows.extend((noaa_probe if source == 'noaa' else ecmwf_probe)(downloads, cycle, args.steps, locations, args.smoke))
        except Exception as error:
            errors[source] = f'{type(error).__name__}: {error}'
            print(f'{source}: {errors[source]}', flush=True)
    if rows:
        with (args.output/'points.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report = dict(schema_version=1, cycle_utc=cycle.isoformat(), steps=args.steps, smoke=args.smoke, offline=args.offline,
        status='failed' if errors else 'passed', errors=errors,
        elapsed_seconds=round(time.monotonic()-started, 2), transferred_bytes=downloads.bytes,
        scope='Campione a scadenze selezionate, non serie continua di 96 ore; nessun calcolo runup/TWL.',
        parameter_warning='PERPW/DIRPW NOAA mantenuti nativi: verificare periodo e direzione prima dell’uso nel runup. ECMWF usa pp1d e mwd.',
        records=len(rows), counts={s: len([r for r in rows if r['source']==s]) for s in sources},
        requests=downloads.log)
    (args.output/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({k:v for k,v in report.items() if k!='requests'}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
