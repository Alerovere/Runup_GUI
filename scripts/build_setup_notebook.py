"""Regenerate the standalone Colab notebook from the shared setup modules."""
from pathlib import Path
import json
import nbformat as nbf

ROOT=Path(__file__).resolve().parents[1]
cells=[]
def md(text):
    cells.append(nbf.v4.new_markdown_cell(text.strip()))
def code(text, *, form=False, tags=()):
    cell=nbf.v4.new_code_cell(text.strip())
    if form: cell.metadata['cellView']='form'
    if tags: cell.metadata['tags']=list(tags)
    cells.append(cell)

md('''# Onde a riva — Definizione dei siti di studio

Un sito alla volta: scegli il punto costiero e quello offshore, carica i profili QGIS, verifica la pendenza della battigia, prepara ERA5 ed esporta un pacchetto per il portale.

**Il notebook è autosufficiente:** le funzioni del progetto sono incluse nella cella tecnica; non occorre clonare GitHub o pubblicare il sito. Parti in modalità dimostrativa per vedere tutti i passaggi senza credenziali. Per i tuoi dati disattiva `DEMO` e usa le celle in ordine.

La pendenza segue **Stockdon_runup_soluzione.ipynb**, celle 24–25: orientamento mare→terra dalla media delle prime/ultime 10 quote; distanza euclidea X/Y dal primo punto a mare; selezione prima del primo punto sopra `Z_MAX`; regressione con `np.polyfit`. Le formule di runup del portale restano invariate.

Il pacchetto finale non contiene token o credenziali. Il notebook non pubblica e non modifica automaticamente la repository.''')
md('''## 1. Ambiente e cartella di lavoro
Apri in Colab con **File → Carica notebook**. È sufficiente il runtime CPU. L’installazione riguarda soltanto questo runtime.''')
code('''#@title Installa le librerie
INSTALLA_DIPENDENZE = True #@param {type:"boolean"}
if INSTALLA_DIPENDENZE:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "numpy>=1.24", "pandas>=2", "matplotlib>=3.7", "folium>=0.14", "pyproj>=3.6", "cdsapi>=0.7.7,<1", "netCDF4>=1.7,<2"])
print("Ambiente pronto.")''',form=True,tags=('install-dependencies',))
modules=['__init__.py','site_setup.py','time_utils.py','era5_download.py','climate.py','site_package.py','LICENSE-wave-climate.txt']
sources={'forecast_service/'+name:(ROOT/'forecast_service'/name).read_text() for name in modules}
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
sys.path.insert(0, str(RUNTIME))
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import folium
from IPython.display import display, FileLink
from pyproj import CRS, Transformer
from forecast_service.site_setup import analyze_transects, BEACHFACE_METHOD_VERSION
from forecast_service.era5_download import download_series
from forecast_service.climate import build_climate
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
md('''## 2. Definisci il sito
Le coordinate sono in gradi WGS84. Il punto sulla mappa identifica il sito; quello offshore serve a scaricare onde Copernicus ed ERA5. La cella marina ERA5 verrà verificata durante il download. Il punto del livello marino può essere distinto da quello delle onde.

I valori iniziali sono quelli provvisori di Borghetto; possono essere sostituiti liberamente. Il campo `ID_SITO` deve usare lettere minuscole, numeri e trattini.''')
code('''#@title Identità e punti di estrazione
ID_SITO = "borghetto-santo-spirito" #@param {type:"string"}
NOME_SITO = "Borghetto Santo Spirito (SV)" #@param {type:"string"}
TRATTO_DI_COSTA = "Riviera di Ponente · Mar Ligure" #@param {type:"string"}
LAT_SITO = 44.109 #@param {type:"number"}
LON_SITO = 8.242 #@param {type:"number"}
LAT_ONDE = 44.046833 #@param {type:"number"}
LON_ONDE = 8.389593 #@param {type:"number"}
LIVELLO_STESSO_PUNTO = True #@param {type:"boolean"}
LAT_LIVELLO = 44.046833 #@param {type:"number"}
LON_LIVELLO = 8.389593 #@param {type:"number"}
import re
if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ID_SITO):
    raise ValueError("ID_SITO non valido.")
for lat, lon in [(LAT_SITO,LON_SITO),(LAT_ONDE,LON_ONDE),(LAT_LIVELLO,LON_LIVELLO)]:
    if not np.isfinite([lat,lon]).all() or not 30<=lat<=46.5 or not -18.2<=lon<=37:
        raise ValueError("Le coordinate devono essere nel dominio mediterraneo.")
WORK = BASE / ID_SITO
WORK.mkdir(parents=True, exist_ok=True)
SITE_INPUT = dict(name=NOME_SITO, area=TRATTO_DI_COSTA,
    map_point=dict(latitude=LAT_SITO,longitude=LON_SITO),
    wave_point=dict(latitude=LAT_ONDE,longitude=LON_ONDE))
MAPPA = folium.Map(location=[LAT_SITO,LON_SITO],zoom_start=12,tiles="OpenStreetMap")
folium.Marker([LAT_SITO,LON_SITO],tooltip="Sito costiero").add_to(MAPPA)
folium.CircleMarker([LAT_ONDE,LON_ONDE],radius=7,color="#006d77",tooltip="Punto onde richiesto").add_to(MAPPA)
folium.LatLngPopup().add_to(MAPPA)
display(MAPPA)
print("Clicca sulla mappa per leggere coordinate, poi riportale nei campi e riesegui questa cella.")''',form=True)
md('''## 3. Carica i profili esportati da QGIS
Usa il CSV del tuo notebook, con colonne predefinite `TR_ID`, `distance`, `SAMPLE_1`, `X`, `Y`. Puoi modificare i nomi sotto. **X e Y devono appartenere a un CRS proiettato con unità in metri**, non essere longitudine e latitudine. `distance` serve a ordinare i punti; la distanza della regressione viene ricalcolata da X/Y come nel notebook fornito.

In modalità demo vengono creati due transetti sintetici, uno con ordine inverso, con un abbassamento del terreno dietro la prima quota sopra `Z_MAX`: quel tratto deve rimanere escluso dalla stima.''')
code('''#@title Colonne, coordinate e profili
COL_ID = "TR_ID" #@param {type:"string"}
COL_DIST = "distance" #@param {type:"string"}
COL_Z = "SAMPLE_1" #@param {type:"string"}
COL_X = "X" #@param {type:"string"}
COL_Y = "Y" #@param {type:"string"}
CRS_PROFILI = "EPSG:32632" #@param {type:"string"}
FILE_PROFILI = "" #@param {type:"string"}
SEPARATORE = "," #@param {type:"string"}
DECIMALE = "." #@param {type:"string"}
CORREZIONE_QUOTE_DEM_M = 0.0 #@param {type:"number"}
RIFERIMENTO_QUOTE = "Livello medio mare, da verificare" #@param {type:"string"}
crs = CRS.from_user_input(CRS_PROFILI)
if not crs.is_projected or not all(abs(a.unit_conversion_factor-1)<1e-9 for a in crs.axis_info[:2]):
    raise ValueError("Usa coordinate X/Y in un CRS proiettato in metri.")
if DEMO:
    to_xy = Transformer.from_crs(4326,crs,always_xy=True)
    x0,y0=to_xy.transform(LON_SITO,LAT_SITO)
    demo_rows=[]
    for name,beta,reverse in [("T1",.045,False),("T2",.065,True)]:
        d=np.arange(45)*2.0
        z=beta*d-.3
        z[(d>=40)&(d<=56)]=.4
        xy=np.column_stack([x0+.6*d,y0+.8*d+(10 if name=="T2" else 0)])
        if reverse:
            z=z[::-1]; xy=xy[::-1]
        for i,dist in enumerate(d):
            demo_rows.append({COL_ID:name,COL_DIST:dist,COL_Z:z[i],COL_X:xy[i,0],COL_Y:xy[i,1]})
    profili=pd.DataFrame(demo_rows)
    PROFILE_SOURCE="profili_sintetici"
else:
    if not FILE_PROFILI:
        from google.colab import files
        uploaded=files.upload()
        if len(uploaded)!=1:
            raise ValueError("Carica un solo CSV di profili.")
        name,content=next(iter(uploaded.items()))
        source=WORK/Path(name).name
        source.write_bytes(content)
    else:
        source=Path(FILE_PROFILI)
    profili=pd.read_csv(source,sep=SEPARATORE,decimal=DECIMALE)
    PROFILE_SOURCE=source.name
if len({COL_ID,COL_DIST,COL_Z,COL_X,COL_Y})!=5:
    raise ValueError("I nomi delle cinque colonne devono essere distinti.")
PROFILE_DATA_MODE="demo" if DEMO else "study"
profili[COL_Z]=pd.to_numeric(profili[COL_Z],errors="raise")+CORREZIONE_QUOTE_DEM_M
print(f"{len(profili)} punti, {profili[COL_ID].nunique()} transetti. Fonte: {PROFILE_SOURCE}")
display(profili.head())''',form=True)
md('''## 4. Calcola la pendenza come nel notebook di riferimento
La procedura:
1. elimina le sole quote mancanti e ordina per `distance`;
2. se la media delle prime 10 quote è maggiore di quella delle ultime 10, inverte il profilo;
3. calcola `x_mare = hypot(X-X_primo, Y-Y_primo)`;
4. si ferma **prima del primo punto con quota maggiore di `Z_MAX`**;
5. fra i punti precedenti usa quelli con quota almeno `Z_MIN` e calcola `np.polyfit(x_mare, quota, 1)[0]`.

La pendenza resta con il proprio segno: un risultato negativo non viene convertito in positivo. Vengono segnalati i profili degeneri o con pendenza fuori da 0–1. Con profili molto corti, le prime/ultime 10 quote possono sovrapporsi: verifica il grafico e, se necessario, scegli esplicitamente l’orientamento.''')
code('''#@title Intervallo della battigia e orientamento
Z_MIN = 0.0 #@param {type:"number"}
Z_MAX = 1.0 #@param {type:"number"}
ORIENTAMENTO = "auto" #@param ["auto", "distance_increases_landward", "distance_increases_seaward"]
riepilogo, preparati, selezioni = analyze_transects(profili,Z_MIN,Z_MAX,
    id_col=COL_ID,distance_col=COL_DIST,elevation_col=COL_Z,x_col=COL_X,y_col=COL_Y,orientation=ORIENTAMENTO)
display(riepilogo)
ANALYSIS_SIGNATURE=(Z_MIN,Z_MAX,ORIENTAMENTO,COL_ID,COL_DIST,COL_Z,COL_X,COL_Y,
    hashlib.sha256(pd.util.hash_pandas_object(profili,index=True).values.tobytes()).hexdigest())
riepilogo.to_csv(WORK/"pendenze_transetti.csv",index=False)
validi=riepilogo[riepilogo.status=="valid"]
if validi.empty:
    raise ValueError("Nessun transetto valido: controlla colonne, intervallo e orientamento.")
print("Pendenze valide:",validi.slope.min(),"—",validi.slope.max(),"m/m")
if validi.orientation_ambiguous.any():
    print("Attenzione: orientamento automatico ambiguo per alcuni profili; controlla i grafici.")''',form=True)
code('''#@title Verifica un transetto nel grafico
ID_TRANSETTO_DA_VEDERE = "" #@param {type:"string"}
identifier=ID_TRANSETTO_DA_VEDERE or str(validi.iloc[0].transect_id)
if identifier not in preparati:
    raise ValueError("Transetto non valido o inesistente; scegli un ID dalla tabella.")
p=preparati[identifier]; sel=selezioni[identifier]
info=validi[validi.transect_id==identifier].iloc[0]
fig,ax=plt.subplots(figsize=(10,4))
ax.plot(p.x_mare,p[COL_Z],color=".35",label="Profilo completo")
ax.scatter(p.loc[sel,"x_mare"],p.loc[sel,COL_Z],color="#d87832",label="Punti usati nella regressione",zorder=3)
xfit=p.loc[sel,"x_mare"]
ax.plot(xfit,info.slope*xfit+info.fit_intercept_m,color="#b54135",ls="--",label="Retta stimata")
ax.axhspan(Z_MIN,Z_MAX,color="#d5e9ee",alpha=.35,label="Intervallo di quota")
if info.first_above_zmax_found:
    ax.axvline(p.loc[int(info.stop_index),"x_mare"],color="#8b633f",ls=":",label="Primo punto sopra Z_MAX")
ax.set(xlabel="Distanza euclidea dal primo punto a mare [m]",ylabel="Quota sul riferimento dichiarato [m]",
       title=f"{'DEMO · ' if DEMO else ''}{identifier}: beta = {info.slope:.4f}, R² = {info.r_squared:.3f}")
ax.legend(fontsize=8); ax.grid(alpha=.2); fig.tight_layout()
fig.savefig(WORK/"profilo_selezionato.png",dpi=170)
PLOT_ANALYSIS_SIGNATURE=ANALYSIS_SIGNATURE
plt.show()''',form=True)
md('''Controlla soprattutto che il primo punto sia dalla parte del mare e che i punti arancioni rappresentino la battigia. L’esclusione dietro il primo superamento di `Z_MAX` riprende il notebook didattico; non costituisce una simulazione della connessione idraulica o dell’inondazione.''')
code('''#@title Scegli i transetti e le pendenze da esportare
TRANSETTI_ESCLUSI = "" #@param {type:"string"}
MODALITA_PENDENZE = "Valori dei transetti" #@param ["Valori dei transetti", "Intervallo minimo-massimo"]
NUM_PENDENZE = 5 #@param {type:"integer"}
excluded={v.strip() for v in TRANSETTI_ESCLUSI.split(",") if v.strip()}
unknown=excluded-set(riepilogo.transect_id)
if unknown:
    raise ValueError(f"ID da escludere non riconosciuti: {unknown}")
scelti=riepilogo[~riepilogo.transect_id.isin(excluded)].copy()
if scelti.empty or (scelti.status!="valid").any():
    raise ValueError("Correggi i transetti non validi o escludili esplicitamente prima di esportare.")
if MODALITA_PENDENZE=="Valori dei transetti":
    PENDENZE=sorted(set(float(value) for value in scelti.slope))
else:
    if NUM_PENDENZE<2:
        raise ValueError("Usa almeno due campioni per un intervallo.")
    PENDENZE=sorted(set(float(value) for value in np.linspace(scelti.slope.min(),scelti.slope.max(),NUM_PENDENZE)))
SELECTION_ANALYSIS_SIGNATURE=ANALYSIS_SIGNATURE
print("Pendenze da usare nel portale:",PENDENZE)
print("Gli eventuali valori identici sono deduplicati; gli scenari del portale non pesano i transetti per lunghezza di costa.")''',form=True)
md('''## 5. Stagioni, strutture e riferimento delle quote
Le quote seguenti sono **esempi da definire per il sito**, come nella prima versione del portale. Indica inizio/fine della stagione in formato `MM-GG`; lascia entrambi vuoti se ancora sconosciuti. La correzione del livello marino raccorda il riferimento del modello a quello locale; non va usata per correggere automaticamente il DEM.''')
code('''#@title Configurazione delle soglie
INIZIO_ESTATE = "" #@param {type:"string"}
FINE_ESTATE = "" #@param {type:"string"}
QUOTA_OMBRELLONI_M = 0.7 #@param {type:"number"}
QUOTA_STRUTTURE_STAGIONALI_M = 0.9 #@param {type:"number"}
QUOTA_CHIOSCHI_M = 1.1 #@param {type:"number"}
QUOTA_PASSEGGIATA_M = 1.4 #@param {type:"number"}
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
display(pd.DataFrame(thresholds)[["short_label","elevation_m","season"]])''',form=True)
md('''## 6. ERA5 — scarica una volta o riusa il tuo CSV
Per dati reali servono un account Climate Data Store e l’accettazione personale delle condizioni di [ERA5 time-series](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries?tab=download). La ricerca automatica della cella marina usa anche [ERA5 grigliato](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download).

Puoi salvare il token nei **Secrets di Colab**, con nome `CDS_KEY` e accesso a questo notebook, oppure inserirlo nel campo protetto quando richiesto. Non scriverlo nei campi del notebook. La cache contiene soltanto richieste e dati: sarà riutilizzata se la sessione riparte dalla stessa cartella.

Il servizio ERA5 restituisce **periodo medio**, non Tp: lo salviamo come `tm_s`; non lo usiamo come periodo di picco per il runup. Il confronto storico usa Hs. I massimi annuali osservati non sono periodi di ritorno.''')
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
    era5_frame=pd.DataFrame({"time":time,"hs_m":hs})
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
md('''## 7. Rivedi ed esporta il sito
Il pacchetto contiene configurazione, soglie, pendenze e relativa diagnostica, profili normalizzati e climatologia quando disponibile. **Conserva la cache o il CSV storico in Drive**: il pacchetto riporta il riferimento statistico, non tutti i NetCDF delle richieste.

Un pacchetto prodotto in modalità demo è marcato come tale e l’importatore lo rifiuta per impostazione predefinita. Nessun token entra nel pacchetto. Nessun file del portale viene modificato da Colab.''')
code('''#@title Riepilogo prima dell’esportazione
from forecast_service.time_utils import iso
import hashlib
current_signature=(Z_MIN,Z_MAX,ORIENTAMENTO,COL_ID,COL_DIST,COL_Z,COL_X,COL_Y,
    hashlib.sha256(pd.util.hash_pandas_object(profili,index=True).values.tobytes()).hexdigest())
if PROFILE_DATA_MODE!=("demo" if DEMO else "study") or (CLIMATE is not None and CLIMATE_DATA_MODE!=("demo" if DEMO else "study")):
    raise ValueError("Modalità cambiata: riesegui caricamento profili, pendenze e climatologia prima di esportare.")
if current_signature!=ANALYSIS_SIGNATURE or SELECTION_ANALYSIS_SIGNATURE!=ANALYSIS_SIGNATURE or PLOT_ANALYSIS_SIGNATURE!=ANALYSIS_SIGNATURE:
    raise ValueError("Parametri o profili cambiati: riesegui calcolo, grafico e selezione delle pendenze.")
normalized=profili.rename(columns={COL_ID:"TR_ID",COL_DIST:"distance",COL_Z:"SAMPLE_1",COL_X:"X",COL_Y:"Y"})[["TR_ID","distance","SAMPLE_1","X","Y"]]
normalized.to_csv(WORK/"profili_normalizzati.csv",index=False)
location=dict(SITE_INPUT,slopes=PENDENZE,roughness_m=float(RUGOSITA_M),parameters_status="provisional",
    datum_offset_m=float(OFFSET_LIVELLO_M),vertical_reference_status="provisional",
    climatology_file=f"config/climatology/{ID_SITO}.json" if CLIMATE is not None else None,
    summer_season=dict(start_month_day=INIZIO_ESTATE or None,end_month_day=FINE_ESTATE or None,status="configured" if INIZIO_ESTATE else "to_be_defined"),
    transects=json.loads(scelti.to_json(orient="records")),notes=NOTE_SITO)
if not LIVELLO_STESSO_PUNTO:
    location["sealevel_point"]=dict(latitude=LAT_LIVELLO,longitude=LON_LIVELLO)
payload=dict(schema_version=1,slug=ID_SITO,data_mode="demo" if DEMO else "study",location=location,thresholds=thresholds,
    provenance=dict(created_at=iso(dt.datetime.now(dt.timezone.utc)),slope_method=BEACHFACE_METHOD_VERSION,
        reference_notebook="Stockdon_runup_soluzione.ipynb, celle 24–25",profile_source=PROFILE_SOURCE,
        profile_sha256=hashlib.sha256((WORK/"profili_normalizzati.csv").read_bytes()).hexdigest(),
        profile_data_mode=PROFILE_DATA_MODE,climate_data_mode=CLIMATE_DATA_MODE if CLIMATE else None,
        profile_crs=crs.to_string(),vertical_reference=RIFERIMENTO_QUOTE,z_correction_m=CORREZIONE_QUOTE_DEM_M,
        excluded_transects=sorted(excluded),slope_sampling=MODALITA_PENDENZE,z_min_m=Z_MIN,z_max_m=Z_MAX))
display(pd.DataFrame([{"località":NOME_SITO,"modalità":payload["data_mode"],"transetti inclusi":len(scelti),"pendenze":PENDENZE,"ERA5 o riferimento":CLIMATE["source"] if CLIMATE else "Non configurato","stagione estiva":f"{INIZIO_ESTATE} / {FINE_ESTATE}" if INIZIO_ESTATE else "Da definire"}]))
print("Le soglie e il raccordo delle quote restano da validare, anche con profili misurati.")''',form=True)
code('''#@title Crea e scarica il pacchetto
ESPORTA_PACCHETTO = True #@param {type:"boolean"}
if ESPORTA_PACCHETTO:
    attachments={name:WORK/name for name in ["pendenze_transetti.csv","profili_normalizzati.csv","profilo_selezionato.png"]}
    for name in ["climatologia.png","massimi_annuali.csv"]:
        if CLIMATE is not None and (WORK/name).exists(): attachments[name]=WORK/name
    output=WORK/f"{ID_SITO}_{'DEMO' if DEMO else 'studio'}.zip"
    write_site_package(output,payload,climatology=CLIMATE,attachments=attachments)
    print("Pacchetto creato:",output)
    try:
        from google.colab import files
        files.download(str(output))
    except ImportError:
        display(FileLink(str(output)))''',form=True,tags=('export-package',))
md('''## 8. Importa il pacchetto nella repository
Dopo il download, dal terminale nella cartella `Runup_GUI`, per aggiornare una località già presente:

```sh
python scripts/import_site_package.py /percorso/borghetto-santo-spirito_studio.zip --replace
```

Per una località nuova ometti `--replace`. Il controllo della configurazione viene eseguito prima di scrivere i file. Per una prova locale con un pacchetto demo serve anche `--allow-demo`; non usarlo per pubblicare parametri di esempio come dati reali.

Dopo l’importazione rigenera il bollettino e verifica il risultato nel portale. Il download ERA5 rimane un’attività di setup: i due aggiornamenti giornalieri leggono il riferimento già salvato.

### Riferimenti
- Metodo della pendenza: notebook didattico fornito dall’utente **Stockdon_runup_soluzione.ipynb**, celle 24–25.
- Stockdon, H. F., Holman, R. A., Howd, P. A., & Sallenger, A. H. (2006). *Empirical parameterization of setup, swash, and runup*. Coastal Engineering, 53(7), 573–588. https://doi.org/10.1016/j.coastaleng.2005.12.005
- ERA5 hourly time-series: https://doi.org/10.24381/1cf1ad76. Il downloader adatta lo script fornito dall’utente, copyright 2026 Alessio Rovere, MIT; la licenza è inclusa nella cella tecnica.
- [Colab: caricamento, salvataggio e condivisione dei notebook](https://research.google.com/colaboratory/faq.html).''')
nb=nbf.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'colab':{'name':'Definisci_siti_studio.ipynb','provenance':[]}})
nbf.validate(nb)
target=ROOT/'notebooks/Definisci_siti_studio.ipynb'
target.parent.mkdir(exist_ok=True)
nbf.write(nb,target)
print(target, len(cells),'celle')
