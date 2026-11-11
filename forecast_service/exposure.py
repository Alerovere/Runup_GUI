"""User-defined sectors of incoming waves; no nearshore wave transformation."""
import math


def is_exposed(direction, exposure):
    if not exposure or not exposure.get('sectors_deg') or not isinstance(direction, (int, float)) or not math.isfinite(direction):
        return None
    direction %= 360
    return any((a <= direction <= b or b == 360 and direction == 0) if a <= b else (direction >= a or direction <= b)
               for a, b in exposure['sectors_deg'])


def validate_exposure(exposure):
    if exposure is None:
        return
    if not isinstance(exposure, dict) or not isinstance(exposure.get('sectors_deg'), list) or not exposure['sectors_deg']:
        raise ValueError('Esposizione: indicare almeno un settore oppure lasciare il campo non configurato.')
    if not isinstance(exposure.get('note', ''), str):
        raise ValueError('La nota sull’esposizione deve essere un testo.')
    for pair in exposure['sectors_deg']:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('Ogni settore deve contenere due angoli: da, a.')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pair):
            raise ValueError('Gli angoli di esposizione devono essere numeri finiti.')
        start, end = pair
        if not 0 <= start < 360 or not 0 <= end <= 360 or start == end:
            raise ValueError('Settori non validi: inizio da 0 a meno di 360, fine da 0 a 360; estremi distinti. Per tutte le direzioni usare 0,360.')


def parse_exposure(text, note=''):
    """Parse clockwise incoming sectors, e.g. '315,45; 90,180'."""
    if not text.strip():
        return None
    try:
        sectors = [[float(value.strip()) for value in sector.split(',')] for sector in text.split(';')]
    except ValueError as error:
        raise ValueError('Usare coppie di gradi separate da virgola e settori separati da punto e virgola, es. 315,45; 90,180.') from error
    exposure = {'sectors_deg': sectors, 'note': note}
    validate_exposure(exposure)
    return exposure
