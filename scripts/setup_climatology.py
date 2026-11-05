#!/usr/bin/env python3
"""Download ERA5 once or import a saved CSV; daily forecasts never call CDS."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from forecast_service.climate import build_climate
from forecast_service.era5_download import download_series


def main():
    parser=argparse.ArgumentParser(description='Prepara una climatologia ERA5 per una località.')
    parser.add_argument('location',help='Identificativo in config/locations.json')
    parser.add_argument('--csv',type=Path,help='Importa un CSV già scaricato; nessuna richiesta CDS.')
    parser.add_argument('--hs-column',default='hs_m',help='Usare hs per il CSV dell’app wave_climate originale.')
    parser.add_argument('--time-column',default='time')
    parser.add_argument('--start',default='1991-01-01')
    parser.add_argument('--end',default='2020-12-31')
    parser.add_argument('--cache',type=Path,default=Path('/tmp/onde-a-riva-era5-cache'))
    parser.add_argument('--cell-lat',type=float,help='Cella marina ERA5 già nota; richiede anche --cell-lon.')
    parser.add_argument('--cell-lon',type=float)
    parser.add_argument('--allow-missing',action='store_true',help='Scarta esplicitamente Hs mancanti e registra il conteggio.')
    parser.add_argument('--replace',action='store_true',help='Sostituisce una climatologia già preparata.')
    args=parser.parse_args()
    config_path=ROOT/'config/locations.json'
    config=json.loads(config_path.read_text())
    if args.location not in config['locations']:
        parser.error('Località non presente nella configurazione.')
    target=ROOT/'config/climatology'/f'{args.location}.json'
    if target.exists() and not args.replace:
        parser.error('Climatologia già presente. Riusarla o specificare --replace.')
    if (args.cell_lat is None)!=(args.cell_lon is None):
        parser.error('Specificare entrambe le coordinate della cella ERA5.')
    args.cache.mkdir(parents=True,exist_ok=True)
    metadata={}
    if args.csv:
        csv_path=args.csv
    else:
        cell=(args.cell_lon,args.cell_lat) if args.cell_lat is not None else None
        frame,metadata=download_series(config['locations'][args.location],dt.date.fromisoformat(args.start),dt.date.fromisoformat(args.end),args.cache,cell=cell)
        csv_path=args.cache/f'{args.location}_ERA5_hourly.csv'
        frame.to_csv(csv_path,index=False)
        if metadata['missing_hs_records'] and not args.allow_missing:
            parser.error(f"{metadata['missing_hs_records']} ore senza Hs: CSV conservato in cache. Controllare i dati o usare --allow-missing.")
    if args.allow_missing:
        import pandas as pd
        frame=pd.read_csv(csv_path)
        valid=frame[args.hs_column].notna()
        metadata['dropped_missing_rows']=int((~valid).sum())
        clean_path=args.cache/f'{args.location}_clean.csv'
        frame.loc[valid].to_csv(clean_path,index=False)
        csv_path=clean_path
    result=build_climate(csv_path,'ERA5',time_column=args.time_column,hs_column=args.hs_column)
    result.update(download=metadata,doi='10.24381/1cf1ad76')
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    temporary.replace(target)
    config['locations'][args.location]['climatology_file']=str(target.relative_to(ROOT))
    temporary_config=config_path.with_suffix('.json.tmp')
    temporary_config.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    temporary_config.replace(config_path)
    print(f'Climatologia salvata in {target}. Rigenerare il bollettino per visualizzarla.')


if __name__=='__main__':
    main()
