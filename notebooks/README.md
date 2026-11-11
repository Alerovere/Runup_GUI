# Definizione dei siti in Colab

Aprire `Definisci_siti_studio.ipynb` in [Google Colab](https://colab.research.google.com/) usando **File → Carica notebook**. Le funzioni sono incluse nel notebook: non occorre clonare la repository, pubblicare il sito o configurare GitHub per eseguirlo.

## Prima prova

1. Eseguire le celle in ordine con `DEMO=True`. Non servono token né richieste a servizi esterni; i profili e la distribuzione delle onde sono sintetici e dichiarati come tali.
2. Controllare la tabella delle pendenze e il grafico: i punti arancioni sono quelli usati per la regressione. Il terreno dietro il primo punto sopra Z_MAX deve essere escluso anche se torna a quote inferiori.
3. Esportare il pacchetto demo per familiarizzare con i contenuti. L’importatore del portale lo rifiuta per impostazione predefinita.

## I propri siti di studio

1. Impostare `DEMO=False`, poi rieseguire tutte le celle.
2. Compilare nome, identificativo, tratto di costa e coordinate del sito e del punto onde offshore. Si può impostare un punto distinto per il livello marino. La mappa mostra i punti e restituisce coordinate al clic; riportare quelle scelte nei campi e rieseguire la cella.
   Definire anche i settori di provenienza delle onde che espongono la spiaggia, oppure lasciare il campo vuoto se ancora sconosciuti. Sono ammessi più settori arbitrari, in gradi dal Nord geografico e in senso orario: `20,120;250,300` è solo un esempio di formato. Il settore `315,45` attraversa il Nord; `0,360` include tutte le direzioni. Lo schema circolare serve a verificare la scelta. Nessun settore è preimpostato per Venezia o Borghetto.
3. Caricare il CSV QGIS o indicare un file già presente. I nomi iniziali sono quelli del notebook fornito: `TR_ID`, `distance`, `SAMPLE_1`, `X`, `Y`. Sono modificabili. Indicare il CRS proiettato in metri; EPSG:32632 è solo il valore iniziale per Borghetto. Le quote devono riferirsi a un riferimento dichiarato, con correzione esplicita se necessaria.
4. Impostare Z_MIN e Z_MAX. Il metodo è quello del notebook didattico: orientamento dalla media delle prime/ultime 10 quote, distanza X/Y dal primo punto a mare, arresto al primo punto sopra Z_MAX e regressione lineare sul tratto precedente con quota almeno Z_MIN. Con profili corti l’orientamento può essere ambiguo: verificarlo e scegliere il verso esplicitamente se necessario. Il segno della pendenza non viene nascosto con un valore assoluto.
5. Esaminare grafici e diagnostica. Correggere i transetti non validi oppure escluderli esplicitamente. Scegliere se esportare le pendenze dei transetti o campionare uniformemente l’intervallo minimo–massimo.
6. Definire stagione estiva, rugosità e soglie delle strutture. Le soglie proposte restano esempi da validare.
7. Scaricare ERA5 dal CDS oppure importare un CSV già disponibile. Il default storico è 1991–2020, modificabile. Il download richiede il consenso esplicito nella cella e le condizioni dei dataset accettate personalmente sul CDS. Il token si legge dai Secrets Colab `CDS_KEY` o tramite input protetto; non scriverlo nei campi del notebook. Per conservare la cache fra sessioni si può attivare il salvataggio su Drive.
8. Verificare distribuzione, percentili 95/99, massimo osservato e massimi annuali. ERA5 fornisce periodo medio, non Tp; il portale continua a usare Tp Copernicus per il runup. Il confronto fra tutte le ore storiche è distinto dal nuovo fit Gumbel dei massimi annuali per settore.
9. Rivedere il riepilogo e scaricare lo ZIP del sito. Dopo aver cambiato modalità o parametri, rieseguire caricamento, calcolo, grafico e selezione prima dell’esportazione: il notebook verifica la coerenza di questi passaggi.

## Importazione nel portale

Dalla radice di Runup_GUI, per aggiornare Borghetto già presente:

```sh
python scripts/import_site_package.py /percorso/borghetto-santo-spirito_studio.zip --replace
```

Per Venezia usare il suo identificativo. Per località nuove omettere `--replace`. L’importatore valida la configurazione prima di aggiornare i file, copia la climatologia quando disponibile e conserva la documentazione del sito in `config/study_sites/IDENTIFICATIVO/`. Non effettua commit, push o pubblicazioni. Per una prova locale esplicita con lo ZIP demo occorre anche `--allow-demo`.

Il pacchetto comprende configurazione, soglie, tabella delle pendenze, profili normalizzati, un grafico del transetto scelto e il riferimento climatologico quando calcolato. I token e i NetCDF della cache non vengono inclusi. Conservare la cache o il CSV storico separatamente per eventuali aggiornamenti.

La stima delle pendenze usa il metodo del notebook fornito, senza cambiare le formule di runup già presenti nell’app. Non viene simulata la propagazione dell’acqua a terra e il riferimento delle quote richiede ancora verifica locale.

## Aggiornare il notebook come sviluppatore

Le funzioni condivise sono in `forecast_service/site_setup.py`, `era5_download.py`, `climate.py`, `exposure.py`, `time_utils.py` e `site_package.py`. Dopo una modifica, rigenerare il notebook per aggiornare la copia inclusa:

```sh
python -m pip install nbformat
python scripts/build_setup_notebook.py
```

Il test `test_notebook_embeds_current_sources` verifica che la copia inclusa non diverga dai moduli del progetto. Il notebook distribuito non contiene output o credenziali salvati.

I settori sono esportati nello ZIP come `location.wave_exposure`. Servono a mostrare avvertenze sul sito: non filtrano la climatologia ERA5 e non azzerano né correggono onde, runup o TWL. Onde fuori settore non garantiscono assenza di effetti sulla spiaggia, perché rifrazione, diffrazione e riparo non sono simulati.

## Curve Gumbel per settore di provenienza

Nella nuova sezione **Impostazioni dei massimi annuali per settore**, lasciare `CALCOLA_ESTREMI_SETTORIALI=True` e scegliere `AMPIEZZA_SETTORI_ESTREMI`. Il valore iniziale di 45° definisce una partizione statistica uniforme di tutte le direzioni: non è una scelta sull’esposizione di Venezia o Borghetto. È possibile usare anche 30°, 60°, 90°, 120°, 180° o tutte le direzioni (360°). I settori sono centrati su multipli dell’ampiezza, con inizio incluso e fine esclusa.

Il download normalizza automaticamente la direzione in `direction_deg`. Per un CSV già disponibile, indicare il nome corretto in `COL_DIREZIONE_ERA5`: la direzione deve indicare la provenienza, in gradi dal Nord geografico e in senso orario. Il vecchio file climatologico con le sole Hs ordinate non consente di ricostruire questa informazione; occorre riusare la serie completa dalla cache o scaricarla nuovamente.

Il notebook seleziona un massimo Hs per anno di calendario UTC **all’interno di ciascun settore**, utilizzando anni con copertura oraria completa. La direzione può mancare nelle ore con Hs=0; una direzione mancante con onde positive rende l’anno incompleto. Non si dividono per direzione i soli massimi annuali generali. Gli anni senza onde positive da un settore non sono eliminati per produrre un fit condizionato: quel settore resta senza stima Gumbel.

Il fit richiede 30 anni utilizzabili per impostazione predefinita. Usa massima verosimiglianza (`scipy.stats.gumbel_r.fit`) e 400 ricampionamenti degli anni per una banda bootstrap al 95%. I grafici di controllo confrontano curva e massimi annuali, con tempi di ritorno 1,01–100 anni. La banda rappresenta l’incertezza del fit e non include bias ERA5/Copernicus, errore previsionale, effetti a riva o non stazionarietà.

Il pacchetto ZIP include i parametri e le curve di tutti i settori e, quando esiste un fit, il grafico `estremi_settoriali.png`. Dopo l’importazione e la rigenerazione del bollettino, il portale seleziona il settore della direzione nell’ora del massimo Hs dei quattro giorni. Il selettore consente di confrontare anche il picco di ciascun altro settore presente nelle onde previste. Un settore senza fit valido rimane esplicitamente senza stima; non viene sostituito dalla curva di tutte le direzioni.

Si assume che i massimi annuali siano indipendenti e stazionari e che Gumbel sia una distribuzione appropriata: sono ipotesi da verificare, non garantite dal numero di anni. Il tempo di ritorno riguarda l’altezza significativa **al largo** per il settore, non runup, TWL o allagamenti. Le elaborazioni rimangono sperimentali e non utilizzabili per previsioni, allerte o decisioni gestionali.

Riferimenti: [Gumbel e metodi SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gumbel_r.html); [convenzione delle direzioni ECMWF](https://confluence.ecmwf.int/spaces/FCST/pages/111155338/What+is+the+direction+convention+for+wave+fields).

## Riferimento SSH fisso: distinto da ERA5

Prima dell’esportazione, la nuova sezione **Riferimento storico del livello marino** definisce lo zero dei grafici e del TWL. Per Borghetto è già incluso il riferimento Copernicus del **2025** (8.760 ore nella cella verificata; media circa −0,4032 m): scegliere **Usa riferimento incluso**. Non occorre riscaricare ERA5.

Per un altro sito scegliere **Calcola da Copernicus**, indicare un anno completo disponibile e abilitare `CONSENSO_DOWNLOAD_SSH`. L’account è quello Copernicus Marine, distinto da CDS: le credenziali possono essere lette dai Secrets Colab `COPERNICUSMARINE_USERNAME` e `COPERNICUSMARINE_PASSWORD` oppure inserite tramite input protetto. Non sono scritte nei file esportati. È possibile anche importare un riferimento JSON precedentemente preparato. Il controllo verifica anno, punto richiesto, cella selezionata e completezza oraria; il riferimento non viene riutilizzato per una cella diversa.

Il pacchetto salva `mean_reference_m` e `sea_level_reference`, inclusi anno, cella, versione del prodotto e hash della serie. La media resta fissa a ogni previsione. I grafici dichiarano **zero = media Copernicus 2025**, e non sostengono che questo coincida già con il livello medio mare locale misurato. Il raccordo alle quote delle strutture resta da verificare.

## Transetti da GeoJSON e raster originali dell’intera area

Per preparare i profili non serve più esportare prima un CSV di punti:

1. Nella sezione 3 scegliere **GeoJSON + DEM**, indicare il file di linee e il DEM GeoTIFF, il campo identificativo dei transetti (inizialmente `TR_ID`) e il CRS del GeoJSON. Per GeoJSON standard è WGS84/EPSG:4326. Il CRS di lavoro dei profili resta proiettato in metri.
2. Impostare `PASSO_CAMPIONAMENTO_M`: `0` usa il passo del DEM, un valore positivo sceglie il passo in metri. Le quote provengono dalle celle del DEM originale, indipendentemente dalla risoluzione dell’ortofoto. Eventuali Z nel GeoJSON non sono usate. NoData e punti esterni restano quote mancanti; non sono riempiti con zero.
3. Verificare diagnostica, orientamento, grafici e selezione della battigia con Z_MIN/Z_MAX, come prima. Il metodo della regressione resta invariato. Le linee dovrebbero essere rettilinee; la distanza per il fit è quella euclidea dal primo punto a mare, come nel notebook di riferimento.
4. Nella sezione 5A attivare `USA_AREE_GEOJSON` e caricare i poligoni. I campi iniziali sono `sector_id` (ID come `ponente`, `centro`, `levante`) e `name` (nome leggibile); si possono modificare. Ogni transetto incluso viene assegnato usando il centro del tratto di battigia selezionato. Confini ambigui o transetti fuori dalle aree richiedono una correzione o `ASSEGNAZIONI_MANUALI`. Le linee non vengono tagliate sui confini dei settori.
5. Nella sezione 5B attivare `PREPARA_MAPPE_DA_AREE`, indicare l’ortofoto comune e i crediti. Il DEM dei profili viene riutilizzato se `FILE_DEM_MAPPE` è vuoto. Il notebook prepara ciascuna mappa usando il poligono con `MARGINE_CLIPPING_M` di margine (100 m iniziali, modificabili). Il margine serve per la connessione; il risultato visualizzato resta ritagliato al settore. I punti di avvio verso mare sono ricavati dai primi punti validi dei profili orientati; sono verificabili nell’anteprima e sostituibili con `PUNTI_MARE_MANUALI`.

Il campo `RISOLUZIONE_ORTOFOTO_M` parte da **0,5 m/pixel** e usa **metri/pixel**, separatamente dal DEM: `0` mantiene le dimensioni della griglia; `0.5` significa 50 cm/pixel e `0.005` significa 5 mm/pixel. Si ricampiona lo sfondo con interpolazione bilineare. L’immagine pubblicata può avere una risoluzione diversa dalla griglia di calcolo ma la stessa estensione geografica. Il passo effettivo ai bordi del rettangolo è approssimato tramite distanze geodetiche; target e dimensioni sono registrati nei metadati.

Per mantenere leggeri pacchetto e sito, un singolo ritaglio ortofoto deve restare entro 4096 pixel per asse e 12 MiB. Un’impostazione troppo fine interrompe la preparazione con un messaggio: non viene degradata silenziosamente. Le parti senza ortofoto restano trasparenti e mostrano OpenStreetMap. Le quote dei profili non vengono ricavate dall’ortofoto ricampionata.

### Cartella locale degli originali

Mettere i file sorgente in `notebooks/dati originali/`, per esempio DEM, ortofotomosaico completo, linee dei transetti e poligoni dei settori. La cartella è esclusa da Git tramite `.gitignore`: **non viene inclusa nel push né scaricata da GitHub/Colab**. Da Colab occorre caricare i file oppure leggerli da Drive; un percorso del Mac non è accessibile dal runtime Colab.

Il pacchetto esporta le griglie e le ortofoto ritagliate/ricampionate, diagnostica e geometrie utili a documentare il setup; non include i GeoTIFF originali. Eseguire il controllo del riferimento verticale e compilare autore, data e licenza dei rilievi prima di abilitare le mappe. Le pendenze e i risultati devono essere ricontrollati dopo aver cambiato i sorgenti.
