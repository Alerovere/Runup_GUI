"""Regenerate the standalone Colab notebook from the shared setup modules."""
from pathlib import Path
import json
import ast
import nbformat as nbf

ROOT=Path(__file__).resolve().parents[1]
def saved_form_values(previous_cells):
    values = {}
    for cell in previous_cells:
        if cell.get('cell_type') != 'code':
            continue
        for line in ''.join(cell['source']).splitlines():
            if '#@param' not in line and line.split('=',1)[0].strip() not in {'QUOTA_OMBRELLONI_M','QUOTA_STRUTTURE_STAGIONALI_M','QUOTA_CHIOSCHI_M','QUOTA_PASSEGGIATA_M','Z_MIN','Z_MAX','ORIENTAMENTO'}:
                continue
            try:
                node = ast.parse(line.split('#@param', 1)[0].strip()).body[0]
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    value = ast.literal_eval(node.value)
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        values[node.targets[0].id] = value
            except (ValueError, SyntaxError, IndexError):
                continue
    return values


def apply_form_values(text, values):
    result = []
    for line in text.splitlines():
        if '#@param' in line or line.split('=',1)[0].strip() in {'Z_MIN','Z_MAX','ORIENTAMENTO'}:
            name = line.split('=', 1)[0].strip()
            if name.isidentifier() and name in values:
                line = f"{name} = {values[name]!r}" + (" #@param" + line.split("#@param",1)[1] if "#@param" in line else "")
        result.append(line)
    return '\n'.join(result)


target = ROOT/'notebooks/Definisci_siti_studio.ipynb'
previous = json.loads(target.read_text()) if target.exists() else {'cells': []}
form_values = saved_form_values(previous['cells'])
# Adopt the requested default; the measured and linear alternatives remain available.
if form_values.get('MODALITA_PENDENZE') == 'Valori dei transetti' and not any('slope-sampling' in c.get('metadata',{}).get('tags',[]) for c in previous['cells']):
    form_values['MODALITA_PENDENZE'] = 'Monte Carlo · normale troncata'
previous_ids = {''.join(cell['source']).splitlines()[0]: cell.get('id')
                for cell in previous['cells'] if ''.join(cell['source']).strip()}
cells=[]
def md(text):
    cells.append(nbf.v4.new_markdown_cell(text.strip()))
def code(text, *, form=True, tags=()):
    cell=nbf.v4.new_code_cell(apply_form_values(text.strip(), form_values))
    if form: cell.metadata['cellView']='form'
    if tags: cell.metadata['tags']=list(tags)
    cells.append(cell)

md('# Onde a riva — Definizione dei siti di studio\n\n**Un’area di studio, con eventuali settori costieri.**\n\nInput dell’area: **DEM e GeoJSON dei transetti**; l’**ortofotomosaico è facoltativo**. Puoi aggiungere un GeoJSON facoltativo dei **punti delle strutture**, con campo `struttura`, per proporre quote medie dal DEM. Il GeoJSON dei poligoni dei **settori costieri è facoltativo**: senza poligoni si rappresenta la spiaggia intera. Non occorre preparare CSV di punti o raster ritagliati.\n\n| Comuni all’area | Specifici del settore costiero |\n|---|---|\n| DEM e ortofoto sorgenti; direzioni di esposizione | Transetti assegnati e relative pendenze |\n| Punto di previsione di onde, surge e marea | Strutture esposte presenti e loro quote |\n| Punto e serie storica ERA5 | Risultati del runup/TWL e ritagli della mappa |\n\nIl percorso è unico: file → profili e pendenze → settori costieri → strutture esposte → ritagli → ERA5 comune → esportazione. I dati di previsione vengono scaricati dal servizio giornaliero, non moltiplicati per settore costiero.\n\n**Il notebook è autosufficiente:** le funzioni del progetto sono incluse nella cella tecnica; non occorre clonare GitHub o pubblicare il sito. Parti in modalità dimostrativa per vedere tutti i passaggi senza credenziali. Per i tuoi dati disattiva `DEMO` e usa le celle in ordine.\n\nPer i profili estratti dal DEM, la pendenza segue **Stockdon_runup_soluzione.ipynb**, celle 24–25: orientamento mare→terra dalla media delle prime/ultime 10 quote; distanza euclidea X/Y dal primo punto a mare; selezione prima del primo punto sopra `Z_MAX`; regressione con `np.polyfit`. Per i transetti GNSS XYZ già rilevati sulla battigia si usa invece l’intero transetto, senza selezione Zmin/Zmax; si può ricalcolare la pendenza oppure usare un campo già calcolato, scelto esplicitamente. Le formule di runup del portale restano invariate. Le pendenze misurate alimentano poi il campionamento Monte Carlo per ciascun settore (oppure per la spiaggia intera).\n\nIl pacchetto finale non contiene token o credenziali. Il notebook non pubblica e non modifica automaticamente la repository.')
md('## 1. Ambiente e cartella di lavoro\nEsegui le tre celle in ordine. **Installa le librerie** prepara il runtime CPU; **Carica le funzioni** contiene il codice tecnico già pronto e non richiede modifiche. Può impiegare qualche minuto: attendi il messaggio finale.\n\nIn **Modalità e salvataggio** disattiva `DEMO` per i tuoi rilievi. Attiva Google Drive per riutilizzare file e cache fra sessioni; indica soltanto il nome della cartella dentro “Il mio Drive”. Le celle mostrano moduli: non occorre aprire il codice.')
code('''#@title Installa le librerie
INSTALLA_DIPENDENZE = True #@param {type:"boolean"}
if INSTALLA_DIPENDENZE:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "numpy>=1.24", "pandas>=2", "matplotlib>=3.7", "folium>=0.14", "pyproj>=3.6", "cdsapi>=0.7.7,<1", "netCDF4>=1.7,<2", "scipy>=1.11,<2", "copernicusmarine==2.4.1", "rasterio>=1.3,<2", "shapely>=2,<3", "ipywidgets>=8,<9"])
print("Ambiente pronto.")''',form=True,tags=('install-dependencies',))
modules=['__init__.py','site_setup.py','time_utils.py','era5_download.py','climate.py','exposure.py','extremes.py','sealevel_reference.py','site_package.py','sectors.py','inundation.py','mapping_setup.py','geospatial_setup.py','gnss_setup.py','gnss_forms.py','structure_forms.py','structure_points.py','contour_preview.py','slope_sampling.py','sector_forms.py','terrain_background.py','demo_survey.py','ensemble.py','LICENSE-wave-climate.txt']
sources={'forecast_service/'+name:(ROOT/'forecast_service'/name).read_text() for name in modules}
for reference_path in sorted(ROOT.glob('config/study_sites/*/sea_level_reference_*.json')):
    sources[str(reference_path.relative_to(ROOT))]=reference_path.read_text()
code('''#@title Carica le funzioni del progetto (cella tecnica)
# Codice condiviso con la repository, incluso per funzionare anche prima del push.
from pathlib import Path
import json, sys, tempfile, hashlib
RUNTIME = Path(tempfile.mkdtemp(prefix="ondeariva_runtime_"))
BUNDLED_SOURCES = '''+repr(sources)+'''
for relative, source in BUNDLED_SOURCES.items():
    target = RUNTIME / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
for module_name in list(sys.modules):
    if module_name=="forecast_service" or module_name.startswith("forecast_service."):
        del sys.modules[module_name]
sys.path.insert(0, str(RUNTIME))
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import folium
try:
    from google.colab import output as colab_output
    colab_output.enable_custom_widget_manager()
except ImportError:
    pass
from IPython.display import display, FileLink
from pyproj import CRS, Transformer
from forecast_service.site_setup import analyze_transects, BEACHFACE_METHOD_VERSION
from forecast_service.era5_download import download_series
from forecast_service.climate import build_climate
from forecast_service.exposure import parse_exposure
from forecast_service.extremes import build_directional_extremes
from forecast_service.sealevel_reference import download_reference, validate_reference, apply_reference
from forecast_service.site_package import write_site_package
print("Metodo pendenze:", BEACHFACE_METHOD_VERSION)''',form=True,tags=('bundled-library',))
code('''#@title Modalità e salvataggio
DEMO = True #@param {type:"boolean"}
USA_GOOGLE_DRIVE = False #@param {type:"boolean"}
CARTELLA_DRIVE = "OndeARiva_setup" #@param {type:"string"}
if USA_GOOGLE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
    BASE = Path("/content/drive/MyDrive") / CARTELLA_DRIVE
else:
    BASE = Path("/content/ondeariva_dati") if Path("/content").exists() else RUNTIME / "dati"
BASE.mkdir(parents=True, exist_ok=True)
print("Modalità:", "DIMOSTRATIVA — profili e onde sintetici" if DEMO else "SITO DI STUDIO — dati dell’utente")
print("Cartella:", BASE)
print("La cartella del runtime è temporanea. Per conservare la cache usa Drive oppure scarica il pacchetto finale.")''',form=True)
md('''## 2. Area di studio e dati marini comuni
Le coordinate sono in gradi WGS84. Il punto sulla mappa identifica il sito; quello offshore serve a scaricare onde Copernicus ed ERA5. La cella marina ERA5 verrà verificata durante il download. Il punto del livello marino può essere distinto da quello delle onde.

I valori iniziali sono quelli provvisori di Borghetto; possono essere sostituiti liberamente. Il campo `ID_SITO` deve usare lettere minuscole, numeri e trattini.''')
code('#@title Identità e punti di estrazione\nID_SITO = "borghetto-santo-spirito" #@param {type:"string"}\nNOME_SITO = "Borghetto Santo Spirito (SV)" #@param {type:"string"}\nTRATTO_DI_COSTA = "Riviera di Ponente · Mar Ligure" #@param {type:"string"}\n#@markdown **Posizione della località sulla mappa** · latitudine e longitudine WGS84.\nLAT_SITO = 44.109 #@param {type:"number"}\nLON_SITO = 8.242 #@param {type:"number"}\n#@markdown **Punto al largo** · coordinate per onde e serie storica.\nLAT_ONDE = 44.046833 #@param {type:"number"}\nLON_ONDE = 8.389593 #@param {type:"number"}\n#@markdown **Livello marino** · lascia attiva la casella se usa lo stesso punto delle onde.\nLIVELLO_STESSO_PUNTO = True #@param {type:"boolean"}\nLAT_LIVELLO = 44.046833 #@param {type:"number"}\nLON_LIVELLO = 8.389593 #@param {type:"number"}\nimport re\nif not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ID_SITO):\n    raise ValueError("ID_SITO non valido.")\nfor lat, lon in [(LAT_SITO,LON_SITO),(LAT_ONDE,LON_ONDE),(LAT_LIVELLO,LON_LIVELLO)]:\n    if not np.isfinite([lat,lon]).all() or not 30<=lat<=46.5 or not -18.2<=lon<=37:\n        raise ValueError("Le coordinate devono essere nel dominio mediterraneo.")\nWORK = BASE / ID_SITO\nWORK.mkdir(parents=True, exist_ok=True)\nSITE_INPUT = dict(name=NOME_SITO, area=TRATTO_DI_COSTA,\n    map_point=dict(latitude=LAT_SITO,longitude=LON_SITO),\n    wave_point=dict(latitude=LAT_ONDE,longitude=LON_ONDE))\nMAPPA = folium.Map(location=[LAT_SITO,LON_SITO],zoom_start=12,tiles="OpenStreetMap")\nfolium.Marker([LAT_SITO,LON_SITO],tooltip="Sito costiero").add_to(MAPPA)\nfolium.CircleMarker([LAT_ONDE,LON_ONDE],radius=7,color="#006d77",tooltip="Punto onde richiesto").add_to(MAPPA)\nfolium.LatLngPopup().add_to(MAPPA)\ndisplay(MAPPA)\nprint("Clicca sulla mappa per leggere coordinate, poi riportale nei campi e riesegui questa cella.")',form=True)

md('''### Direzioni di esposizione — comuni all’intera area
Indica le **direzioni da cui provengono le onde**, non quelle verso cui si muovono: 0° = Nord, 90° = Est, 180° = Sud, 270° = Ovest, in senso orario rispetto al Nord geografico. I settori devono riferirsi al punto offshore scelto e alla spiaggia rappresentata, tenendo conto di costa, promontori e opere.

Scrivi coppie `da,a`, separate da `;` per più settori. Esempi solo di formato: `90,180` comprende Est→Sud; `315,45` attraversa il Nord; `0,360` include tutte le direzioni. Gli estremi sono inclusi. **Lascia vuoto finché non hai definito l’esposizione del sito**: nessun settore di esempio viene applicato automaticamente.

Questi intervalli di provenienza sono comuni a tutti i settori costieri: non sono poligoni della spiaggia. Il portale avverte quando la direzione al largo è fuori dagli intervalli indicati. Questa verifica non simula rifrazione, diffrazione o riparo e non azzera né corregge automaticamente onde, runup o TWL. Anche il confronto storico ERA5 resta riferito a tutte le direzioni.''')
code('''#@title Settori di provenienza delle onde che espongono la spiaggia
SETTORI_PROVENIENZA = "" #@param {type:"string"}
NOTE_ESPOSIZIONE = "" #@param {type:"string"}
ESPOSIZIONE = parse_exposure(SETTORI_PROVENIENZA, NOTE_ESPOSIZIONE)
if ESPOSIZIONE is None:
    print("Esposizione non definita: il portale mostrerà un’avvertenza.")
else:
    display(pd.DataFrame(ESPOSIZIONE["sectors_deg"], columns=["Da (gradi)", "A (gradi, senso orario)"]))
    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw={"projection": "polar"})
    ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
    ax.set_xticks(np.deg2rad(np.arange(0, 360, 45)), ["N", "NE", "E", "SE", "S", "SO", "O", "NO"])
    ax.set_yticks([])
    for start, end in ESPOSIZIONE["sectors_deg"]:
        span = 360 if end-start == 360 else (end-start) % 360
        angles = np.deg2rad(np.linspace(start, start+span, 181))
        ax.fill_between(angles, 0, 1, color="#527d78", alpha=.35)
    ax.set_title("Direzioni di provenienza che espongono la spiaggia")
    plt.show()
    print("Schema orientativo: non è una simulazione della propagazione verso riva.")''',form=True,tags=('wave-exposure',))
md('''### Stagione e parametri di calcolo — comuni all’area
Stagione, rugosità e raccordo del livello marino si impostano una volta. Le strutture esposte saranno definite nel passaggio successivo, separatamente per ogni settore costiero. Indica inizio/fine della stagione in formato `MM-GG`; lascia entrambi vuoti se ancora sconosciuti. La correzione del livello marino raccorda il riferimento del modello a quello locale; non va usata per correggere automaticamente il DEM.''')
code('''#@title Stagione, metodi e riferimento delle quote
INIZIO_ESTATE = "" #@param {type:"string"}
FINE_ESTATE = "" #@param {type:"string"}
QUOTA_OMBRELLONI_M = '''+repr(form_values.get('QUOTA_OMBRELLONI_M',0.7))+'''
QUOTA_STRUTTURE_STAGIONALI_M = '''+repr(form_values.get('QUOTA_STRUTTURE_STAGIONALI_M',0.9))+'''
QUOTA_CHIOSCHI_M = '''+repr(form_values.get('QUOTA_CHIOSCHI_M',1.1))+'''
QUOTA_PASSEGGIATA_M = '''+repr(form_values.get('QUOTA_PASSEGGIATA_M',1.4))+'''
RUGOSITA_M = 0.001 #@param {type:"number"}
OFFSET_LIVELLO_M = 0.0 #@param {type:"number"}
NOTE_SITO = "Parametri di studio; quote e raccordo verticale da validare." #@param {type:"string"}
import datetime as dt
if bool(INIZIO_ESTATE)!=bool(FINE_ESTATE):
    raise ValueError("Indica entrambe le date estive oppure nessuna.")
for value in (INIZIO_ESTATE,FINE_ESTATE):
    if value: dt.datetime.strptime("2000-"+value,"%Y-%m-%d")
heights=[QUOTA_OMBRELLONI_M,QUOTA_STRUTTURE_STAGIONALI_M,QUOTA_CHIOSCHI_M,QUOTA_PASSEGGIATA_M]
if not np.isfinite(heights).all() or heights!=sorted(set(heights)):
    raise ValueError("Le quattro quote devono essere finite e strettamente crescenti.")
if not np.isfinite([RUGOSITA_M,OFFSET_LIVELLO_M]).all() or RUGOSITA_M<0:
    raise ValueError("Rugosità o correzione del livello non valide.")
thresholds=[]
for identifier,height,label,season in zip(
    ["prima_fila_ombrelloni","strutture_turistiche_stagionali","strutture_turistiche_fisse","infrastrutture_fisse"],heights,
    ["Prima fila di ombrelloni","Strutture turistiche stagionali","Chioschi e strutture fisse","Passeggiata a mare"],
    ["summer","summer","all_year","all_year"]):
    thresholds.append(dict(id=identifier,elevation_m=float(height),short_label=label,description="Possibile interessamento: "+label.lower(),season=season))
print("I valori iniziali delle strutture vengono proposti nel modulo successivo, dove possono variare per settore costiero.")''',form=True)
md('## 3. File dell’area: obbligatori e facoltativi\n**Obbligatori per il percorso con mappe:** DEM GeoTIFF e GeoJSON dei transetti. Scegli **DEM + linee** per estrarre le quote dal raster, oppure **GNSS (LineString XYZ)** per usare i punti e le quote misurate sulla battigia. Il DEM resta necessario per le mappe e per le eventuali quote delle strutture. **Facoltativi:** ortofoto GeoTIFF, poligoni dei settori costieri e punti delle strutture con campo `struttura`.\n\nInserisci il percorso Drive di ogni file disponibile. Se lasci vuoto un file obbligatorio, Colab chiede di caricarlo. Per un file facoltativo, lascia sia il percorso vuoto sia la casella disattivata per saltarlo; attiva la casella per caricarlo dal computer. Senza ortofoto, le mappe mostrano il DEM a colori e OpenStreetMap dove mancano quote. Senza settori si usa la spiaggia intera.\n\n**Impostazioni dei file:** quote in metri; CRS dei GeoJSON e campo identificativo devono corrispondere ai dati esportati da QGIS. `PASSO_CAMPIONAMENTO_M=0` segue il pixel DEM. Nel percorso DEM le quote provengono dal raster; nel percorso GNSS dalla terza coordinata Z del GeoJSON, in metri. Il GNSS ha un proprio riferimento verticale e una correzione separata. Non viene eseguita una conversione automatica fra quote ellissoidiche, ortometriche o livello medio mare. Per i GNSS, dopo la lettura del file scegli i campi nei menu: ID, pendenza β (facoltativa nel ricalcolo) e R² fornito (facoltativo, per confronto). Il CRS dichiarato viene proposto automaticamente e deve essere confermato.\n\nI punti delle strutture vanno sul terreno o sulla quota d’accesso, non sui tetti. La cartella locale `notebooks/dati originali/` non viene trasferita automaticamente su Colab.')
code('#@title File dell’area di studio\nSORGENTE_PENDENZE = "DEM + linee" #@param ["DEM + linee", "GNSS (LineString XYZ)"]\nFILE_DEM_PROFILI = "" #@param {type:"string"}\nFILE_ORTOFOTO_COMUNE = "" #@param {type:"string"}\nUSA_ORTOFOTO = False #@param {type:"boolean"}\nFILE_TRANSETTI_GEOJSON = "" #@param {type:"string"}\nFILE_AREE_GEOJSON = "" #@param {type:"string"}\nFILE_PUNTI_STRUTTURE = "" #@param {type:"string"}\nUSA_PUNTI_STRUTTURE = False #@param {type:"boolean"}\nUSA_AREE_GEOJSON = False #@param {type:"boolean"}\nprint("Percorsi impostati. Esegui la cella successiva per leggere i dati.")',form=True,tags=('area-inputs',))
code('#@title Sistema di coordinate e lettura dei file\n#@markdown **CRS di lavoro:** deve essere proiettato in metri. Serve a entrambi i percorsi.\nCRS_PROFILI = "EPSG:32632" #@param {type:"string"}\n#@markdown **Poligoni e punti delle strutture, se presenti:** campi e CRS dei relativi file.\nCOL_ID_AREE = "sector_id" #@param {type:"string"}\nCOL_NOME_AREE = "name" #@param {type:"string"}\nCRS_GEOJSON_AREE = "EPSG:4326" #@param {type:"string"}\nCOL_STRUTTURA = "struttura" #@param {type:"string"}\nCRS_GEOJSON_STRUTTURE = "EPSG:4326" #@param {type:"string"}\n#@markdown **Solo per DEM + linee:** questi campi definiscono ID, CRS delle linee e passo del campionamento. Il GNSS avrà i suoi menu dopo la lettura del file.\nCOL_ID_GEOJSON = "TR_ID" #@param {type:"string"}\nCRS_GEOJSON_TRANSETTI = "EPSG:4326" #@param {type:"string"}\nPASSO_CAMPIONAMENTO_M = 0.0 #@param {type:"number"}\n#@markdown **Quote del DEM:** la correzione si applica ai profili DEM e ai punti delle strutture. Le quote GNSS hanno impostazioni separate.\nCORREZIONE_QUOTE_DEM_M = 0.0 #@param {type:"number"}\nRIFERIMENTO_QUOTE = "Livello medio mare, da verificare" #@param {type:"string"}\nCOL_ID, COL_DIST, COL_Z, COL_X, COL_Y = "TR_ID", "distance", "SAMPLE_1", "X", "Y"\ncrs = CRS.from_user_input(CRS_PROFILI)\nif not crs.is_projected or not all(abs(a.unit_conversion_factor-1)<1e-9 for a in crs.axis_info[:2]):\n    raise ValueError("Usa un CRS di lavoro proiettato in metri.")\n\ndef scegli_file(percorso, messaggio):\n    if percorso:\n        source = Path(percorso)\n    else:\n        print(messaggio)\n        from google.colab import files\n        uploaded = files.upload()\n        if len(uploaded) != 1:\n            raise ValueError("Seleziona un solo file per questo passaggio.")\n        name, content = next(iter(uploaded.items()))\n        source = WORK / Path(name).name\n        source.write_bytes(content)\n    if not source.is_file():\n        raise ValueError(f"File non trovato: {source}")\n    return source\n\nAREAS_SOURCE = None\nSTRUCTURES_SOURCE = None\nif DEMO:\n    from forecast_service.demo_survey import create_demo_survey\n    DEM_SOURCE, ORTHO_SOURCE, GEO_TRANSECTS_SOURCE = create_demo_survey(WORK/"input_DEMO", LAT_SITO, LON_SITO, CRS_PROFILI)\n    print("DEM, immagine e transetti sintetici: nessun rilievo reale.")\nelse:\n    DEM_SOURCE = scegli_file(FILE_DEM_PROFILI, "1/2 · Carica il DEM GeoTIFF dell’intera area")\n    ORTHO_SOURCE = scegli_file(FILE_ORTOFOTO_COMUNE, "Facoltativo · Carica l’ortofotomosaico GeoTIFF") if FILE_ORTOFOTO_COMUNE or USA_ORTOFOTO else None\n    GEO_TRANSECTS_SOURCE = scegli_file(FILE_TRANSETTI_GEOJSON, "2/2 · Carica il GeoJSON delle linee dei transetti")\n    if USA_AREE_GEOJSON or FILE_AREE_GEOJSON:\n        AREAS_SOURCE = scegli_file(FILE_AREE_GEOJSON, "Facoltativo · Carica i poligoni dei settori costieri")\n    if USA_PUNTI_STRUTTURE or FILE_PUNTI_STRUTTURE:\n        STRUCTURES_SOURCE = scegli_file(FILE_PUNTI_STRUTTURE, "Facoltativo · Carica il GeoJSON dei punti delle strutture")\nPROFILE_SOURCE_KIND = "DEM + linee" if DEMO else SORGENTE_PENDENZE\nGNSS_FIELD_EDITOR = None\nGNSS_FIELDS = None\nif PROFILE_SOURCE_KIND == "GNSS (LineString XYZ)":\n    from forecast_service.gnss_forms import GNSSFieldEditor\n    try:\n        from google.colab import output as colab_output\n        colab_output.enable_custom_widget_manager()\n    except ImportError:\n        pass\n    GNSS_FIELD_EDITOR = GNSSFieldEditor(GEO_TRANSECTS_SOURCE)\n    print("Transetti GNSS:", GNSS_FIELD_EDITOR.schema["count"], "· conferma i campi qui sotto, poi esegui Leggi i profili.")\n    display(GNSS_FIELD_EDITOR.view)\nelse:\n    print("Percorso DEM: le quote saranno estratte dal raster. Esegui Leggi i profili.")',form=True,tags=("area-read",))
code('#@title Leggi i profili dalla sorgente scelta\nif PROFILE_SOURCE_KIND != ("DEM + linee" if DEMO else SORGENTE_PENDENZE):\n    raise ValueError("Sorgente cambiata: riesegui la lettura dei file prima di proseguire.")\nif GNSS_FIELD_EDITOR:\n    from forecast_service.gnss_setup import extract_gnss_profiles\n    GNSS_FIELDS = GNSS_FIELD_EDITOR.read()\n    options={key:GNSS_FIELDS[key] for key in ["geojson_crs","id_field","slope_field","r2_field","z_correction_m"]}\n    profili,diagnostica_estrazione,GEO_PREPROCESSING = extract_gnss_profiles(GEO_TRANSECTS_SOURCE,profile_crs=CRS_PROFILI,**options)\n    GEO_PREPROCESSING.update(slope_source=GNSS_FIELDS["slope_source"],vertical_reference=GNSS_FIELDS["vertical_reference"])\n    PROFILE_SOURCE = f"{GEO_TRANSECTS_SOURCE.name} · vertici GNSS XYZ"\n    PROFILE_VERTICAL_REFERENCE = GNSS_FIELDS["vertical_reference"]\n    PROFILE_Z_CORRECTION = GNSS_FIELDS["z_correction_m"]\n    print("Usati tutti i vertici GNSS originali: nessun campionamento delle quote dal DEM, nessuna selezione Zmin/Zmax.")\nelse:\n    from forecast_service.geospatial_setup import extract_dem_profiles\n    profili, diagnostica_estrazione, GEO_PREPROCESSING = extract_dem_profiles(\n        DEM_SOURCE, GEO_TRANSECTS_SOURCE, profile_crs=CRS_PROFILI,\n        geojson_crs="EPSG:4326" if DEMO else CRS_GEOJSON_TRANSETTI,\n        id_field="TR_ID" if DEMO else COL_ID_GEOJSON, step_m=PASSO_CAMPIONAMENTO_M)\n    profili[COL_Z] += CORREZIONE_QUOTE_DEM_M\n    PROFILE_SOURCE = f"{GEO_TRANSECTS_SOURCE.name} + {DEM_SOURCE.name}"\n    PROFILE_VERTICAL_REFERENCE = RIFERIMENTO_QUOTE\n    PROFILE_Z_CORRECTION = CORREZIONE_QUOTE_DEM_M\n    print("Passo dei profili:",GEO_PREPROCESSING["step_m"],"m")\nPROFILE_DATA_MODE = "demo" if DEMO else "study"\ndiagnostica_estrazione.to_csv(WORK/"estrazione_transetti.csv", index=False)\ndisplay(diagnostica_estrazione)\nPROFILE_CONFIG_SIGNATURE = json.dumps(GNSS_FIELDS,sort_keys=True)\nprint("I dati originali restano sorgenti locali. Verifica ora le impostazioni di pendenza.")',tags=('profile-read',))
md('## 4. Pendenza dei transetti: imposta, calcola e controlla\n**DEM + linee:** scegli Zmin/Zmax per delimitare la battigia, come nel notebook didattico già usato. Il fit si ferma prima del primo superamento di Zmax.\n\n**GNSS:** i transetti sono già rilevati sulla battigia, quindi **si usano tutti i vertici XYZ senza Zmin/Zmax**. Con il ricalcolo, si regredisce la quota sulla distanza euclidea X/Y dal primo punto a mare; non si aggiungono punti né si campiona il DEM. Se scegli “Usa il campo pendenza”, il valore selezionato viene conservato come β e distinto dal ricalcolo. Il campo R² fornito resta un riferimento separato, non un filtro automatico.\n\nNel modulo qui sotto il GNSS mostra soltanto l’orientamento. Per profili corti, l’orientamento automatico confronta gruppi alle estremità senza sovrapporli. Controlla i grafici e le linee curve o con ritorni: non vengono rettificate automaticamente. Dopo le impostazioni esegui **Calcola le pendenze**, poi controlla ed eventualmente escludi i transetti non validi.')
code('#@title Imposta il calcolo della pendenza\nfrom forecast_service.gnss_forms import ProfileFitEditor\nZ_MIN = 0.0\nZ_MAX = 1.0\nORIENTAMENTO = "auto"\nFIT_EDITOR = ProfileFitEditor(gnss=PROFILE_SOURCE_KIND=="GNSS (LineString XYZ)",z_min=Z_MIN,z_max=Z_MAX,orientation=ORIENTAMENTO)\ndisplay(FIT_EDITOR.view)\nprint("Conferma le impostazioni, poi esegui Calcola le pendenze.")',form=True)
code('#@title Calcola le pendenze dei transetti\nFIT_SETTINGS = FIT_EDITOR.read()\nZ_MIN,Z_MAX,ORIENTAMENTO = FIT_SETTINGS["z_min"],FIT_SETTINGS["z_max"],FIT_SETTINGS["orientation"]\nif PROFILE_SOURCE_KIND=="GNSS (LineString XYZ)":\n    if GNSS_FIELD_EDITOR.read()!=GNSS_FIELDS:\n        raise ValueError("Campi GNSS cambiati: riesegui Leggi i profili prima di calcolare le pendenze.")\n    from forecast_service.gnss_setup import analyze_gnss_transects,GNSS_OLS_METHOD,GNSS_ATTRIBUTE_METHOD\n    riepilogo,preparati,selezioni=analyze_gnss_transects(profili,references=GEO_PREPROCESSING["references"],\n        slope_source=GNSS_FIELDS["slope_source"],orientation=ORIENTAMENTO)\n    PROFILE_FIT_METHOD=GNSS_OLS_METHOD if GNSS_FIELDS["slope_source"]=="xyz" else GNSS_ATTRIBUTE_METHOD\nelse:\n    riepilogo,preparati,selezioni=analyze_transects(profili,Z_MIN,Z_MAX,\n        id_col=COL_ID,distance_col=COL_DIST,elevation_col=COL_Z,x_col=COL_X,y_col=COL_Y,orientation=ORIENTAMENTO)\n    PROFILE_FIT_METHOD=BEACHFACE_METHOD_VERSION\ndisplay(riepilogo)\nANALYSIS_SIGNATURE=(PROFILE_SOURCE_KIND,FIT_SETTINGS,PROFILE_CONFIG_SIGNATURE,COL_ID,COL_DIST,COL_Z,COL_X,COL_Y,\n    hashlib.sha256(pd.util.hash_pandas_object(profili,index=True).values.tobytes()).hexdigest())\nriepilogo.to_csv(WORK/"pendenze_transetti.csv",index=False)\nvalidi=riepilogo[riepilogo.status=="valid"]\nif validi.empty:raise ValueError("Nessun transetto valido: controlla i dati, i campi e l’orientamento.")\nprint("Metodo usato:",PROFILE_FIT_METHOD)\nprint("Pendenze valide:",validi.slope.min(),"—",validi.slope.max(),"m/m")\nif validi.orientation_ambiguous.any():print("Orientamento automatico ambiguo per alcuni transetti: controlla i grafici o scegli manualmente il lato mare.")',tags=('profile-analysis',))
code('#@title Verifica un transetto nel grafico\nID_TRANSETTO_DA_VEDERE = "" #@param {type:"string"}\nidentifier=ID_TRANSETTO_DA_VEDERE or str(validi.iloc[0].transect_id)\nif DEMO and identifier not in preparati: identifier=str(validi.iloc[0].transect_id)\nif identifier not in preparati:\n    raise ValueError("Transetto non valido o inesistente; scegli un ID dalla tabella.")\np=preparati[identifier]; sel=selezioni[identifier]\ninfo=validi[validi.transect_id==identifier].iloc[0]\nfig,ax=plt.subplots(figsize=(10,4))\nax.plot(p.x_mare,p[COL_Z],color=".35",label="Profilo completo")\nax.scatter(p.loc[sel,"x_mare"],p.loc[sel,COL_Z],color="#d87832",label="Punti usati nella regressione",zorder=3)\nxfit=p.loc[sel,"x_mare"]\nax.plot(xfit,info.slope*xfit+info.fit_intercept_m,color="#b54135",ls="--",label="Retta stimata" if PROFILE_FIT_METHOD!="gnss_slope_attribute_v1" else "Retta associata alla pendenza fornita")\nif Z_MIN is not None:\n    ax.axhspan(Z_MIN,Z_MAX,color="#d5e9ee",alpha=.35,label="Intervallo di quota")\nif info.first_above_zmax_found:\n    ax.axvline(p.loc[int(info.stop_index),"x_mare"],color="#8b633f",ls=":",label="Primo punto sopra Z_MAX")\nax.set(xlabel="Distanza euclidea dal primo punto a mare [m]",ylabel=f"Quota [m] · {PROFILE_VERTICAL_REFERENCE}",\n       title=f"{\'DEMO · \' if DEMO else \'\'}{identifier}: beta = {info.slope:.4f}, R² = {info.r_squared:.3f}")\nax.legend(fontsize=8); ax.grid(alpha=.2); fig.tight_layout()\nfig.savefig(WORK/"profilo_selezionato.png",dpi=170)\nPLOT_ANALYSIS_SIGNATURE=ANALYSIS_SIGNATURE\nplt.show()',form=True)
md('Controlla soprattutto che il primo punto sia dalla parte del mare e che i punti arancioni rappresentino la battigia. L’esclusione dietro il primo superamento di `Z_MAX` riprende il notebook didattico; non costituisce una simulazione della connessione idraulica o dell’inondazione. Con il GNSS i punti arancioni comprendono tutti i vertici; non si applica il filtro di quota del percorso DEM.')
code('#@title Conferma i transetti da includere\n#@markdown Lascia vuoto per includere tutti i transetti validi. Per escluderne alcuni, scrivi gli ID separati da virgole.\nTRANSETTI_ESCLUSI = "" #@param {type:"string"}\nexcluded={v.strip() for v in TRANSETTI_ESCLUSI.split(",") if v.strip()}\nunknown=excluded-set(riepilogo.transect_id)\nif unknown:\n    raise ValueError(f"ID da escludere non riconosciuti: {unknown}")\nscelti=riepilogo[~riepilogo.transect_id.isin(excluded)].copy()\nif scelti.empty or (scelti.status!="valid").any():\n    raise ValueError("Correggi i transetti non validi o escludili esplicitamente prima di esportare.")\nPENDENZE=sorted(set(float(value) for value in scelti.slope))\nSELECTION_ANALYSIS_SIGNATURE=ANALYSIS_SIGNATURE\nprint(f"Transetti inclusi: {len(scelti)}. Il campionamento delle pendenze si imposta dopo l’assegnazione ai settori.")',form=True)
md('## 5. Settori costieri, nomi e variabilità delle pendenze\nEsegui **Controlla l’assegnazione**. Ogni transetto è assegnato usando il centro del tratto di battigia impiegato per la pendenza. Se il punto è in più poligoni o sul confine, scegli il settore nel menu. Le opzioni sono limitate ai settori che intersecano il tratto usato per il fit; senza opzioni occorre correggere il poligono. Le linee non vengono tagliate.\n\nPoi esegui **Assegna**, modifica i **nomi pubblici** nelle caselle e prosegui con **Conferma nomi e campiona**. Gli ID tecnici rimangono invariati. Senza poligoni compare una sola scheda per la spiaggia intera. Onde, livello marino, esposizione e dati storici restano comuni all’area.')
code('#@title Controlla l’assegnazione dei transetti\nimport copy\nfrom forecast_service.sectors import resolve_sectors\nfrom forecast_service.geospatial_setup import sector_assignment_choices, sectors_from_beachfaces, reproject_geometry\nfrom forecast_service.sector_forms import SectorAssignmentEditor, SectorNameEditor\ntry:\n    from google.colab import output as colab_output\n    colab_output.enable_custom_widget_manager()\nexcept ImportError:\n    pass\nASSEGNAZIONI_EDITOR = None\nif AREAS_SOURCE:\n    proposte, nomi = sector_assignment_choices(AREAS_SOURCE, preparati, selezioni, scelti.transect_id,\n        profile_crs=CRS_PROFILI,geojson_crs=CRS_GEOJSON_AREE,id_field=COL_ID_AREE,name_field=COL_NOME_AREE,x_col=COL_X,y_col=COL_Y)\n    ASSEGNAZIONI_EDITOR = SectorAssignmentEditor(proposte, nomi)\n    print(f"{sum(r[\'automatic\'] is not None for r in proposte)} transetti assegnati automaticamente su {len(proposte)}.")\n    display(ASSEGNAZIONI_EDITOR.view)\nelse:\n    print("Spiaggia intera: nessuna assegnazione da scegliere. Esegui la cella successiva.")',tags=('coastal-sectors',))
code('#@title Assegna i transetti ai settori costieri\nSETTORI_SPIAGGIA = {}\nASSEGNAZIONI_MANUALI = ASSEGNAZIONI_EDITOR.read() if ASSEGNAZIONI_EDITOR else {}\nif AREAS_SOURCE:\n    SETTORI_SPIAGGIA, POLIGONI_SETTORI, assegnazioni = sectors_from_beachfaces(\n        AREAS_SOURCE, preparati, selezioni, scelti.transect_id,\n        profile_crs=CRS_PROFILI, geojson_crs=CRS_GEOJSON_AREE,\n        id_field=COL_ID_AREE, name_field=COL_NOME_AREE,\n        x_col=COL_X, y_col=COL_Y, manual=ASSEGNAZIONI_MANUALI)\n    assegnazioni.to_csv(WORK/"assegnazioni_settori.csv", index=False)\n    UNITA_COSTIERE = {key:value["name"] for key,value in SETTORI_SPIAGGIA.items()}\n    display(assegnazioni.groupby("sector_id").size().rename("Numero di transetti").to_frame())\nelse:\n    import rasterio\n    from shapely.geometry import box, mapping\n    with rasterio.open(DEM_SOURCE) as source_dem:\n        POLIGONI_SETTORI = {"whole": mapping(reproject_geometry(box(*source_dem.bounds), source_dem.crs, "EPSG:4326"))}\n    UNITA_COSTIERE = {"whole": NOME_SITO + " · spiaggia intera"}\nNOMI_SETTORI_EDITOR = SectorNameEditor(UNITA_COSTIERE)\nprint("Modifica qui i nomi da mostrare sul sito, poi esegui la cella successiva.")\ndisplay(NOMI_SETTORI_EDITOR.view)\nSECTOR_ANALYSIS_SIGNATURE = ANALYSIS_SIGNATURE')
md('### Come entrano le pendenze nel runup\nOgni pendenza campionata viene applicata a ciascuna formula empirica, usando le stesse onde del settore. I transetti restano misure di riferimento, non previsioni indipendenti. Il campionamento rappresenta una scelta sulla variabilità della spiaggia: non attribuisce probabilità agli eventi o ai modelli. I percentili dei risultati restano indicatori di sensibilità.\n\nL’ipotesi normale è un’opzione da controllare con gli istogrammi sotto. Media e deviazione standard (divisore N) sono quelle dei valori misurati, prima del troncamento; la media dei campioni può quindi differire. Rimangono disponibili l’uso diretto delle pendenze misurate e l’intervallo regolare.')
code('#@title Conferma nomi e campiona le pendenze per settore\n#@markdown **Monte Carlo:** media e deviazione standard sono calcolate sulle pendenze misurate del singolo settore. La normale è troncata al suo minimo e massimo misurati. Con un solo valore distinto si usa una pendenza fissa.\nMODALITA_PENDENZE = "Monte Carlo · normale troncata" #@param ["Monte Carlo · normale troncata", "Valori dei transetti", "Intervallo minimo-massimo"]\nNUM_CAMPIONI_MC = 200 #@param {type:"integer"}\nSEME_MONTE_CARLO = 42 #@param {type:"integer"}\n#@markdown `NUM_PENDENZE` è usato soltanto nell’alternativa “Intervallo minimo-massimo”.\nNUM_PENDENZE = 5 #@param {type:"integer"}\nfrom forecast_service.slope_sampling import sample_slopes\nUNITA_COSTIERE = NOMI_SETTORI_EDITOR.read()\nfor key,sector in SETTORI_SPIAGGIA.items():sector["name"] = UNITA_COSTIERE[key]\nmethod={"Monte Carlo · normale troncata":"truncated_normal","Valori dei transetti":"measured","Intervallo minimo-massimo":"linear_range"}[MODALITA_PENDENZE]\ncount=NUM_CAMPIONI_MC if method=="truncated_normal" else NUM_PENDENZE if method=="linear_range" else 200\nPENDENZE, SLOPE_SAMPLING = sample_slopes(scelti.slope.tolist(),method=method,count=count,seed=SEME_MONTE_CARLO,unit_id="whole")\nSLOPE_SAMPLING_BY_UNIT = {}; rows=[]; sampled_rows=[]\nfor unit,name in UNITA_COSTIERE.items():\n    local = scelti if unit=="whole" else scelti[scelti.transect_id.isin(SETTORI_SPIAGGIA[unit]["transect_ids"])]\n    values,metadata = sample_slopes(local.slope.tolist(),method=method,count=count,seed=SEME_MONTE_CARLO,unit_id=unit)\n    SLOPE_SAMPLING_BY_UNIT[unit] = metadata\n    if unit!="whole":SETTORI_SPIAGGIA[unit].update(slopes=values,slope_sampling=metadata)\n    rows.append({"Settore":name,"Transetti":metadata["source_count"],"Media misurata β":metadata["source_mean"],\n        "Deviazione standard β":metadata["source_std"],"Minimo β":metadata["source_min"],"Massimo β":metadata["source_max"],"Campioni usati":len(values)})\n    sampled_rows.extend({"sector_id":unit,"slope":v} for v in values)\n    fig,ax=plt.subplots(figsize=(7,3))\n    ax.hist(local.slope,bins="auto",alpha=.55,label="Transetti misurati",density=True,color="#768b6e")\n    ax.hist(values,bins="auto",histtype="step",linewidth=2,label="Pendenze per i modelli",density=True,color="#9b632d")\n    ax.set(title=name,xlabel="Pendenza β = dislivello / distanza",ylabel="Densità relativa");ax.legend();display(fig);plt.close(fig)\ndisplay(pd.DataFrame(rows).set_index("Settore").T)\npd.DataFrame(sampled_rows).to_csv(WORK/"pendenze_campionate.csv",index=False)\n(WORK/"campionamento_pendenze.json").write_text(json.dumps(SLOPE_SAMPLING_BY_UNIT,ensure_ascii=False,indent=2))\nSLOPE_OPTIONS_SIGNATURE=(MODALITA_PENDENZE,NUM_CAMPIONI_MC,SEME_MONTE_CARLO,NUM_PENDENZE)\npreview_location=dict(SITE_INPUT,slopes=PENDENZE,roughness_m=float(RUGOSITA_M),transects=scelti.to_dict(orient="records"),wave_exposure=ESPOSIZIONE,sectors=SETTORI_SPIAGGIA)\nresolve_sectors(preview_location, thresholds)\nprint("Campioni salvati: verranno riutilizzati nelle previsioni, senza nuove estrazioni giornaliere. Non sono probabilità di allagamento.")',tags=('slope-sampling',))
md('''## 6. Strutture esposte — una scheda per settore costiero
Qui definisci **quali strutture sono presenti**, il loro nome, la quota e l’attività estiva o annuale. Deseleziona quelle assenti e usa “Aggiungi struttura” per altre strutture. Gli elenchi possono essere diversi tra settori costieri. Se la spiaggia non è suddivisa, compare una sola scheda.

Con un GeoJSON dei punti, il modulo parte soltanto dalle strutture mappate in ogni settore costiero e dalla media delle quote valide lette dal DEM originale. Minimo, massimo e numero di punti restano visibili; la media non rappresenta la quota del primo punto che potrebbe essere raggiunto. Senza punti, le quattro strutture iniziali restano esempi da verificare, non vincoli. Le quote devono usare lo stesso riferimento verticale del TWL. Dopo le modifiche esegui la cella di verifica; l’esportazione legge nuovamente il modulo aggiornato.''')
code('#@title Quote delle strutture dai punti sul DEM (facoltativo)\nESCLUDI_PUNTI_STRUTTURE_NON_VALIDI = False #@param {type:"boolean"}\nPROPOSTE_STRUTTURE = None\nSTRUCTURE_POINT_META = None\nif STRUCTURES_SOURCE:\n    from forecast_service.structure_points import thresholds_from_structure_points\n    PROPOSTE_STRUTTURE, PUNTI_STRUTTURE_REPORT, STRUTTURE_QUOTE_RIEPILOGO, STRUCTURE_POINT_META = thresholds_from_structure_points(\n        DEM_SOURCE, STRUCTURES_SOURCE, POLIGONI_SETTORI,\n        geojson_crs=CRS_GEOJSON_STRUTTURE, label_field=COL_STRUTTURA,\n        elevation_correction_m=CORREZIONE_QUOTE_DEM_M)\n    PUNTI_STRUTTURE_REPORT.to_csv(WORK/"quote_strutture_punti.csv", index=False)\n    STRUTTURE_QUOTE_RIEPILOGO.to_csv(WORK/"quote_strutture_riepilogo.csv", index=False)\n    display(STRUTTURE_QUOTE_RIEPILOGO[["sector_id", "structure", "mean_elevation_m", "min_elevation_m", "max_elevation_m", "n_valid", "n_excluded"]].rename(columns={"sector_id":"Settore costiero", "structure":"Struttura", "mean_elevation_m":"Quota media (m)", "min_elevation_m":"Quota minima (m)", "max_elevation_m":"Quota massima (m)", "n_valid":"Punti validi", "n_excluded":"Punti esclusi"}))\n    invalidi = PUNTI_STRUTTURE_REPORT[PUNTI_STRUTTURE_REPORT.status != "valid"]\n    if len(invalidi):\n        display(invalidi[["point_index", "feature_id", "structure", "sector_id", "status", "reason"]])\n        if not ESCLUDI_PUNTI_STRUTTURE_NON_VALIDI:\n            raise ValueError("Ci sono punti senza quota valida o con assegnazione ambigua: correggi il GeoJSON oppure conferma esplicitamente l’esclusione con la casella sopra e riesegui.")\n    print("Quote proposte: media aritmetica dei punti validi per struttura e settore costiero.")\n    print("Correzione verticale del DEM applicata:", CORREZIONE_QUOTE_DEM_M, "m; la stessa dovrà essere usata per il DEM della mappa.")\n    print("Per i punti senza campo stagione è proposta l’attività annuale: verifica e modifica nel modulo.")\nelse:\n    print("Nessun GeoJSON dei punti: compila manualmente le strutture come prima.")\n',form=True,tags=('structure-points',))
code('#@title Compila le strutture esposte\nfrom forecast_service.structure_forms import StructureEditor\ntry:\n    from google.colab import output as colab_output\n    colab_output.enable_custom_widget_manager()\nexcept ImportError:\n    pass\nSTRUTTURE_EDITOR = StructureEditor(UNITA_COSTIERE, thresholds, by_unit=PROPOSTE_STRUTTURE)\ndisplay(STRUTTURE_EDITOR.view)',tags=('exposed-structures',))
code('''#@title Verifica le strutture per ciascun settore costiero
STRUTTURE_PER_UNITA = STRUTTURE_EDITOR.read()
for key, values in STRUTTURE_PER_UNITA.items():
    print(UNITA_COSTIERE[key])
    display(pd.DataFrame(values, columns=["short_label", "elevation_m", "season"])[["short_label", "elevation_m", "season"]])
    if key != "whole": SETTORI_SPIAGGIA[key]["thresholds"] = values
thresholds = STRUTTURE_PER_UNITA.get("whole", next(iter(STRUTTURE_PER_UNITA.values())))''',tags=('validate-structures',))
md('## 7. Prepara le mappe: tre moduli, poi il controllo\nEsegui nell’ordine **7A Crediti**, **7B Quote**, **7C Risoluzione** e **Prepara i ritagli**. DEM e ortofoto eventualmente presente sono già caricati. Il preprocessing prepara un ritaglio per settore oppure per la spiaggia intera; gli originali restano invariati.\n\nCon ortofoto si pubblica un’immagine a 0,5 m/pixel. Senza ortofoto si usa il DEM con legenda delle quote; NoData ed esterno del ritaglio sono trasparenti, con OpenStreetMap sotto. Qui controlli i dati cartografici; le previsioni dei quattro giorni vengono aggiunte dal servizio giornaliero.\n\nCon transetti GNSS, gli avvii delle mappe vengono controllati con campioni del **DEM**, orientati secondo il rilievo GNSS. Questi campioni servono soltanto alla cartografia e non modificano le pendenze GNSS. Le quote GNSS non vengono confrontate direttamente con il DEM per assumere un raccordo verticale.')
code('#@title 7A · Autore, data e licenza del rilievo\n#@markdown Indica chi ha prodotto i dati, quando sono stati acquisiti e con quale licenza possono essere pubblicati. Queste informazioni compariranno sul sito.\nCREDITI_RILIEVI = "" #@param {type:"string"}\nDATA_RILIEVI = "" #@param {type:"string"}\nLICENZA_RILIEVI = "" #@param {type:"string"}',form=True)
code('#@title 7B · Riferimento verticale delle quote\n#@markdown Specifica lo zero del DEM. La correzione in metri si **somma** al DEM della mappa. Conferma il raccordo soltanto dopo aver verificato che DEM e livello totale dell’acqua abbiano lo stesso riferimento.\nRIFERIMENTO_VERTICALE_MAPPA = "" #@param {type:"string"}\nCORREZIONE_DEM_MAPPA_M = 0.0 #@param {type:"number"}\nRACCORDO_VERTICALE_CONFERMATO = False #@param {type:"boolean"}')
code('#@title 7C · Risoluzione e margine del ritaglio\n#@markdown L’ortofoto usa il passo indicato in metri/pixel, se presente. Il margine mantiene terreno circostante nel calcolo della connessione; non allarga l’area visualizzata. La griglia DEM cartografica è leggera: verifica le opere strette nell’anteprima.\nRISOLUZIONE_ORTOFOTO_M = 0.5 #@param {type:"number"}\nMARGINE_CLIPPING_M = 100.0 #@param {type:"number"}\n#@markdown **Controllo avanzato degli avvii:** se il primo punto cade su NoData, la ricerca prosegue soltanto sullo stesso transetto entro questi limiti di distanza e rialzo. Non modifica il DEM. Inizia con i valori proposti e controlla gli spostamenti nel riepilogo.\nMAX_AVANZAMENTO_AVVIO_M = 5.0 #@param {type:"number"}\nMAX_RIALZO_AVVIO_M = 0.5 #@param {type:"number"}\n#@markdown Per un’eccezione manuale: seleziona una sola unità e indica punti WGS84 come `[[longitudine, latitudine], ...]`. Lascia entrambi i campi vuoti per la ricerca automatica.\nUNITA_AVVII_MANUALI = "" #@param {type:"string"}\nPUNTI_AVVIO_MANUALI_JSON = "" #@param {type:"string"}')
code('#@title Prepara i ritagli per il sito\nfrom forecast_service.mapping_setup import prepare_mapping, SeedSelectionError\nif STRUCTURE_POINT_META and not np.isclose(CORREZIONE_DEM_MAPPA_M, STRUCTURE_POINT_META["elevation_correction_m"], rtol=0, atol=1e-9):\n    raise ValueError("Punti delle strutture e mappa usano lo stesso DEM: verificare e uniformare la correzione verticale prima di preparare i ritagli.")\nPUNTI_MARE_MANUALI = {}\nif UNITA_AVVII_MANUALI.strip() or PUNTI_AVVIO_MANUALI_JSON.strip():\n    if UNITA_AVVII_MANUALI.strip() not in UNITA_COSTIERE:\n        raise ValueError("Seleziona un ID di unità esistente per gli avvii manuali.")\n    PUNTI_MARE_MANUALI[UNITA_AVVII_MANUALI.strip()] = json.loads(PUNTI_AVVIO_MANUALI_JSON)\n    if not PUNTI_MARE_MANUALI[UNITA_AVVII_MANUALI.strip()]:raise ValueError("Inserisci almeno un punto manuale.")\nMAP_PROFILES = preparati\nif PROFILE_SOURCE_KIND=="GNSS (LineString XYZ)":\n    from forecast_service.gnss_setup import gnss_map_profiles\n    auto_ids=set()\n    for unit in POLIGONI_SETTORI:\n        if unit in PUNTI_MARE_MANUALI:continue\n        auto_ids.update(SETTORI_SPIAGGIA[unit]["transect_ids"] if unit!="whole" else scelti.transect_id)\n    MAP_PROFILES={}\n    if auto_ids:\n        MAP_PROFILES,map_report,map_metadata=gnss_map_profiles(DEM_SOURCE,GEO_TRANSECTS_SOURCE,\n            {key:preparati[key] for key in sorted(auto_ids)},profile_crs=CRS_PROFILI,\n            geojson_crs=GNSS_FIELDS["geojson_crs"],id_field=GNSS_FIELDS["id_field"])\n        map_report.to_csv(WORK/"campioni_dem_solo_avvii_mappa.csv",index=False)\n        print("Avvii cartografici: quote campionate dal DEM lungo le linee GNSS, separatamente dalle pendenze. Controlla i punti sulla mappa.")\nto_wgs = Transformer.from_crs(CRS_PROFILI, 4326, always_xy=True)\nCARTOGRAFIE = []\nfor unit, polygon in POLIGONI_SETTORI.items():\n    ids = SETTORI_SPIAGGIA[unit]["transect_ids"] if unit != "whole" else list(scelti.transect_id)\n    seeds = PUNTI_MARE_MANUALI.get(unit)\n    seed_profiles = None\n    if seeds is None:\n        seed_profiles = {}\n        for key in ids:\n            # Already oriented sea → land; select only the initial coastal prefix.\n            profile = MAP_PROFILES[key]\n            prefix = profile.loc[profile["x_mare"] <= MAX_AVANZAMENTO_AVVIO_M+1e-8]\n            samples = []\n            for x, y, distance, source_z in prefix[[COL_X, COL_Y, "x_mare", COL_Z]].itertuples(index=False, name=None):\n                lon, lat = to_wgs.transform(float(x), float(y))\n                map_z = float(source_z)+CORREZIONE_DEM_MAPPA_M-(CORREZIONE_QUOTE_DEM_M if PROFILE_SOURCE_KIND=="DEM + linee" else 0.)\n                samples.append([lon, lat, float(distance), map_z])\n            seed_profiles[str(key)] = samples\n    CARTOGRAFIE.append(dict(unit_id=unit, dem_path=str(DEM_SOURCE), orthophoto_path=str(ORTHO_SOURCE) if ORTHO_SOURCE else None,\n        display_polygon=polygon, seed_points=seeds, seed_profiles=seed_profiles,\n        seed_max_advance_m=MAX_AVANZAMENTO_AVVIO_M, seed_max_rise_m=MAX_RIALZO_AVVIO_M, survey_credit="DEMO sintetico" if DEMO else CREDITI_RILIEVI,\n        survey_date="Dati sintetici" if DEMO else DATA_RILIEVI, license="Solo dimostrazione" if DEMO else LICENZA_RILIEVI,\n        vertical_reference="Zero sintetico comune" if DEMO else RIFERIMENTO_VERTICALE_MAPPA,\n        dem_offset_m=CORREZIONE_DEM_MAPPA_M,\n        vertical_alignment_confirmed=True if DEMO else RACCORDO_VERTICALE_CONFERMATO,\n        clip_to_polygon=True, clip_buffer_m=MARGINE_CLIPPING_M,\n        orthophoto_resolution_m=RISOLUZIONE_ORTOFOTO_M))\nMAPPING_CONFIGS = {}; CARTOGRAPHY_ASSETS = {}\nfor spec in CARTOGRAFIE:\n    unit = spec["unit_id"]\n    try:\n        metadata, assets = prepare_mapping(output=WORK/"cartography"/unit, slug=ID_SITO, **spec)\n    except SeedSelectionError as error:\n        avvii = pd.DataFrame(error.report)\n        avvii.to_csv(WORK/f"avvii_mare_{unit}.csv", index=False)\n        display(avvii[["transect_id", "status", "advance_m", "grid_elevation_m"]])\n        raise\n    avvii = pd.DataFrame(metadata["seed_selection"])\n    avvii.to_csv(WORK/f"avvii_mare_{unit}.csv", index=False)\n    adjusted=avvii[avvii.advance_m>1e-8]\n    display(pd.DataFrame({"Controllo":["Transetti verificati","Avvii avanzati sul transetto","Avanzamento massimo (m)"],\n        "Valore":[len(avvii),len(adjusted),round(float(avvii.advance_m.max()),3)]}).set_index("Controllo"))\n    print(UNITA_COSTIERE[unit], "· elenco completo degli avvii:")\n    display(FileLink(str(WORK/f"avvii_mare_{unit}.csv")))\n    MAPPING_CONFIGS[unit] = metadata; CARTOGRAPHY_ASSETS.update(assets)\n    from forecast_service.inundation import load_grid\n    grid, seeds, mask, bounds = load_grid(assets[f"cartography/{unit}/grid.npz"])\n    import base64, html\n    from forecast_service.terrain_background import terrain_background\n    controllo=folium.Map(location=[(bounds[0][0]+bounds[1][0])/2,(bounds[0][1]+bounds[1][1])/2],tiles="OpenStreetMap")\n    ortho_preparata=assets.get(f"cartography/{unit}/orthophoto.png")\n    if ortho_preparata:\n        folium.raster_layers.ImageOverlay(str(ortho_preparata),bounds=bounds,name="Ortofoto del rilievo",opacity=1).add_to(controllo)\n    else:\n        background,scale=terrain_background(grid,mask)\n        folium.raster_layers.ImageOverlay("data:image/png;base64,"+base64.b64encode(background).decode(),bounds=bounds,name="DEM · quote del terreno",opacity=1).add_to(controllo)\n        colors=",".join(scale["colors"])\n        legend=f\'<div style="position:fixed;bottom:25px;left:15px;z-index:9999;background:white;padding:8px">Quota DEM: {scale["min_m"]:.2f} m <span style="display:inline-block;width:100px;height:12px;background:linear-gradient(to right,{colors})"></span> {scale["max_m"]:.2f} m</div>\'\n        controllo.get_root().html.add_child(folium.Element(legend))\n    avvii_layer=folium.FeatureGroup(name="Punti di avvio verso mare")\n    for entry in metadata["seed_selection"]:\n        lon,lat=entry.get("grid_cell_center",entry["selected_point"])\n        folium.CircleMarker([lat,lon],radius=3,color="#bd2a22",fill=True,fill_opacity=1,\n            tooltip=html.escape(str(entry["transect_id"]))+f" · avanzamento {entry[\'advance_m\']:.2f} m").add_to(avvii_layer)\n    avvii_layer.add_to(controllo)\n    folium.LayerControl(collapsed=False).add_to(controllo)\n    controllo.fit_bounds(bounds)\n    print("Controllo cartografico ·",UNITA_COSTIERE[unit],"· non è una previsione")\n    display(controllo)\nMAP_ANALYSIS_SIGNATURE = ANALYSIS_SIGNATURE\nCARTOGRAPHY_SIGNATURE = json.dumps(CARTOGRAFIE, sort_keys=True)\nprint("Ritagli pronti:", list(MAPPING_CONFIGS), "· sfondo:", "ortofoto" if ORTHO_SOURCE else "DEM a colori + OpenStreetMap")\n',tags=('survey-cartography',))
md('### 7.1 Prova del limite sul DSM — sole linee\n\nQuesto passaggio facoltativo lavora **sulla rappresentazione del limite**, senza creare un DTM, riempire buchi o modificare il DSM. Le pendenze e le quote delle strutture restano quelle dei passaggi precedenti.\n\n1. Scegli una **quota di prova**, nello stesso riferimento del DEM cartografico già corretto. È una prova geometrica, non una previsione.\n2. Il calcolo originale trova le celle sotto quota connesse ai punti a mare.\n3. Si estrae soltanto il fronte esterno fra celle osservate raggiunte e terreno esterno non raggiunto. I contorni degli isolotti interni, come quelli degli ombrelloni, vengono omessi; i bordi NoData e il limite del ritaglio non diventano falsi fronti di risalita.\n4. Si regolarizza la linea con una tolleranza in metri. **0 mantiene la linea originale**; partire da valori piccoli confrontandoli con risoluzione e precisione del rilievo.\n\nLa mappa mostra linee sull’ortofoto, senza riempimenti. Puoi accendere il limite originale e confrontarlo con quello regolarizzato. La regolarizzazione può spostare il tratto disegnato entro la tolleranza: **non corregge la propagazione bloccata da false barriere del DSM** e non viene usata per soglie o misure di superficie.\n\nGli eventuali GeoJSON, PNG e metadati esportati sono **diagnostica di prova**: non attivano la regolarizzazione nelle previsioni pubblicate. I GeoTIFF e il calcolo di connessione restano invariati.')
code('#@title Quota di prova e regolarizzazione della linea\nESEGUI_PROVA_LINEA = False #@param {type:"boolean"}\nQUOTA_TWL_PROVA_M = 1.4 #@param {type:"number"}\nTOLLERANZA_LINEA_M = 1.0 #@param {type:"number"}\nUNITA_LINEA_DA_VEDERE = "" #@param {type:"string"}\nprint("Unità disponibili:", list(MAPPING_CONFIGS))\nprint("Lascia vuota l’unità per vedere la prima; inserisci un ID per cambiare settore costiero.")\nif not ESEGUI_PROVA_LINEA:\n    print("Prova disattivata: puoi proseguire il setup senza modifiche.")',form=True,tags=('contour-preview-settings',))
code('#@title Confronta il limite originale e la linea regolarizzata\nfrom forecast_service.contour_preview import preview_from_grid\nLINE_PREVIEW_META = None\nLINE_PREVIEW_ATTACHMENTS = {}\nif ESEGUI_PROVA_LINEA:\n    if not MAPPING_CONFIGS:\n        raise ValueError("Prima prepara i ritagli cartografici.")\n    unit = UNITA_LINEA_DA_VEDERE.strip() or next(iter(MAPPING_CONFIGS))\n    if unit not in MAPPING_CONFIGS:\n        raise ValueError("Unità sconosciuta: scegli un ID dalla lista della cella precedente.")\n    grid_path = CARTOGRAPHY_ASSETS[f"cartography/{unit}/grid.npz"]\n    original_line, display_line, line_meta = preview_from_grid(\n        grid_path, level_m=QUOTA_TWL_PROVA_M, tolerance_m=TOLLERANZA_LINEA_M,\n        display_polygon=POLIGONI_SETTORI[unit])\n    line_meta["unit_id"] = unit\n    line_meta["data_mode"] = "demo" if DEMO else "study"\n    line_meta["vertical_reference"] = MAPPING_CONFIGS[unit]["vertical_reference"]\n    line_meta["dem_offset_m"] = MAPPING_CONFIGS[unit]["dem_offset_m"]\n    preview_dir = WORK / "prova_linee"\n    preview_dir.mkdir(exist_ok=True)\n    diagnostic_paths = {}\n    for name, value in [(f"limite_originale_{unit}.geojson", original_line),\n                        (f"limite_regolarizzato_{unit}.geojson", display_line),\n                        (f"prova_linea_{unit}.json", line_meta)]:\n        target = preview_dir / name\n        target.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+"\\n")\n        diagnostic_paths[name] = target\n    bounds = line_meta["bounds_wgs84"]\n    preview_map = folium.Map(location=[(bounds[0][0]+bounds[1][0])/2,\n                                       (bounds[0][1]+bounds[1][1])/2], tiles="OpenStreetMap")\n    ortho_path = CARTOGRAPHY_ASSETS.get(f"cartography/{unit}/orthophoto.png")\n    if ortho_path:\n        folium.raster_layers.ImageOverlay(image=str(ortho_path), bounds=bounds,\n            name="Ortofoto del rilievo", opacity=1).add_to(preview_map)\n    if not ortho_path:\n        import base64\n        from forecast_service.terrain_background import terrain_background\n        dem_grid,_,dem_mask,_=load_grid(grid_path)\n        background,scale=terrain_background(dem_grid,dem_mask)\n        folium.raster_layers.ImageOverlay("data:image/png;base64,"+base64.b64encode(background).decode(),\n            bounds=bounds,name="DEM · quote del terreno",opacity=1).add_to(preview_map)\n        colors=",".join(scale["colors"])\n        legend=f\'<div style="position:fixed;bottom:25px;left:15px;z-index:9999;background:white;padding:8px">Quota DEM: {scale["min_m"]:.2f} m <span style="display:inline-block;width:100px;height:12px;background:linear-gradient(to right,{colors})"></span> {scale["max_m"]:.2f} m</div>\'\n        preview_map.get_root().html.add_child(folium.Element(legend))\n    if original_line["features"]:\n        folium.GeoJson(original_line, name="Limite originale (stesso calcolo)", show=False,\n            style_function=lambda f: {"color":"#555555", "weight":2, "dashArray":"4,4"}).add_to(preview_map)\n    if display_line["features"]:\n        folium.GeoJson(display_line, name="Linea regolarizzata — solo visualizzazione",\n            style_function=lambda f: {"color":"#176ca4", "weight":3}).add_to(preview_map)\n    folium.LayerControl(collapsed=False).add_to(preview_map)\n    preview_map.fit_bounds(bounds)\n    html_path = preview_dir / f"confronto_linee_{unit}.html"\n    preview_map.save(str(html_path))\n    display(preview_map)\n    # Static comparison in the prepared map CRS; PNG is diagnostic only.\n    from forecast_service.geospatial_setup import reproject_geometry\n    from shapely.geometry import shape\n    left, bottom, right, top = line_meta["bounds_3857"]\n    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")\n    def disegna_linee(ax, geometry, color):\n        if geometry.is_empty:\n            return\n        if geometry.geom_type == "LineString":\n            ax.plot(*geometry.xy, color=color, linewidth=1.4)\n        elif hasattr(geometry, "geoms"):\n            for part in geometry.geoms:\n                disegna_linee(ax, part, color)\n    for ax, collection, title, color in zip(axes, [original_line, display_line],\n            ["Limite originale", "Linea regolarizzata (solo disegno)"], ["#555555", "#176ca4"]):\n        if ortho_path:\n            ax.imshow(plt.imread(ortho_path), extent=[left,right,bottom,top])\n        else:\n            terrain=ax.imshow(np.where(dem_mask,dem_grid,np.nan),extent=[left,right,bottom,top],cmap=LinearSegmentedColormap.from_list("quote_dem",scale["colors"]),vmin=scale["min_m"],vmax=scale["max_m"])\n            fig.colorbar(terrain,ax=ax,label="Quota DEM (m)",shrink=.7)\n        for feature in collection["features"]:\n            disegna_linee(ax, reproject_geometry(shape(feature["geometry"]), 4326, 3857), color)\n        ax.set(xlim=(left,right), ylim=(bottom,top), title=title)\n        ax.set_aspect("equal"); ax.set_axis_off()\n    fig.suptitle(f"{UNITA_COSTIERE[unit]} · quota di prova {QUOTA_TWL_PROVA_M:g} m · tolleranza {TOLLERANZA_LINEA_M:g} m")\n    png_path = preview_dir / f"confronto_linee_{unit}.png"\n    fig.savefig(png_path, dpi=140)\n    display(fig); plt.close(fig)\n    diagnostic_paths[png_path.name] = png_path\n    LINE_PREVIEW_META = line_meta\n    LINE_PREVIEW_ATTACHMENTS = diagnostic_paths\n    display(pd.DataFrame([{"Quota di prova (m)":line_meta["level_m"],\n        "Tolleranza (m)":line_meta["tolerance_m"], "Vertici originali":line_meta["original_vertices"],\n        "Vertici regolarizzati":line_meta["simplified_vertices"],\n        "Isolotti interni non disegnati":line_meta["internal_components_not_drawn"],\n        "Celle riempite":line_meta["filled_cells"]}]))\n    if line_meta["empty"]:\n        print("Nessun fronte osservabile per questa quota: controlla punti a mare, quota, copertura e NoData. Il bordo del DEM non è un limite di risalita.")\n    if line_meta["seeds_below_level"] == 0:\n        print("La quota è sotto tutti i punti di avvio: la prova non raggiunge celle.")\n    print("DSM, griglia originale, pendenze, soglie e maschera di connessione non modificati.")\n    print("HTML interattivo salvato:", html_path)\n    display(FileLink(str(html_path)))',tags=('contour-preview',))

md('''## 8. Serie storica ERA5 — unica per tutta l’area
Per dati reali servono un account Climate Data Store e l’accettazione personale delle condizioni di [ERA5 time-series](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries?tab=download). La ricerca automatica della cella marina usa anche [ERA5 grigliato](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download).

Puoi salvare il token nei **Secrets di Colab**, con nome `CDS_KEY` e accesso a questo notebook, oppure inserirlo nel campo protetto quando richiesto. Non scriverlo nei campi del notebook. La cache contiene soltanto richieste e dati: sarà riutilizzata se la sessione riparte dalla stessa cartella.

Il servizio ERA5 restituisce **periodo medio**, non Tp: lo salviamo come `tm_s`; non lo usiamo come periodo di picco per il runup. Il confronto storico usa Hs. Il confronto con tutte le ore storiche è distinto dal fit Gumbel dei massimi annuali per settore descritto sotto.''')

md('''### Tempi di ritorno per direzione delle onde (non settori costieri)
La suddivisione statistica in settori di provenienza è distinta dall’esposizione fisica della spiaggia. Puoi scegliere l’ampiezza dei settori: nessuna direzione è privilegiata. I settori sono centrati su multipli dell’ampiezza scelta; per esempio, con 45°, quello centrato a 90° va da 67,5° incluso a 112,5° escluso. Le direzioni indicano **da dove arrivano** le onde.

Per ogni anno di calendario UTC completo si seleziona il massimo Hs **fra tutte le ore di ciascun settore**, non si suddivide il solo massimo annuale generale. Si usano soltanto anni con copertura oraria completa e direzione valida (la direzione può mancare nelle ore di calma con Hs=0). Se un settore non ha onde positive in qualche anno completo, il fit non viene mostrato: rimuovere quegli anni condizionerebbe la frequenza.

Il fit è una **Gumbel sui massimi annuali** (massima verosimiglianza), con banda bootstrap al 95% ricampionando gli anni. Questa prima versione richiede 30 anni completi; una serie lunga non dimostra da sola che Gumbel sia adeguata. Si assumono stazionarietà e indipendenza dei massimi annuali. Sul sito il picco Hs dei quattro giorni viene confrontato con il settore della sua direzione in quell’ora; si possono esaminare anche i picchi negli altri settori presenti.

Il tempo di ritorno riguarda Hs al largo per quel settore, non runup o allagamenti. La differenza fra ERA5 e Copernicus non è corretta e non rientra nella banda del fit. Non usare queste elaborazioni sperimentali per previsioni o scelte gestionali.''')
code('''#@title Impostazioni dei massimi annuali per settore
CALCOLA_ESTREMI_SETTORIALI = True #@param {type:"boolean"}
AMPIEZZA_SETTORI_ESTREMI = 45 #@param [30,45,60,90,120,180,360]
COL_DIREZIONE_ERA5 = "direction_deg" #@param {type:"string"}
MIN_ANNI_ESTREMI = 30
REPLICHE_BOOTSTRAP = 400
print("Settori statistici:",AMPIEZZA_SETTORI_ESTREMI,"gradi; minimo",MIN_ANNI_ESTREMI,"anni completi.")''',form=True,tags=('directional-extremes-settings',))
code('''#@title Sorgente e periodo storico
MODALITA_ERA5 = "Scarica ERA5" #@param ["Scarica ERA5", "Importa CSV", "Salta per ora"]
ERA5_INIZIO = "1991-01-01" #@param {type:"date"}
ERA5_FINE = "2020-12-31" #@param {type:"date"}
CONSENSO_DOWNLOAD_ERA5 = False #@param {type:"boolean"}
CELLA_ERA5_NOTA = False #@param {type:"boolean"}
LAT_CELLA_ERA5 = 44.0 #@param {type:"number"}
LON_CELLA_ERA5 = 8.5 #@param {type:"number"}
FILE_CSV_ERA5 = "" #@param {type:"string"}
COL_TEMPO_ERA5 = "time" #@param {type:"string"}
COL_HS_ERA5 = "hs" #@param {type:"string"}
SCARTA_HS_MANCANTI = False #@param {type:"boolean"}
CLIMATE=None
CLIMATE_DATA_MODE="demo" if DEMO else "study"
climate_metadata={}
CACHE=BASE/"_cache_era5"
CACHE.mkdir(parents=True,exist_ok=True)
if DEMO:
    # Synthetic reference, clearly labelled; never presented as an ERA5 download.
    time=pd.date_range("2019-01-01", "2020-12-31 23:00",freq="h",tz="UTC")
    index=np.arange(len(time))
    hs=.25+1.1*(.5+.5*np.sin(index/179))**3+.3*(.5+.5*np.sin(index/37))
    era5_frame=pd.DataFrame({"time":time,"hs_m":hs,"direction_deg":(index*13)%360})
    history=WORK/"clima_dimostrativo.csv"; era5_frame.to_csv(history,index=False)
    CLIMATE=build_climate(history,"Esempio sintetico; non ERA5")
    climate_metadata={"mode":"demo","description":"Distribuzione sintetica per verificare il notebook."}
elif MODALITA_ERA5=="Scarica ERA5":
    if not CONSENSO_DOWNLOAD_ERA5:
        raise ValueError("Accetta le condizioni sul CDS e imposta CONSENSO_DOWNLOAD_ERA5=True per avviare la richiesta.")
    import os
    if not os.environ.get("CDS_KEY"):
        token=None
        try:
            from google.colab import userdata
            token=userdata.get("CDS_KEY")
        except Exception:
            pass
        if not token:
            from getpass import getpass
            token=getpass("Token CDS (input nascosto): ")
        if not token: raise ValueError("Token CDS non disponibile.")
        os.environ["CDS_KEY"]=token
        del token
    known_cell=(LON_CELLA_ERA5,LAT_CELLA_ERA5) if CELLA_ERA5_NOTA else None
    era5_frame,climate_metadata=download_series(SITE_INPUT,dt.date.fromisoformat(ERA5_INIZIO),dt.date.fromisoformat(ERA5_FINE),CACHE,cell=known_cell)
    history=WORK/"ERA5_hourly.csv"; era5_frame.to_csv(history,index=False)
    if climate_metadata["missing_hs_records"] and not SCARTA_HS_MANCANTI:
        raise ValueError("ERA5 ha ore mancanti: CSV conservato. Esamina i dati; puoi autorizzare lo scarto con SCARTA_HS_MANCANTI.")
    if SCARTA_HS_MANCANTI:
        climate_metadata["dropped_missing_rows"]=int(era5_frame.hs_m.isna().sum())
        era5_frame=era5_frame.dropna(subset=["hs_m"])
        history=WORK/"ERA5_hs_valide.csv"; era5_frame.to_csv(history,index=False)
    CLIMATE=build_climate(history,"ERA5")
elif MODALITA_ERA5=="Importa CSV":
    if not FILE_CSV_ERA5:
        from google.colab import files
        uploaded=files.upload()
        if len(uploaded)!=1: raise ValueError("Carica un solo CSV storico.")
        name,content=next(iter(uploaded.items()))
        history=WORK/Path(name).name; history.write_bytes(content)
    else:
        history=Path(FILE_CSV_ERA5)
    era5_frame=pd.read_csv(history)
    if SCARTA_HS_MANCANTI:
        climate_metadata["dropped_missing_rows"]=int(era5_frame[COL_HS_ERA5].isna().sum())
        era5_frame=era5_frame.dropna(subset=[COL_HS_ERA5])
        history=WORK/"ERA5_import_hs_valide.csv"; era5_frame.to_csv(history,index=False)
    CLIMATE=build_climate(history,"ERA5 (CSV dell’utente)",time_column=COL_TEMPO_ERA5,hs_column=COL_HS_ERA5)
else:
    print("Climatologia saltata: la località potrà essere esportata senza riferimento storico.")
if CLIMATE is not None:
    if CALCOLA_ESTREMI_SETTORIALI:
        imported=not DEMO and MODALITA_ERA5=="Importa CSV"
        CLIMATE["directional_extremes"]=build_directional_extremes(history,
            time_column=COL_TEMPO_ERA5 if imported else "time",
            hs_column=COL_HS_ERA5 if imported else "hs_m",
            direction_column=COL_DIREZIONE_ERA5 if imported else "direction_deg",
            sector_width_deg=int(AMPIEZZA_SETTORI_ESTREMI),min_years=MIN_ANNI_ESTREMI,
            bootstrap_replicates=REPLICHE_BOOTSTRAP)
        ext=CLIMATE["directional_extremes"]
        if ext["status"]=="available":
            display(pd.DataFrame([{"settore":f'{s["start_deg"]:g}° → {s["end_deg"]:g}°',
                "anni":s["fit"]["n_years"],"fit":s["fit"]["status"],"nota":s["fit"].get("reason","")}
                for s in ext["sectors"]]))
        else: print(ext["reason"])
    CLIMATE["download"]=climate_metadata
    if not DEMO: CLIMATE["doi"]="10.24381/1cf1ad76"
    (WORK/"climatology.json").write_text(json.dumps(CLIMATE,ensure_ascii=False,allow_nan=False,separators=(",",":")))
    display(pd.DataFrame([{k:CLIMATE[k] for k in ["source","start","end","n_records","p95_m","p99_m","max_hs_m","coverage_fraction"]}]))''',form=True)
code('''#@title Verifica la distribuzione e i massimi annuali
if CLIMATE is not None:
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    axes[0].hist(CLIMATE["hs_sorted_m"],bins=50,color="#527d78",density=True)
    for key,label,color in [("p95_m","P95","#b39245"),("p99_m","P99","#b65f44")]:
        axes[0].axvline(CLIMATE[key],ls="--",color=color,label=f"{label}: {CLIMATE[key]:.2f} m")
    axes[0].set(xlabel="Hs [m]",ylabel="Densità",title=CLIMATE["source"])
    axes[0].legend()
    annual=pd.DataFrame.from_dict(CLIMATE["annual_maxima"],orient="index")
    axes[1].bar(annual.index,annual.hs_m,color="#527d78")
    axes[1].tick_params(axis="x",labelrotation=60)
    axes[1].set(xlabel="Anno",ylabel="Hs massima osservata [m]",title="Massimi annuali osservati, non valori di ritorno")
    fig.tight_layout(); fig.savefig(WORK/"climatologia.png",dpi=150); plt.show()
    annual.to_csv(WORK/"massimi_annuali.csv",index_label="year")
    display(annual)
    if "cell_lat" in climate_metadata:
        m=folium.Map(location=[LAT_ONDE,LON_ONDE],zoom_start=8)
        folium.Marker([LAT_SITO,LON_SITO],tooltip="Sito").add_to(m)
        folium.CircleMarker([LAT_ONDE,LON_ONDE],radius=6,color="green",tooltip="Punto onde richiesto").add_to(m)
        folium.CircleMarker([climate_metadata["cell_lat"],climate_metadata["cell_lon"]],radius=7,color="orange",tooltip="Cella marina ERA5 usata").add_to(m)
        display(m)
else:
    print("Nessuna climatologia selezionata.")''',form=True)

code('''#@title Verifica le curve Gumbel dei settori
ext=CLIMATE.get("directional_extremes") if CLIMATE else None
if ext and ext["status"]=="available":
    valid=[s for s in ext["sectors"] if s["fit"]["status"]=="available"]
    if valid:
        fig,axes=plt.subplots((len(valid)+1)//2,2,figsize=(12,4*((len(valid)+1)//2)),squeeze=False)
        for ax,sector in zip(axes.flat,valid):
            fit=sector["fit"]; periods=fit["return_period_years"]
            ax.fill_between(periods,fit["ci95_low_m"],fit["ci95_high_m"],alpha=.2,color="#527d78",label="Bootstrap 95%")
            ax.plot(periods,fit["return_level_m"],color="#194e4c",label="Gumbel")
            ax.scatter([r["return_period_years"] for r in fit["empirical"]],[r["hs_m"] for r in fit["empirical"]],s=12,label="Massimi annuali")
            ax.set(xscale="log",xlabel="Tempo di ritorno [anni]",ylabel="Hs al largo [m]",title=f'{sector["start_deg"]:g}° → {sector["end_deg"]:g}° · {fit["n_years"]} anni')
            ax.set_ylim(bottom=0); ax.legend(fontsize=8)
        for ax in list(axes.flat)[len(valid):]: ax.set_visible(False)
        fig.tight_layout(); fig.savefig(WORK/"estremi_settoriali.png",dpi=150); plt.show()
    else: print("Nessun settore soddisfa i requisiti per il fit. Esamina le note nella tabella.")
else: print("Estremi settoriali non configurati.")''',form=True,tags=('directional-extremes-plot',))

md('''### Zero del livello marino: riferimento storico fisso Copernicus
Questa sezione è separata da ERA5: usa la **SSH del modello fisico Copernicus**, che comprende la marea e le variazioni atmosferiche e oceanografiche. Si calcola una volta la media di un anno UTC completo nella stessa cella usata per le previsioni, e la si conserva per gli aggiornamenti futuri. Non si sottrae la media dei giorni di previsione.

Per Borghetto è incluso il riferimento già verificato del **2025**: 8.760 ore, media SSH circa −0,4032 m. Puoi usarlo senza scaricare nuovamente dati o rifare ERA5. Il controllo rifiuta di applicarlo se cambi il punto del livello marino. Per un altro sito scegli **Calcola da Copernicus** e un anno completo disponibile nell’archivio: il download richiede l’account Copernicus Marine, distinto da quello CDS/ERA5. Le credenziali si leggono dai Secrets Colab o da input protetto e non sono esportate.

Lo zero così ottenuto è la **media del modello nell’anno dichiarato**, non una calibrazione del livello medio mare misurato sulla spiaggia. Il raccordo con le quote delle strutture rimane provvisorio. Eventuali correzioni locali devono restare esplicite nel campo `OFFSET_LIVELLO_M`.''')
code('''#@title Riferimento storico del livello marino
MODALITA_RIFERIMENTO_SSH = "Usa riferimento incluso" #@param ["Usa riferimento incluso", "Calcola da Copernicus", "Importa JSON"]
ANNO_RIFERIMENTO_SSH = 2025 #@param {type:"integer"}
CONSENSO_DOWNLOAD_SSH = False #@param {type:"boolean"}
FILE_RIFERIMENTO_SSH = "" #@param {type:"string"}
SEA_LEVEL_REFERENCE=None
reference_location=dict(SITE_INPUT)
if not LIVELLO_STESSO_PUNTO:
    reference_location["sealevel_point"]=dict(latitude=LAT_LIVELLO,longitude=LON_LIVELLO)
if DEMO:
    print("Modalità demo: il livello marino resta sintetico; nessun riferimento reale viene usato.")
elif MODALITA_RIFERIMENTO_SSH=="Usa riferimento incluso":
    reference_file=RUNTIME/"config"/"study_sites"/ID_SITO/f"sea_level_reference_{ANNO_RIFERIMENTO_SSH}.json"
    if not reference_file.exists():
        raise ValueError("Nessun riferimento incluso per questo sito/anno: scegli Calcola da Copernicus o Importa JSON.")
    SEA_LEVEL_REFERENCE=json.loads(reference_file.read_text())
elif MODALITA_RIFERIMENTO_SSH=="Importa JSON":
    if FILE_RIFERIMENTO_SSH:
        SEA_LEVEL_REFERENCE=json.loads(Path(FILE_RIFERIMENTO_SSH).read_text())
    else:
        from google.colab import files
        uploaded=files.upload()
        if len(uploaded)!=1: raise ValueError("Carica un solo riferimento JSON.")
        SEA_LEVEL_REFERENCE=json.loads(next(iter(uploaded.values())))
else:
    if not CONSENSO_DOWNLOAD_SSH:
        raise ValueError("Per scaricare la SSH storica imposta CONSENSO_DOWNLOAD_SSH=True.")
    from getpass import getpass
    def account_secret(name,prompt):
        import os
        value=os.environ.get(name)
        if not value:
            try:
                from google.colab import userdata
                value=userdata.get(name)
            except Exception:
                pass
        return value or getpass(prompt)
    username=account_secret("COPERNICUSMARINE_USERNAME","Username Copernicus Marine: ")
    password=account_secret("COPERNICUSMARINE_PASSWORD","Password Copernicus Marine: ")
    try:
        SEA_LEVEL_REFERENCE=download_reference(reference_location,int(ANNO_RIFERIMENTO_SSH),username,password,cache=BASE/"_cache_ssh")
    finally:
        del username,password
if SEA_LEVEL_REFERENCE is not None:
    validate_reference(SEA_LEVEL_REFERENCE,location=reference_location)
    if SEA_LEVEL_REFERENCE["year"]!=ANNO_RIFERIMENTO_SSH:
        raise ValueError("L’anno del riferimento JSON non corrisponde a quello selezionato.")
    (WORK/f"sea_level_reference_{ANNO_RIFERIMENTO_SSH}.json").write_text(json.dumps(SEA_LEVEL_REFERENCE,ensure_ascii=False,allow_nan=False,indent=2))
    display(pd.DataFrame([{"riferimento":f'Media SSH Copernicus {SEA_LEVEL_REFERENCE["year"]}',"media SSH (m)":SEA_LEVEL_REFERENCE["mean_ssh_m"],"ore":SEA_LEVEL_REFERENCE["n_records"],"cella":SEA_LEVEL_REFERENCE["selected_point"],"versione dataset":SEA_LEVEL_REFERENCE["dataset_version"]}]))
    print("Questo valore resterà fisso nei futuri bollettini. Il raccordo con le quote locali è ancora da verificare.")''',form=True,tags=('historical-sealevel-reference',))
md('''## 9. Rivedi ed esporta l’area
Il pacchetto contiene configurazione, soglie, pendenze e relativa diagnostica, profili normalizzati e climatologia quando disponibile. **Conserva la cache o il CSV storico in Drive**: il pacchetto riporta il riferimento statistico, non tutti i NetCDF delle richieste.

Un pacchetto prodotto in modalità demo è marcato come tale e l’importatore lo rifiuta per impostazione predefinita. Nessun token entra nel pacchetto. Nessun file del portale viene modificato da Colab.''')
code('#@title Riepilogo prima dell’esportazione\nfrom forecast_service.time_utils import iso\nimport hashlib\nline_preview_metadata = None\nif globals().get("ESEGUI_PROVA_LINEA", False):\n    line_preview_metadata = globals().get("LINE_PREVIEW_META")\n    preview_unit = UNITA_LINEA_DA_VEDERE.strip() or next(iter(MAPPING_CONFIGS))\n    if not line_preview_metadata or preview_unit not in MAPPING_CONFIGS:\n        raise ValueError("Riesegui il confronto delle linee prima di esportare la diagnostica.")\n    preview_grid = CARTOGRAPHY_ASSETS[f"cartography/{preview_unit}/grid.npz"]\n    if (line_preview_metadata["unit_id"] != preview_unit or\n        line_preview_metadata["level_m"] != QUOTA_TWL_PROVA_M or\n        line_preview_metadata["tolerance_m"] != TOLLERANZA_LINEA_M or\n        line_preview_metadata["grid_sha256"] != hashlib.sha256(Path(preview_grid).read_bytes()).hexdigest()):\n        raise ValueError("Quota, tolleranza, settore o griglia cambiati: riesegui il confronto delle linee.")\nif NOMI_SETTORI_EDITOR.read()!=UNITA_COSTIERE or SLOPE_OPTIONS_SIGNATURE!=(MODALITA_PENDENZE,NUM_CAMPIONI_MC,SEME_MONTE_CARLO,NUM_PENDENZE):\n    raise ValueError("Nomi o opzioni delle pendenze cambiati: riesegui Conferma nomi e campiona, poi le celle successive.")\nif ASSEGNAZIONI_EDITOR and ASSEGNAZIONI_EDITOR.read()!=ASSEGNAZIONI_MANUALI:\n    raise ValueError("Assegnazioni cambiate: riesegui Assegna i transetti e le celle successive.")\nif PROFILE_SOURCE_KIND!=("DEM + linee" if DEMO else SORGENTE_PENDENZE):\n    raise ValueError("Sorgente delle pendenze cambiata: riesegui lettura e analisi.")\nif GNSS_FIELD_EDITOR:\n    if GNSS_FIELD_EDITOR.read()!=GNSS_FIELDS or hashlib.sha256(GEO_TRANSECTS_SOURCE.read_bytes()).hexdigest()!=GEO_PREPROCESSING["transects_sha256"]:\n        raise ValueError("File o campi GNSS cambiati: riesegui lettura e analisi prima di esportare.")\ncurrent_signature=(PROFILE_SOURCE_KIND,FIT_EDITOR.read(),PROFILE_CONFIG_SIGNATURE,COL_ID,COL_DIST,COL_Z,COL_X,COL_Y,\n    hashlib.sha256(pd.util.hash_pandas_object(profili,index=True).values.tobytes()).hexdigest())\nif PROFILE_DATA_MODE!=("demo" if DEMO else "study") or (CLIMATE is not None and CLIMATE_DATA_MODE!=("demo" if DEMO else "study")):\n    raise ValueError("Modalità cambiata: riesegui caricamento profili, pendenze e climatologia prima di esportare.")\nif current_signature!=ANALYSIS_SIGNATURE or SELECTION_ANALYSIS_SIGNATURE!=ANALYSIS_SIGNATURE or PLOT_ANALYSIS_SIGNATURE!=ANALYSIS_SIGNATURE:\n    raise ValueError("Parametri o profili cambiati: riesegui calcolo, grafico e selezione delle pendenze.")\nif STRUCTURE_POINT_META:\n    if hashlib.sha256(STRUCTURES_SOURCE.read_bytes()).hexdigest()!=STRUCTURE_POINT_META["points_sha256"] or COL_STRUTTURA!=STRUCTURE_POINT_META["label_field"]:\n        raise ValueError("Punti delle strutture cambiati: riesegui campionamento e modulo delle strutture.")\n    if not np.isclose(CORREZIONE_QUOTE_DEM_M,STRUCTURE_POINT_META["elevation_correction_m"],rtol=0,atol=1e-9):\n        raise ValueError("Correzione delle quote cambiata: riesegui i campionamenti.")\n    if hashlib.sha256(json.dumps(POLIGONI_SETTORI,sort_keys=True).encode()).hexdigest()!=STRUCTURE_POINT_META["polygons_sha256"]:\n        raise ValueError("Poligoni cambiati: riesegui le quote delle strutture.")\nSTRUTTURE_PER_UNITA = STRUTTURE_EDITOR.read()\nif set(STRUTTURE_PER_UNITA) != set(UNITA_COSTIERE):\n    raise ValueError("Unità cambiate: ricrea il modulo delle strutture esposte.")\nthresholds = STRUTTURE_PER_UNITA.get("whole", next(iter(STRUTTURE_PER_UNITA.values())))\nfor key, values in STRUTTURE_PER_UNITA.items():\n    if key != "whole": SETTORI_SPIAGGIA[key]["thresholds"] = values\nnormalized=profili.rename(columns={COL_ID:"TR_ID",COL_DIST:"distance",COL_Z:"SAMPLE_1",COL_X:"X",COL_Y:"Y"})[["TR_ID","distance","SAMPLE_1","X","Y"]]\nnormalized.to_csv(WORK/"profili_normalizzati.csv",index=False)\nlocation=dict(SITE_INPUT,slopes=PENDENZE,slope_sampling=SLOPE_SAMPLING,roughness_m=float(RUGOSITA_M),parameters_status="provisional",\n    wave_exposure=parse_exposure(SETTORI_PROVENIENZA,NOTE_ESPOSIZIONE),\n    datum_offset_m=float(OFFSET_LIVELLO_M),vertical_reference_status="provisional",\n    climatology_file=f"config/climatology/{ID_SITO}.json" if CLIMATE is not None else None,\n    summer_season=dict(start_month_day=INIZIO_ESTATE or None,end_month_day=FINE_ESTATE or None,status="configured" if INIZIO_ESTATE else "to_be_defined"),\n    transects=scelti.to_dict(orient="records"),notes=NOTE_SITO)\nif SETTORI_SPIAGGIA:\n    location["sectors"] = copy.deepcopy(SETTORI_SPIAGGIA)\nresolve_sectors(location, thresholds)\nif SECTOR_ANALYSIS_SIGNATURE != ANALYSIS_SIGNATURE or (MAPPING_CONFIGS and MAP_ANALYSIS_SIGNATURE != ANALYSIS_SIGNATURE):\n    raise ValueError("Profili cambiati: riesegui assegnazione dei settori e preparazione delle mappe.")\nif CARTOGRAPHY_SIGNATURE != json.dumps(CARTOGRAFIE, sort_keys=True):\n    raise ValueError("Cartografia cambiata: riesegui la preparazione prima di esportare.")\nfor unit, metadata in MAPPING_CONFIGS.items():\n    if unit == "whole":\n        location["mapping"] = metadata\n    elif unit in location.get("sectors", {}):\n        location["sectors"][unit]["mapping"] = metadata\n    else:\n        raise ValueError("Settore rimosso: riesegui la preparazione della cartografia.")\nif not LIVELLO_STESSO_PUNTO:\n    location["sealevel_point"]=dict(latitude=LAT_LIVELLO,longitude=LON_LIVELLO)\nif SEA_LEVEL_REFERENCE is not None:\n    if SEA_LEVEL_REFERENCE["year"]!=ANNO_RIFERIMENTO_SSH:\n        raise ValueError("Anno del riferimento cambiato: riesegui la sezione del livello marino prima di esportare.")\n    location=apply_reference(location,SEA_LEVEL_REFERENCE)\npayload=dict(schema_version=1,slug=ID_SITO,data_mode="demo" if DEMO else "study",location=location,thresholds=thresholds,\n    provenance=dict(created_at=iso(dt.datetime.now(dt.timezone.utc)),slope_method=PROFILE_FIT_METHOD,\n        reference_notebook="Stockdon_runup_soluzione.ipynb, celle 24–25" if PROFILE_SOURCE_KIND=="DEM + linee" else "GNSS: intera battigia; distanza euclidea e regressione oppure pendenza fornita nel campo selezionato",profile_source=PROFILE_SOURCE,\n        profile_sha256=hashlib.sha256((WORK/"profili_normalizzati.csv").read_bytes()).hexdigest(),\n        profile_data_mode=PROFILE_DATA_MODE,climate_data_mode=CLIMATE_DATA_MODE if CLIMATE else None,\n        sea_level_reference_year=SEA_LEVEL_REFERENCE["year"] if SEA_LEVEL_REFERENCE else None,\n        geospatial_preprocessing=GEO_PREPROCESSING,structure_point_preprocessing=STRUCTURE_POINT_META,\n        cartographic_line_preview=line_preview_metadata,\n        structure_point_exclusions_confirmed=bool(ESCLUDI_PUNTI_STRUTTURE_NON_VALIDI) if STRUCTURE_POINT_META else None,profile_crs=crs.to_string(),vertical_reference=PROFILE_VERTICAL_REFERENCE,z_correction_m=PROFILE_Z_CORRECTION,\n        excluded_transects=sorted(excluded),slope_sampling=MODALITA_PENDENZE,slope_sampling_by_unit=SLOPE_SAMPLING_BY_UNIT,z_min_m=Z_MIN,z_max_m=Z_MAX))\ndisplay(pd.DataFrame([{"località":NOME_SITO,"modalità":payload["data_mode"],"transetti inclusi":len(scelti),"pendenze":PENDENZE,"ERA5 o riferimento":CLIMATE["source"] if CLIMATE else "Non configurato","esposizione":location["wave_exposure"]["sectors_deg"] if location["wave_exposure"] else "Da definire","stagione estiva":f"{INIZIO_ESTATE} / {FINE_ESTATE}" if INIZIO_ESTATE else "Da definire"}]))\nprint("Le soglie e il raccordo delle quote restano da validare, anche con profili misurati.")',form=True)
code('#@title Crea e scarica il pacchetto\nESPORTA_PACCHETTO = True #@param {type:"boolean"}\nif ESPORTA_PACCHETTO:\n    attachments={name:WORK/name for name in ["pendenze_transetti.csv","profili_normalizzati.csv","profilo_selezionato.png"]}\n    for name in ["climatologia.png","massimi_annuali.csv","estremi_settoriali.png"]:\n        if CLIMATE is not None and (WORK/name).exists(): attachments[name]=WORK/name\n    for name in ["estrazione_transetti.csv", "assegnazioni_settori.csv", "quote_strutture_punti.csv", "quote_strutture_riepilogo.csv", "pendenze_campionate.csv", "campionamento_pendenze.json", "campioni_dem_solo_avvii_mappa.csv"]:\n        if (WORK/name).exists(): attachments[name]=WORK/name\n    for unit in MAPPING_CONFIGS:\n        seed_report = WORK/f"avvii_mare_{unit}.csv"\n        if seed_report.exists(): attachments[seed_report.name] = seed_report\n    if line_preview_metadata:\n        attachments.update(LINE_PREVIEW_ATTACHMENTS)\n    if GEO_TRANSECTS_SOURCE: attachments["transetti.geojson"]=GEO_TRANSECTS_SOURCE\n    if AREAS_SOURCE: attachments["settori.geojson"]=AREAS_SOURCE\n    if STRUCTURES_SOURCE: attachments["strutture.geojson"]=STRUCTURES_SOURCE\n    output=WORK/f"{ID_SITO}_{\'DEMO\' if DEMO else \'studio\'}.zip"\n    write_site_package(output,payload,climatology=CLIMATE,attachments=attachments,cartography=CARTOGRAPHY_ASSETS)\n    print("Pacchetto creato:",output)\n    try:\n        from google.colab import files\n        files.download(str(output))\n    except ImportError:\n        display(FileLink(str(output)))',form=True,tags=('export-package',))
md('''## 10. Importa il pacchetto nella repository
Dopo il download, dal terminale nella cartella `Runup_GUI`, per aggiornare una località già presente:

```sh
python scripts/import_site_package.py /percorso/borghetto-santo-spirito_studio.zip --replace
```

Per una località nuova ometti `--replace`. Il controllo della configurazione viene eseguito prima di scrivere i file. Per una prova locale con un pacchetto demo serve anche `--allow-demo`; non usarlo per pubblicare parametri di esempio come dati reali.

Dopo l’importazione rigenera il bollettino e verifica il risultato nel portale. Il download ERA5 rimane un’attività di setup: gli aggiornamenti giornalieri leggono il riferimento già salvato.

### Riferimenti
- Metodo della pendenza: notebook didattico fornito dall’utente **Stockdon_runup_soluzione.ipynb**, celle 24–25.
- Stockdon, H. F., Holman, R. A., Howd, P. A., & Sallenger, A. H. (2006). *Empirical parameterization of setup, swash, and runup*. Coastal Engineering, 53(7), 573–588. https://doi.org/10.1016/j.coastaleng.2005.12.005
- ERA5 hourly time-series: https://doi.org/10.24381/1cf1ad76. Il downloader adatta lo script fornito dall’utente, copyright 2026 Alessio Rovere, MIT; la licenza è inclusa nella cella tecnica.
- [Colab: caricamento, salvataggio e condivisione dei notebook](https://research.google.com/colaboratory/faq.html).''')
for cell in cells:
    first_line=cell.source.splitlines()[0]
    if previous_ids.get(first_line):
        cell.id=previous_ids[first_line]
nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'colab':{'name':'Definisci_siti_studio.ipynb','provenance':[]}})
nbf.validate(nb)
target=ROOT/'notebooks/Definisci_siti_studio.ipynb'
target.parent.mkdir(exist_ok=True)
nbf.write(nb,target)
print(target, len(cells),'celle')
