# Setup delle località e del riferimento ERA5

La configurazione di una località è distinta dall’aggiornamento delle previsioni. Si preparano una volta profili, soglie, stagione, punto offshore e serie storica; il processo giornaliero riusa questi dati per le successive 96 ore.

## Ambiente dedicato

Dalla radice della repository, nell’ambiente Python del portale:

```sh
python -m pip install -r forecast_service/setup-requirements.txt
```

Le dipendenze aggiuntive CDS e NetCDF servono al setup storico, senza cambiare `requirements.txt` dell’app Streamlit.

## Una nuova località

```sh
python scripts/setup_location.py
```

Il wizard chiede identificativo, nome, tratto di costa, coordinate della mappa e del punto offshore, pendenze, stagione estiva e quote delle quattro strutture. Le quote sono espresse in metri rispetto al livello medio mare locale, con raccordo al riferimento del modello ancora da verificare. Le stagioni possono differire fra località.

La procedura salva una bozza in `config/site_drafts/IDENTIFICATIVO.json`. Dopo averla rivista:

```sh
python scripts/setup_location.py --from-draft config/site_drafts/IDENTIFICATIVO.json --install
```

Il comando aggiunge la nuova località a entrambi i file di configurazione e rifiuta di sovrascrivere località esistenti. Se l’area non è ancora validata, mantenerla come bozza finché non si vuole includerla nei bollettini.

## Pendenze da transetti

Il wizard accetta un CSV con ascissa lungo il profilo e quota, entrambe in metri:

```csv
transect_id,x_m,z_m
T1,0,0
T1,10,0.5
T1,20,1.0
T2,0,0
T2,10,0.7
T2,20,1.4
```

```sh
python scripts/setup_location.py --profile /percorso/transetti.csv --z-min 0 --z-max 1.5
```

Selezionare l’intervallo di quote che descrive il tratto di spiaggia appropriato ai modelli. Il programma non lo individua automaticamente: stima `abs(dz/dx)` con regressione lineare soltanto nei punti di quell’intervallo, per ogni transetto, e salva numerosità e R² come diagnostica. Servono almeno tre ascisse distinte per transetto. La pendenza non è un angolo in gradi; profili complessi e selezioni che mescolano spiaggia e duna richiedono revisione. Il codice non scarica un DEM né costruisce transetti da una linea di costa.

## Account e accesso ERA5

Il download adatta lo script `Wave_climate/src/wave_climate/download.py` fornito dall’utente, preservando cache delle richieste, gestione ZIP/NetCDF, blocchi temporali e suddivisione dei blocchi troppo grandi. La ricerca della cella marina usa il prodotto ERA5 grigliato per un piccolo riquadro; la serie lunga usa il servizio puntuale `reanalysis-era5-single-levels-timeseries`.

1. Accedere al [Climate Data Store](https://cds.climate.copernicus.eu/how-to-api) e configurare il proprio token CDS nel file standard `~/.cdsapirc`, oppure nella variabile d’ambiente `CDS_KEY`. Non inserire il token nei file versionati o nel sito pubblico. L’account CDS è distinto da quello Copernicus Marine.
2. Aprire la pagina di download di [ERA5 time-series](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries?tab=download) e accettare personalmente le condizioni richieste dal servizio.
3. Per la ricerca automatica della cella marina, fare lo stesso per [ERA5 single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download). In alternativa passare `--cell-lat` e `--cell-lon` per una cella marina già nota.

Il programma usa solo Hs, periodo medio e direzione delle onde; non richiede il vento, perché il confronto storico del portale non lo usa. Il periodo medio ERA5 viene salvato come `tm_s`, senza trasformarlo in Tp. Il runup previsionale continua a usare Tp Copernicus.

## Download storico una volta per località

Il periodo predefinito è 1991–2020, modificabile esplicitamente:

```sh
python scripts/setup_climatology.py venezia --start 1991-01-01 --end 2020-12-31
python scripts/setup_climatology.py borghetto-santo-spirito --start 1991-01-01 --end 2020-12-31
```

Le richieste sono memorizzate nella cache locale `/tmp/onde-a-riva-era5-cache`, configurabile con `--cache`. Per conservarla fra riavvii, scegliere una cartella dati esterna alla repository. Il programma produce `config/climatology/LOCALITA.json`, collega il file alla località e rifiuta di rifare il setup se è già presente. Usare `--replace` soltanto per aggiornare intenzionalmente il riferimento. I blocchi presenti in cache vengono riutilizzati.

Se mancano ore o valori di Hs, il comando si ferma e conserva il CSV in cache. Dopo aver esaminato i dati, `--allow-missing` consente di scartare Hs mancanti registrandone il numero. Il riferimento registra periodo effettivo, copertura dei campioni, cella ERA5, hash del CSV, percentili e massimi annuali osservati.

## Riutilizzare un CSV già scaricato dall’altra app

Non occorre ripetere il download:

```sh
python scripts/setup_climatology.py venezia \
  --csv /percorso/Venezia_ERA5_hourly.csv --hs-column hs
```

Un CSV normalizzato con colonne `time,hs_m` usa i nomi predefiniti. Le date sono in UTC. Il programma verifica tempi distinti, Hs finite e non negative e campionamento regolare. Le serie con campionamento irregolare devono essere preparate esplicitamente prima del confronto.

## Cosa mostra il confronto storico

Il portale confronta ogni Hs prevista con la distribuzione empirica della serie storica completa, considerando tutte le stagioni e direzioni. Mostra percentili 95 e 99, massimo storico osservato e posizione del picco previsto nella distribuzione. I valori vengono calcolati al setup; il processo giornaliero legge il riferimento locale e non richiama CDS.

Un percentile 99 indica che il 99% dei campioni storici ha altezza minore o uguale a quella considerata. Non significa un periodo di ritorno di 100 anni. I massimi annuali salvati sono eventi osservati nella rianalisi; non si adatta qui una distribuzione degli estremi. ERA5 e Copernicus hanno risoluzioni e bias diversi: il confronto diretto è indicativo e non applica una correzione dei bias.

## Livello marino e riferimento delle quote

Il prodotto fisico Copernicus mediterraneo comprende la marea del modello. Il portale scarica `zos` e il riferimento statico `mdt` dalla stessa cella. La formula è:

```text
livello_marino = zos - mdt + datum_offset_m
TWL = livello_marino + runup
```

La superficie media statica fornisce un riferimento fisso; non è una calibrazione al caposaldo locale. Quando disponibile, una `mean_reference_m` validata sostituisce MDT. Una correzione di quota locale si configura con `datum_offset_m`. Non usare contemporaneamente correzioni che rappresentano lo stesso scarto. Non sommare una seconda marea al livello `zos`. Il livello è interpolato linearmente tra campioni orari, senza estrapolare né colmare ore mancanti; un errore impedisce la pubblicazione del nuovo bollettino.

Documentazione: [prodotto fisico](https://data.marine.copernicus.eu/product/MEDSEA_ANALYSISFORECAST_PHY_006_013/description), [manuale Copernicus](https://documentation.marine.copernicus.eu/PUM/CMEMS-MED-PUM-006-013.pdf).

## Verifica e pubblicazione

Dopo il setup:

```sh
python -B -m unittest discover -s tests/forecast -v
python scripts/update_forecasts.py --demo
```

La modalità demo mantiene onde e livello sintetici, chiaramente segnalati. Un riferimento ERA5 reale, se configurato, può essere usato anche per verificare il confronto nella demo. Pubblicare i file climatologici e le configurazioni insieme al codice, mantenendo la cache e i NetCDF locali. Il primo workflow `copernicus` verifica l’accesso reale alle onde, al livello marino e al riferimento statico.
