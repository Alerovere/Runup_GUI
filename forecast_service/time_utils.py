"""Pure helpers shared with the standalone Colab setup."""
import math
from datetime import datetime,timezone


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def parse_time(value):
    result=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def quantile(values,q):
    ordered=sorted(values)
    position=(len(ordered)-1)*q
    low,high=math.floor(position),math.ceil(position)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)
