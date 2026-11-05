"""Portable study-site packages exported by the standalone Colab notebook."""
import copy
import json
from pathlib import Path
import re
import tempfile
import zipfile


def validate_payload(payload):
    slug=payload.get('slug','')
    if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug):
        raise ValueError('Identificativo della località non valido.')
    if payload.get('schema_version')!=1 or payload.get('data_mode') not in ('study','demo'):
        raise ValueError('Formato del pacchetto non riconosciuto.')
    if payload.get('data_mode')!='demo' and any(payload.get('provenance',{}).get(key)=='demo' for key in ('profile_data_mode','climate_data_mode')):
        raise ValueError('Dati dimostrativi dichiarati come dati di studio.')
    location=payload['location']
    from forecast_service.exposure import validate_exposure
    validate_exposure(location.get('wave_exposure'))
    if not location.get('slopes') or any(not isinstance(s,(int,float)) or not 0<s<1 for s in location['slopes']):
        raise ValueError('Pendenze non valide.')
    if not payload.get('thresholds'):
        raise ValueError('Soglie mancanti.')
    if location.get('climatology_file') not in (None,f'config/climatology/{slug}.json'):
        raise ValueError('Percorso climatologico non valido nel pacchetto.')
    json.dumps(payload,allow_nan=False)
    return slug


def write_site_package(output,payload,*,climatology=None,attachments=None):
    slug=validate_payload(payload)
    if bool(climatology) != bool(payload['location'].get('climatology_file')):
        raise ValueError('Riferimento climatologico e configurazione non coerenti.')
    if climatology:
        from forecast_service.climate import load_climate
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'climatology.json').write_text(json.dumps(climatology,allow_nan=False))
            load_climate(root,'climatology.json')
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('site.json',json.dumps(payload,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
            if climatology:
                archive.writestr('climatology.json',json.dumps(climatology,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
            for name,path in (attachments or {}).items():
                if not re.fullmatch('[A-Za-z0-9_.-]+',name) or name.startswith('.'):
                    raise ValueError('Nome allegato non valido.')
                archive.write(path,'diagnostics/'+name)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def import_site_package(path,root,*,replace=False,allow_demo=False):
    from forecast_service.pipeline import load_configuration
    from forecast_service.climate import load_climate
    root=Path(root)
    locations,impacts=load_configuration(root)
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)>1000 or sum(m.file_size for m in members)>100*1024*1024:
            raise ValueError('Pacchetto troppo grande.')
        if len({m.filename for m in members})!=len(members):
            raise ValueError('Nomi duplicati nel pacchetto.')
        for member in members:
            name=member.filename
            if name not in ('site.json','climatology.json') and not re.fullmatch(r'diagnostics/[A-Za-z0-9_][A-Za-z0-9_.-]*',name):
                raise ValueError('Percorso non ammesso nel pacchetto.')
        payload=json.loads(archive.read('site.json'))
        slug=validate_payload(payload)
        if payload['data_mode']=='demo' and not allow_demo:
            raise ValueError('Pacchetto dimostrativo: usare --allow-demo soltanto per una prova locale.')
        if slug in locations['locations'] and not replace:
            raise ValueError('Località già presente: usare --replace per aggiornarla intenzionalmente.')
        updates={}
        local=copy.deepcopy(payload['location'])
        if local.get('climatology_file'):
            raw=archive.read('climatology.json')
            with tempfile.TemporaryDirectory() as folder:
                climate_root=Path(folder)
                (climate_root/'climatology.json').write_bytes(raw)
                load_climate(climate_root,'climatology.json')
            updates[local['climatology_file']]=raw
        elif 'climatology.json' in archive.namelist():
            raise ValueError('Climatologia nel pacchetto ma non nella configurazione.')
        locations['locations'][slug]=local
        impacts['locations'][slug]={'name':local['name'],'thresholds':payload['thresholds']}
        for name,contents in [('locations.json',locations),('impact_thresholds.json',impacts)]:
            updates['config/'+name]=(json.dumps(contents,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
        updates[f'config/study_sites/{slug}/site.json']=archive.read('site.json')
        for member in members:
            if member.filename.startswith('diagnostics/'):
                updates[f'config/study_sites/{slug}/'+member.filename]=archive.read(member)
    # Validate merged configuration before touching any existing file.
    with tempfile.TemporaryDirectory() as folder:
        check=Path(folder); (check/'config').mkdir()
        for name in ('locations.json','impact_thresholds.json'):
            (check/'config'/name).write_bytes(updates['config/'+name])
        load_configuration(check)
    old={name:(root/name).read_bytes() if (root/name).exists() else None for name in updates}
    try:
        for name,contents in updates.items():
            destination=root/name; destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.import.tmp')
            temporary.write_bytes(contents); temporary.replace(destination)
    except Exception:
        for name,contents in old.items():
            destination=root/name
            if contents is None:
                destination.unlink(missing_ok=True)
            else:
                destination.write_bytes(contents)
        raise
    return slug
