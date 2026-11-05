#!/usr/bin/env python3
"""Guided local setup. A draft is the default; --install adds a new location."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from forecast_service.pipeline import load_configuration
from forecast_service.site_setup import slopes_from_transects


def ask(value,prompt,default=None):
    if value is not None:
        return value
    answer=input(prompt+(f' [{default}]' if default is not None else '')+': ').strip()
    return answer or default


def install_draft(root,payload):
    slug=payload['slug']
    if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug):
        raise ValueError('Identificativo della bozza non valido.')
    locations,impacts=load_configuration(root)
    if slug in locations['locations']:
        raise ValueError('Località già esistente: nessuna sovrascrittura.')
    locations['locations'][slug]=payload['location']
    impacts['locations'][slug]={'name':payload['location']['name'],'thresholds':payload['thresholds']}
    with tempfile.TemporaryDirectory() as folder:
        config=Path(folder)/'config'; config.mkdir()
        (config/'locations.json').write_text(json.dumps(locations))
        (config/'impact_thresholds.json').write_text(json.dumps(impacts))
        load_configuration(Path(folder))
    old={name:(root/'config'/name).read_bytes() for name in ('locations.json','impact_thresholds.json')}
    try:
        for name,contents in [('locations.json',locations),('impact_thresholds.json',impacts)]:
            target=root/'config'/name
            temporary=target.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(contents,ensure_ascii=False,indent=2)+'\n')
            temporary.replace(target)
    except Exception:
        for name,contents in old.items():
            (root/'config'/name).write_bytes(contents)
        raise


def main():
    parser=argparse.ArgumentParser(description='Configura una nuova località e salva una bozza da rivedere.')
    for name in ['slug','name','area','summer-start','summer-end','slopes']:
        parser.add_argument('--'+name)
    for name in ['latitude','longitude','wave-lat','wave-lon','z-min','z-max']:
        parser.add_argument('--'+name,type=float)
    parser.add_argument('--profile',type=Path,help='CSV QGIS TR_ID,distance,SAMPLE_1,X,Y oppure profilo 1-D transect_id,x_m,z_m.')
    parser.add_argument('--from-draft',type=Path,help='Installa una bozza già rivista, senza ripetere le domande.')
    parser.add_argument('--install',action='store_true',help='Aggiunge la nuova località ai due file di configurazione dopo validazione.')
    args=parser.parse_args()
    if args.from_draft:
        if not args.install:
            parser.error('--from-draft richiede --install.')
        install_draft(ROOT,json.loads(args.from_draft.read_text()))
        print('Località installata. Preparare il riferimento ERA5 con setup_climatology.py.')
        return
    slug=ask(args.slug,'Identificativo breve (lettere minuscole e trattini)')
    if not slug or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug):
        parser.error('Identificativo non valido.')
    locations,impacts=load_configuration()
    if slug in locations['locations']:
        parser.error('Identificativo già esistente: nessuna località viene sovrascritta.')
    name=ask(args.name,'Nome visibile')
    area=ask(args.area,'Tratto di costa e bacino')
    lat=float(ask(args.latitude,'Latitudine sulla mappa'))
    lon=float(ask(args.longitude,'Longitudine sulla mappa'))
    wlat=float(ask(args.wave_lat,'Latitudine del punto offshore Copernicus',lat))
    wlon=float(ask(args.wave_lon,'Longitudine del punto offshore Copernicus',lon))
    diagnostics=[]
    if args.profile:
        zmin=float(ask(args.z_min,'Quota minima del tratto da usare per la pendenza [m]'))
        zmax=float(ask(args.z_max,'Quota massima del tratto da usare per la pendenza [m]'))
        diagnostics=slopes_from_transects(args.profile,zmin,zmax)
        slopes=sorted(set(round(t['slope'],6) for t in diagnostics))
    else:
        slopes=sorted(set(float(s.strip()) for s in ask(args.slopes,'Pendenze beta separate da virgola','0.03,0.05,0.07').split(',')))
    start=ask(args.summer_start,'Inizio stagione estiva MM-GG (invio per lasciare da definire)','') or None
    end=ask(args.summer_end,'Fine stagione estiva MM-GG (invio per lasciare da definire)','') or None
    loc={'name':name,'area':area,'map_point':{'latitude':lat,'longitude':lon},'wave_point':{'latitude':wlat,'longitude':wlon},
         'slopes':slopes,'roughness_m':.001,'parameters_status':'provisional','datum_offset_m':0.0,
         'vertical_reference_status':'provisional','climatology_file':None,
         'summer_season':{'start_month_day':start,'end_month_day':end,'status':'configured' if start and end else 'to_be_defined'},
         'transects':diagnostics,'notes':'Punti, pendenze, rugosità e quote da verificare. Tutte le direzioni sono incluse.'}
    template=copy.deepcopy(next(iter(impacts['locations'].values()))['thresholds'])
    for threshold in template:
        threshold['elevation_m']=float(input(f"Quota per {threshold.get('short_label',threshold['description'])} [m LMM] [{threshold['elevation_m']}]: ").strip() or threshold['elevation_m'])
    locations['locations'][slug]=loc
    impacts['locations'][slug]={'name':name,'thresholds':template}
    # Exercise the same validation used by scheduled publication, before installing.
    with tempfile.TemporaryDirectory() as folder:
        config=Path(folder)/'config'; config.mkdir()
        (config/'locations.json').write_text(json.dumps(locations))
        (config/'impact_thresholds.json').write_text(json.dumps(impacts))
        load_configuration(Path(folder))
    draft=ROOT/'config/site_drafts'/f'{slug}.json'
    draft.parent.mkdir(parents=True,exist_ok=True)
    with draft.open('x',encoding='utf-8') as handle:
        json.dump({'slug':slug,'location':loc,'thresholds':template,'next_step':f'python scripts/setup_climatology.py {slug}'},handle,ensure_ascii=False,indent=2)
        handle.write('\n')
    if args.install:
        install_draft(ROOT,{'slug':slug,'location':loc,'thresholds':template})
    print(f"{'Località installata' if args.install else 'Bozza salvata'}: {draft}")
    print('Verificare la cella marina e il riferimento delle quote; poi preparare ERA5 con setup_climatology.py.')


if __name__=='__main__':
    main()
