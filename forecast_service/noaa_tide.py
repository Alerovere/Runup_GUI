"""Read only STOFS-2D-Global HTP tide points, never the global field."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import math
import re
import struct
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import numpy as np

UTC=timezone.utc
SIZE={1:1,2:1,3:2,4:4,5:4,6:8}
DTYPE={1:">i1",3:">i2",4:">i4",5:">f4",6:">f8"}
class Header:
    def __init__(self, data): self.data=data; self.offset=4
    def integer(self):
        value=struct.unpack_from(">I",self.data,self.offset)[0]; self.offset+=4; return value
    def string(self):
        n=self.integer(); raw=self.data[self.offset:self.offset+n]; self.offset+=(n+3)//4*4; return raw.decode()
    def attributes(self):
        tag,n=self.integer(),self.integer(); result={}
        if tag not in (0,12): raise ValueError("Attributi NetCDF non riconosciuti")
        for _ in range(n):
            name=self.string(); kind=self.integer(); count=self.integer(); size=SIZE[kind]*count
            raw=self.data[self.offset:self.offset+size]; self.offset+=(size+3)//4*4
            result[name]=raw.decode(errors="replace") if kind==2 else np.frombuffer(raw,dtype=DTYPE[kind]).tolist()
        return result
    def parse(self):
        if self.data[:4] != b"CDF\x01": raise ValueError("Formato NetCDF non supportato")
        records=self.integer(); tag,n=self.integer(),self.integer(); dims=[]
        if tag != 10: raise ValueError("Dimensioni NetCDF assenti")
        for _ in range(n):
            name=self.string(); length=self.integer(); dims.append((name,length))
        attrs=self.attributes(); tag,n=self.integer(),self.integer(); variables={}
        if tag != 11: raise ValueError("Variabili NetCDF assenti")
        for _ in range(n):
            name=self.string(); ndims=self.integer(); axes=[self.integer() for _ in range(ndims)]
            metadata=self.attributes(); kind=self.integer(); vsize=self.integer(); begin=self.integer()
            variables[name]={"dims":[dims[i][0] for i in axes],"shape":[dims[i][1] or records for i in axes],
                             "record":bool(axes and dims[axes[0]][1]==0),"attrs":metadata,"type":kind,"vsize":vsize,"begin":begin}
        return {"records":records,"dimensions":dims,"attributes":attrs,"variables":variables,"header_bytes":self.offset}


class RangeReader:
    def __init__(self,url):
        self.url=url;self.bytes=0;self.requests=0;self.size=None;self.lock=threading.Lock()
    def read(self,start,length):
        if start<0 or not 0<length<=131072: raise ValueError("Range NOAA non valido.")
        with self.lock:
            self.bytes+=length;self.requests+=1
            if self.bytes>1_000_000 or self.requests>450: raise ValueError("Budget puntuale NOAA superato.")
        end=start+length-1
        request=Request(self.url,headers={"Range":f"bytes={start}-{end}","User-Agent":"Onde-a-riva/1.0"})
        with urlopen(request,timeout=45) as response:
            match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",response.headers.get("Content-Range", ""))
            if response.status!=206 or not match or tuple(map(int,match.groups()[:2]))!=(start,end):
                raise ValueError("NOAA non rispetta Range: campo globale non scaricato.")
            size=int(match.group(3))
            with self.lock:
                if self.size is not None and self.size!=size: raise ValueError("File NOAA cambiato durante la lettura.")
                self.size=size
            data=response.read(length+1)
            if len(data)!=length: raise ValueError("Range NOAA incompleto.")
            return data


def validate_header(header,grid,cycle):
    variables=header["variables"]
    if not header["attributes"].get("title","").startswith(grid["grid_title_prefix"]):
        raise ValueError("Griglia NOAA cambiata: ripetere il setup dei punti.")
    if dict(header["dimensions"]).get("node")!=grid["node_count"]:
        raise ValueError("Numero di nodi NOAA cambiato: ripetere il setup.")
    if not header["attributes"].get("rundes","").startswith(cycle.strftime("%Y%m%d%H")):
        raise ValueError("Corsa NOAA diversa dal file richiesto.")
    if header["attributes"].get("nws") != [0]:
        raise ValueError("Il file NOAA contiene forzanti meteorologiche: non è sola marea.")
    if variables["zeta"]["dims"]!=["time","node"] or variables["zeta"]["type"]!=6 or variables["zeta"]["attrs"].get("units")!="m":
        raise ValueError("Struttura o unità NOAA non supportate.")
    if variables["time"]["type"]!=6 or not variables["time"]["attrs"]["units"].startswith("seconds since "):
        raise ValueError("Asse temporale NOAA non supportato.")
    if any(variables[k]["type"]!=6 or variables[k]["dims"]!=["node"] for k in ["x","y"]):
        raise ValueError("Coordinate NOAA non supportate.")


def fetch_tides(grid,start,hours,now=None,reader_factory=RangeReader):
    now=now or datetime.now(UTC)
    # The 00 run is not available at 00:00. Allow at least one hour to publish.
    reference=min(now-timedelta(hours=1), start)
    latest=reference.replace(hour=reference.hour//6*6,minute=0,second=0,microsecond=0)
    reader=header=cycle=None
    for attempt in range(4):
        cycle=latest-timedelta(hours=6*attempt)
        url=f"https://noaa-gestofs-pds.s3.amazonaws.com/stofs_2d_glo.{cycle:%Y%m%d}/stofs_2d_glo.t{cycle:%H}z.fields.htp.nc"
        candidate=reader_factory(url)
        try:
            header=Header(candidate.read(0,16384)).parse()
            reader=candidate;break
        except HTTPError as error:
            if error.code!=404: raise
    if reader is None: raise ValueError("Nessuna corsa NOAA HTP disponibile.")
    validate_header(header,grid,cycle)
    variables=header["variables"]
    stride=sum(var["vsize"] for var in variables.values() if var["record"])
    def scalar(name,record=0,index=0):
        var=variables[name]
        offset=var["begin"]+(stride*record if var["record"] else 0)+index*8
        value=float(np.frombuffer(reader.read(offset,8),dtype=">f8")[0])
        if not math.isfinite(value): raise ValueError("Valore NOAA non finito.")
        return value
    for point in grid["locations"].values():
        index=point["node_index_zero_based"]
        if not 0<=index<grid["node_count"]: raise ValueError("Indice del nodo NOAA non valido.")
        if abs(scalar("x",index=index)-point["longitude"])>1e-7 or abs(scalar("y",index=index)-point["latitude"])>1e-7:
            raise ValueError("Il nodo NOAA non coincide più con il punto salvato.")
    base_text=variables["time"]["attrs"]["base_date"].split("!")[0].strip()
    base=datetime.strptime(base_text,"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    count=variables["time"]["shape"][0]
    first=base+timedelta(seconds=scalar("time"))
    last=base+timedelta(seconds=scalar("time",count-1))
    if last-first!=timedelta(hours=count-1): raise ValueError("Passo temporale NOAA non orario.")
    begin=(start-first).total_seconds()/3600
    if not begin.is_integer() or begin<0 or begin+hours>count:
        raise ValueError("Copertura NOAA insufficiente per le onde MeteOcean.")
    indices=list(range(int(begin),int(begin)+hours))
    def sample(record):
        instant=base+timedelta(seconds=scalar("time",record))
        if instant!=first+timedelta(hours=record): raise ValueError("Ora NOAA mancante o duplicata.")
        values={}
        for slug,point in grid["locations"].items():
            value=scalar("zeta",record,point["node_index_zero_based"])
            if abs(value)>10: raise ValueError("Marea NOAA mancante o fuori dai limiti fisici.")
            values[slug]={"time":instant.isoformat().replace("+00:00","Z"),"tide_m":value}
        return values
    records={slug:[] for slug in grid["locations"]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(sample,indices):
            for slug,record in row.items(): records[slug].append(record)
    meta={"provider":"NOAA STOFS-2D-Global","product":"HTP","variable":"zeta","units":"m",
          "cycle_utc":cycle.isoformat(),"source_url":reader.url,"downloaded_at":datetime.now(UTC).isoformat(),
          "grid_title":header["attributes"]["title"],"selected_points":grid["locations"],
          "transferred_bytes":reader.bytes,"range_requests":reader.requests,
          "datum_documentation":"MSL in NOAA distribution documentation; NetCDF uses generic above-geoid standard_name; local datum provisional"}
    return records,meta
