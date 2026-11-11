"""Optional beach subdivisions; forcing belongs to the parent location."""
import math
import re


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value) is not None


def validate_thresholds(thresholds):
    if not isinstance(thresholds, list) or not thresholds:
        raise ValueError('Soglie del settore mancanti.')
    try:
        ids = [t['id'] for t in thresholds]
        heights = [t['elevation_m'] for t in thresholds]
        if len(set(ids)) != len(ids) or any(not valid_id(i.replace('_', '-')) for i in ids):
            raise ValueError('Identificativi delle soglie non validi.')
        if any(not isinstance(h, (int, float)) or not math.isfinite(h) for h in heights) or heights != sorted(set(heights)):
            raise ValueError('Quote delle soglie non valide.')
        if any(t['season'] not in ('summer', 'all_year') or not t.get('description') for t in thresholds):
            raise ValueError('Descrizione o stagione delle soglie non valida.')
    except (KeyError, TypeError) as error:
        raise ValueError('Soglie del settore non valide.') from error


def resolve_sectors(location, thresholds):
    """Derive slopes from assigned transects, never from their order in a list."""
    from forecast_service.exposure import validate_exposure
    sectors = location.get('sectors', {})
    if not isinstance(sectors, dict):
        raise ValueError('I settori devono essere un dizionario.')
    transects = location.get('transects') or []
    by_id = {}
    for row in transects:
        key = str(row['transect_id'])
        if key in by_id:
            raise ValueError('Identificativo transetto duplicato.')
        by_id[key] = row
    assigned = set()
    resolved = {}
    allowed = {'name', 'transect_ids', 'thresholds', 'wave_exposure', 'mapping', 'notes', 'summer_season'}
    for key, sector in sectors.items():
        if not valid_id(key) or key == 'whole' or not isinstance(sector, dict) or not sector.get('name'):
            raise ValueError('Identificativo o nome del settore non valido (whole è riservato).')
        if set(sector) - allowed:
            raise ValueError('Campi del settore non ammessi: ' + ', '.join(sorted(set(sector)-allowed)))
        if not isinstance(sector.get('transect_ids'), list):
            raise ValueError('transect_ids deve essere una lista di identificativi.')
        ids = [str(i) for i in sector['transect_ids']]
        if not ids or len(set(ids)) != len(ids) or set(ids)-by_id.keys():
            raise ValueError(f'Transetti mancanti, duplicati o sconosciuti nel settore {key}.')
        if assigned.intersection(ids):
            raise ValueError('Uno stesso transetto è assegnato a più settori.')
        assigned.update(ids)
        selected = [by_id[i] for i in ids]
        slopes = [row.get('slope') for row in selected]
        if any(row.get('status', 'valid') != 'valid' for row in selected) or not slopes or any(isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) or not 0 < s < 1 for s in slopes):
            raise ValueError(f'Pendenze dei transetti non valide nel settore {key}.')
        slopes = sorted(set(slopes))
        merged = {k: v for k, v in location.items() if k not in ('sectors', 'mapping')}
        merged.update(sector, slopes=slopes, transects=selected, thresholds=sector.get('thresholds', thresholds))
        validate_thresholds(merged['thresholds'])
        validate_exposure(merged.get('wave_exposure'))
        season = merged.get('summer_season')
        if season:
            from datetime import datetime
            dates = [season.get('start_month_day'), season.get('end_month_day')]
            if any(dates) and not all(dates):
                raise ValueError('Definire entrambi gli estremi della stagione.')
            for value in dates:
                if value:
                    datetime.strptime('2000-'+value, '%Y-%m-%d')
        resolved[key] = merged
    if sectors and assigned != set(by_id):
        raise ValueError('Ogni transetto incluso deve appartenere a un settore: ' + ', '.join(sorted(set(by_id)-assigned)))
    return resolved


def mapping_entries(location):
    """Stable identifiers for optional per-beach/per-sector cartography."""
    if location.get('mapping'):
        yield 'whole', location['mapping']
    for key, sector in (location.get('sectors') or {}).items():
        if sector.get('mapping'):
            yield key, sector['mapping']


def validate_mappings(location, slug):
    for key, mapping in mapping_entries(location):
        prefix = f'config/study_sites/{slug}/cartography/{key}/'
        if not isinstance(mapping, dict) or mapping.get('grid_file') != prefix+'grid.npz':
            raise ValueError('Percorso della griglia cartografica non valido.')
        if mapping.get('orthophoto_file') not in (None, prefix+'orthophoto.png'):
            raise ValueError('Percorso dell’ortofoto non valido.')
        for field in ('survey_credit', 'survey_date', 'license', 'vertical_reference'):
            if not isinstance(mapping.get(field), str) or not mapping[field].strip():
                raise ValueError(f'Cartografia: compilare {field}.')
        if mapping.get('vertical_alignment_confirmed') is not True:
            raise ValueError('Confermare il raccordo verticale DEM/livello marino prima di attivare la mappa.')
        if not isinstance(mapping.get('dem_offset_m'), (int, float)) or not math.isfinite(mapping['dem_offset_m']):
            raise ValueError('Correzione verticale del DEM non valida.')
