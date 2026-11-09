"""MeteOcean point CSV feeds. Provider-confirmed UTC, m, s, WW3 directions."""
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import math
from urllib.request import Request, urlopen

UTC=timezone.utc

def download_text(url):
    with urlopen(Request(url,headers={"User-Agent":"Onde-a-riva/1.0"}),timeout=45) as response:
        body=response.read(500_001)
        if len(body)>500_000: raise ValueError("CSV MeteOcean oltre il limite di 500 KB.")
        meta={"url":url,"last_modified":response.headers.get("Last-Modified"),"sha256":sha256(body).hexdigest(),
              "downloaded_at":datetime.now(UTC).isoformat(),"size_bytes":len(body)}
    return body.decode("utf-8-sig"),meta

def instant(value):
    return datetime.strptime(value.strip(),"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

def number(value):
    result=float(value)
    if not math.isfinite(result): raise ValueError("Valore MeteOcean non finito.")
    return result

def parse_waves(text):
    reader=csv.DictReader(io.StringIO(text))
    if not {"time","Hs","Tp","Dirp"}.issubset(reader.fieldnames or []):
        raise ValueError("Colonne MeteOcean Hs/Tp/Dirp mancanti.")
    result=[]
    for row in reader:
        time=instant(row["time"]);hs,tp,direction=(number(row[k]) for k in ("Hs","Tp","Dirp"))
        if not 0<=hs<50 or not 0<=tp<60 or (hs>0 and tp<=0) or not 0<=direction<=360:
            raise ValueError("Parametro di onda MeteOcean fuori dai limiti fisici.")
        result.append({"time":time,"hs_m":hs,"tp_s":tp,"direction_deg":direction%360})
    contiguous(result,3600)
    return result

def parse_surge(text):
    result=[]
    for row in csv.reader(io.StringIO(text)):
        if len(row)!=2: raise ValueError("Il CSV surge MeteOcean deve avere due colonne senza intestazione.")
        value=number(row[1])
        if abs(value)>10: raise ValueError("Surge MeteOcean fuori dai limiti fisici.")
        result.append({"time":instant(row[0]),"surge_m":value})
    contiguous(result,1800)
    return result

def contiguous(rows,seconds):
    if not rows or any((b["time"]-a["time"]).total_seconds()!=seconds for a,b in zip(rows,rows[1:])):
        raise ValueError("Serie MeteOcean vuota, disordinata, duplicata o con intervalli mancanti.")

def fetch_meteocean(settings,slug,start,hours,minimum_hours=96,downloader=download_text):
    feeds=settings["locations"][slug]
    wave_text,wave_meta=downloader(feeds["waves_url"])
    surge_text,surge_meta=downloader(feeds["surge_url"])
    waves,surge=parse_waves(wave_text),parse_surge(surge_text)
    if waves[0]["time"]!=surge[0]["time"]:
        raise ValueError("Onde e surge MeteOcean iniziano in date diverse: possibile aggiornamento incompleto.")
    # Coverage start is not an issue/reference time: the CSVs do not expose the model run.
    end=start+timedelta(hours=hours)
    chosen=[r for r in waves if start<=r["time"]<end]
    if len(chosen)<minimum_hours or chosen[0]["time"]!=start:
        raise ValueError(f"Copertura MeteOcean incompleta: servono almeno {minimum_hours} ore dal periodo richiesto.")
    levels={r["time"]:r["surge_m"] for r in surge}
    result=[]
    for row in chosen:
        if row["time"] not in levels: raise ValueError("Surge MeteOcean mancante all’orario delle onde.")
        result.append({**row,"time":row["time"].isoformat().replace("+00:00","Z"),"surge_m":levels[row["time"]]})
    meta={"provider":"meteocean","dataset_id":"MeteOcean-WW3-point-CSV","variables":["Hs","Tp","Dirp"],
          "direction_kind":"peak_from_direction","direction_convention":"WW3 nautical, from north clockwise",
          "coverage_start":waves[0]["time"].isoformat(),"coverage_end":waves[-1]["time"].isoformat(),
          "selected_point":None,"point_name":slug,"waves":wave_meta,"surge":surge_meta,
          "forecast_reference_time_status":"not_exposed_by_csv","surge_components":"meteorological_only",
          "surge_reference":"anomaly_about_mean_sea_level_provider_confirmed"}
    return result,meta
