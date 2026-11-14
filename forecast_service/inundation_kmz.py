"""Portable Google Earth map, with named estimates, dates and survey credits."""
from io import BytesIO
import json
import xml.etree.ElementTree as ET
from zipfile import ZipFile,ZIP_DEFLATED
from zoneinfo import ZoneInfo

from forecast_service.time_utils import parse_time

NS='http://www.opengis.net/kml/2.2'
ET.register_namespace('',NS)


def _element(parent,tag,text=None,**attributes):
    e=ET.SubElement(parent,'{'+NS+'}'+tag,attributes)
    if text is not None:e.text=str(text)
    return e


def _geometry(parent,geometry):
    kind=geometry['type'];coords=geometry['coordinates']
    if kind in ('MultiPolygon','MultiLineString'):
        multi=_element(parent,'MultiGeometry')
        single='Polygon' if kind=='MultiPolygon' else 'LineString'
        for part in coords:_geometry(multi,dict(type=single,coordinates=part))
    elif kind=='Polygon':
        polygon=_element(parent,'Polygon');_element(polygon,'altitudeMode','clampToGround')
        for index,ring in enumerate(coords):
            boundary=_element(polygon,'outerBoundaryIs' if index==0 else 'innerBoundaryIs')
            linear=_element(boundary,'LinearRing')
            _element(linear,'coordinates',' '.join(f'{x:.12f},{y:.12f},0' for x,y,*_ in ring))
    elif kind=='LineString':
        line=_element(parent,'LineString');_element(line,'tessellate',1);_element(line,'altitudeMode','clampToGround')
        _element(line,'coordinates',' '.join(f'{x:.12f},{y:.12f},0' for x,y,*_ in coords))
    else:raise ValueError('Geometria KMZ non supportata: '+kind)


def export_kmz(areas_raw,lines_raw):
    areas=json.loads(areas_raw);lines=json.loads(lines_raw)
    root=ET.Element('{'+NS+'}kml');doc=_element(root,'Document')
    first=areas['features'][0]['properties']
    _element(doc,'name',first['unit_name']+' · inondazione potenziale')
    _element(doc,'description','Prototipo sperimentale, non utilizzare per previsioni operative o decisioni gestionali. '
        'Due stime alternative, ciascuna nell’ora più intensa dei quattro giorni. Non sono probabilità o profondità di allagamento. '
        'Aprire una sola cartella di stima alla volta. Elaborazione UTC: '+first['issued_at_utc']+'. '
        'Rilievo: '+first['survey_credit']+' · '+first['survey_date']+'. Licenza: '+first['license']+'. Quote: '+first['vertical_reference']+'.')
    for kind,color in [('mean','64e8c56b'),('central_upper','73bc8123')]:
        style=_element(doc,'Style',id=kind+'-area')
        polygon=_element(style,'PolyStyle');_element(polygon,'color',color);_element(polygon,'outline',0)
        style=_element(doc,'Style',id=kind+'-line')
        line=_element(style,'LineStyle');_element(line,'color','ffa46c17');_element(line,'width',2)
    for area in areas['features']:
        p=area['properties'];kind=p['estimate']
        folder=_element(doc,'Folder');_element(folder,'name',p['estimate_label'])
        _element(folder,'visibility',1 if kind=='mean' else 0)
        matching=[f for f in lines['features'] if f['properties']['estimate']==kind]
        for role,feature in [('area',area),*[('line',f) for f in matching]]:
            props=feature['properties'];peak=parse_time(props['peak_time_utc']).astimezone(ZoneInfo('Europe/Rome'))
            pm=_element(folder,'Placemark')
            _element(pm,'name',('Area' if role=='area' else 'Limite')+' · '+peak.strftime('%d/%m/%Y %H:%M %Z'))
            windows='; '.join(w['from']+' — '+w['to'] for w in props['peak_windows_utc'])
            _element(pm,'description',props['estimate_label']+'. Picco: '+peak.strftime('%d/%m/%Y %H:%M %Z')+
                '. Finestre della stessa quota (UTC): '+windows+'. TWL: '+str(props['twl_level_m'])+' m. '
                'Quote: '+props['vertical_reference']+'. Elaborazione UTC: '+props['issued_at_utc']+'. '
                'Estensione statica potenziale, non probabilità o profondità. '+('Limite semplificato soltanto per il disegno.' if role=='line' else ''))
            _element(pm,'styleUrl','#'+kind+'-'+role)
            data=_element(pm,'ExtendedData')
            for key,value in props.items():
                field=_element(data,'Data',name=key)
                _element(field,'value',json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value))
            if feature['geometry']:_geometry(pm,feature['geometry'])
    raw=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    buffer=BytesIO()
    with ZipFile(buffer,'w',ZIP_DEFLATED) as archive:archive.writestr('doc.kml',raw)
    return buffer.getvalue()
