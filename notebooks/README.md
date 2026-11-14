# Configura un’area di studio in Colab

Aprire `Definisci_siti_studio.ipynb` con **File → Carica notebook** in [Google Colab](https://colab.research.google.com/). Il notebook include le funzioni del progetto e prepara un pacchetto ZIP; non pubblica il sito. Per provare senza account o download usare `DEMO=True`.

## Area e settori costieri

**L’area di studio è la località**, per esempio Borghetto Santo Spirito. Può essere una spiaggia intera oppure essere suddivisa in **settori costieri**, rappresentati da poligoni GeoJSON.

| Comuni a tutta l’area | Specifici di ogni settore costiero |
|---|---|
| DEM e ortofotomosaico sorgenti | Transetti assegnati e relative pendenze |
| Direzioni di esposizione alle onde | Elenco delle strutture esposte e quote |
| Punto/serie delle previsioni di onde, surge e marea | Runup, TWL, confronti con le strutture |
| Punto e serie storica ERA5, statistiche comprese | Ritaglio e risultato della mappa |

Il servizio scarica le forzanti una volta per area e le riusa per tutti i settori costieri. Le direzioni di esposizione non si impostano separatamente per settore costiero. I settori statistici di provenienza delle onde ERA5 sono un’altra cosa: riguardano la distribuzione delle direzioni offshore e restano comuni all’area.

## File da preparare

Due file obbligatori per un’area reale:

- **DEM GeoTIFF** dell’intera area, con CRS e quote in metri.
- **GeoJSON delle linee dei transetti**, con un ID univoco per linea; il campo iniziale è `TR_ID`, modificabile.

File facoltativi:

- **Ortofotomosaico GeoTIFF** dell’intera area, georeferenziato e a 8 bit, grigio/RGB/RGBA. Senza ortofoto lo sfondo è il DEM a colori con legenda delle quote; dove manca il DEM rimane OpenStreetMap. Lasciare vuoto `FILE_ORTOFOTO_COMUNE` e disattivato `USA_ORTOFOTO` per saltarla.
- **GeoJSON dei poligoni dei settori costieri**, con ID e nome; i campi iniziali sono `sector_id` e `name`, modificabili. Gli ID usano minuscole, numeri e trattini. `whole` è riservato alla spiaggia intera.
- **GeoJSON dei punti delle strutture**, descritto più sotto.

Non serve un CSV di punti né ritagliare manualmente i raster. Per GeoJSON standard usare EPSG:4326; se il file dichiara un altro CRS, indicarlo esplicitamente. Il CRS di lavoro dei profili deve essere proiettato in metri, per esempio quello effettivamente usato nel rilievo. Con **DEM + linee** le Z del GeoJSON vengono ignorate e le quote si estraggono dal DEM. Con **GNSS (LineString XYZ)** si usano invece le quote Z misurate, come descritto sotto; il DEM resta necessario per cartografia e punti delle strutture.

Conservare i sorgenti in **`notebooks/dati originali/`**, esclusa da Git. La cartella resta sul Mac e non entra nel push. Da Colab caricare i file oppure indicare percorsi su Drive: i percorsi del Mac non sono leggibili dal runtime Colab. I GeoTIFF originali non entrano nel pacchetto esportato.

## Il percorso nel notebook

1. **Ambiente e cartella di lavoro.** Installare le librerie e scegliere modalità demo o dati reali, con eventuale salvataggio su Drive.
2. **Area e dati marini comuni.** Definire nome, coordinate e punto offshore; scegliere le direzioni di provenienza che espongono l’area. Questi dati valgono per tutta l’area. I flussi reali di previsione sono configurati nel servizio, non scaricati separatamente per ogni settore costiero dal notebook.
3. **File dell’area.** Scegliere `SORGENTE_PENDENZE`: **DEM + linee** oppure **GNSS (LineString XYZ)**. Impostare percorsi, CRS e campi, poi eseguire la lettura dei file. Per GNSS, confermare i campi nei menu comparsi e proseguire con **Leggi i profili**. DEM e transetti sono obbligatori per questo percorso con mappe; ortofoto, poligoni e punti delle strutture sono facoltativi. `PASSO_CAMPIONAMENTO_M` riguarda soltanto i profili DEM: 0 segue il pixel, un numero positivo sceglie il passo in metri. I vertici GNSS non vengono ricampionati.
4. **Pendenze e controllo dei transetti.** Eseguire **Imposta il calcolo**, scegliere l’orientamento e poi **Calcola le pendenze**. Per DEM il modulo include Zmin/Zmax e conserva il metodo didattico. Per GNSS non compaiono controlli Zmin/Zmax: si usa l’intera battigia misurata. Controllare grafici e tabella; correggere o escludere esplicitamente i profili non validi. Le formule di runup restano invariate.
5. **Settori costieri e campionamento.** Eseguire **Controlla l’assegnazione**, scegliere nei menu i casi ambigui, poi eseguire **Assegna**. Rinominare i settori nelle caselle ed eseguire **Conferma nomi e campiona**: i nomi pubblici cambiano, gli ID rimangono stabili. Le linee non vengono tagliate. Senza poligoni si conserva una sola spiaggia. Il campionamento Monte Carlo è descritto sotto.
6. **Strutture esposte.** Compare una scheda per ogni settore costiero, oppure una sola scheda per la spiaggia intera. Modificare nomi, quote e attività estiva/annuale; deselezionare le strutture assenti o aggiungerne altre. Gli elenchi possono essere diversi e anche vuoti: grafici e mappa restano disponibili. Eseguire la verifica sotto il modulo dopo le modifiche.
7. **Ritagli e crediti.** Compilare in ordine **7A** (autore, data, licenza), **7B** (riferimento e correzione delle quote), **7C** (risoluzione e controlli avanzati), poi eseguire **Prepara i ritagli**. Il riepilogo mostra per ogni settore pochi indicatori e il collegamento al CSV completo degli avvii. Senza settori costieri si usa l’estensione del DEM. L’anteprima controlla terreno e avvio verso mare, non contiene ancora la previsione.
8. **Serie storica ERA5 comune.** Scaricare una volta per l’area oppure importare una serie disponibile. Distribuzione, massimi annuali, Gumbel per provenienza e citazioni restano conservati. I dati di previsione sono scaricati dal servizio giornaliero e condivisi tra i settori costieri.
9. **Controllo ed esportazione.** Il riepilogo legge nuovamente le strutture dal modulo corrente. Il pacchetto comprende configurazione, profili, diagnostica, ritagli e climatologia disponibile. Gli originali, i token e i NetCDF completi non vengono inclusi. Un pacchetto demo è marcato come tale.
10. **Importazione locale.** Eseguire `python scripts/import_site_package.py /percorso/sito_studio.zip --replace` per aggiornare una località esistente, omettendo `--replace` per una nuova. Dopo il controllo locale, commit/push e workflow pubblicano i derivati.

## Transetti GNSS già rilevati sulla battigia

Il formato è un GeoJSON **FeatureCollection di LineString XYZ**, una linea per transetto. Ogni vertice contiene `[X, Y, Z]`; la Z deve essere in **metri**. Non si aggiungono punti, non si seleziona un intervallo di quota e non si sostituiscono le quote GNSS con quelle del DEM.

Nel punto 3 scegliere **GNSS (LineString XYZ)**, caricare il file e confermare i menu. Per il file fornito:

| Selettore | Valore |
|---|---|
| Identificativo | `transect_id` |
| Campo pendenza β | `tan_beta` |
| Campo R² fornito | `r2` |
| Quote | terza coordinata Z della geometria |
| CRS del file | `EPSG:3003`, letto dalla dichiarazione del GeoJSON |

L’ID è obbligatorio, deve essere univoco e può essere scelto fra i campi del file. I campi β e R² sono facoltativi nel ricalcolo e selezionabili fra gli attributi numerici completi. `n_points` e `length_m` non sono necessari: numero di punti e lunghezza sono ricavati dai vertici. Un campo R² scelto deve essere compreso fra 0 e 1; una pendenza fornita deve essere positiva e inferiore a 1, espressa come rapporto m/m, non gradi o percentuale.

Due metodi espliciti:

- **Ricalcola su tutti i punti XYZ**, predefinito: trasformazione delle sole coordinate X/Y nel CRS metrico di lavoro; distanza euclidea dal primo punto a mare; regressione lineare della quota su tutti i vertici. I valori β e R² eventualmente forniti restano separati per confronto, inclusa la differenza di pendenza. Il risultato può differire da una pendenza calcolata con un’altra definizione di distanza o metodo di fit.
- **Usa il campo pendenza selezionato:** β è quello contenuto nell’attributo scelto. Il metodo viene registrato come importazione da campo, senza presentarlo come nuovo fit. Nel grafico la retta associata al valore fornito passa per le medie di distanza e quota; il suo R² calcolato resta distinto dal campo R² originale.

Per orientare profili brevi, il confronto fra gruppi di quote alle estremità usa gruppi non sovrapposti, fino a 10 punti per lato. È sempre possibile dichiarare se il primo o l’ultimo punto è a mare. Il percorso DEM conserva la regola didattica originale delle prime/ultime 10 quote. Linee curve o con ritorni vengono segnalate ma non rettificate o riordinate. NaN nelle quote GNSS, vertici 2D, ID duplicati, CRS discordanti e punti consecutivi coincidenti producono un errore esplicito.

La correzione e il riferimento verticale GNSS sono **separati da quelli del DEM**. La correzione GNSS si somma soltanto alle sue quote e non cambia la pendenza di un fit con intercetta. Non si assume un raccordo automatico fra quote ellissoidiche, ortometriche o livello medio mare. Punti delle strutture e mappe continuano a usare il DEM e il suo raccordo al TWL.

Per la cartografia vengono campionate quote DEM lungo le linee GNSS, orientate secondo il lato mare del rilievo. Questi campioni densi servono **soltanto a verificare gli avvii delle mappe** e non entrano nel fit GNSS, nell’assegnazione dei settori o nella distribuzione Monte Carlo. In questa sola ricerca cartografica la distanza segue la progressiva della linea, così un eventuale tratto di ritorno non rientra falsamente nei primi metri. La distanza del fit GNSS resta euclidea. Il report aggiuntivo è `campioni_dem_solo_avvii_mappa.csv`. I limiti di ricerca degli avvii rimangono quelli del punto 7; controllare i punti rossi.

Profili, pendenze, campi selezionati, CRS, correzione, riferimento, metodo e hash del sorgente sono tracciati nel pacchetto, insieme al GeoJSON originale. Modificando file, campi o impostazioni occorre rieseguire lettura, calcolo e passaggi successivi prima dell’esportazione.

## Come i transetti alimentano i modelli di runup

La pendenza è ricavata separatamente da ogni transetto: metodo didattico per il DEM, intera battigia XYZ oppure campo selezionato per il GNSS. Dopo le eventuali esclusioni, il campionamento è applicato **separatamente ai transetti di ciascun settore**, oppure all’intera spiaggia se non suddivisa. Le opzioni sono:

- **Monte Carlo · normale troncata**, preimpostata: media aritmetica e deviazione standard con divisore N delle pendenze misurate, comprese le osservazioni ripetute; campionamento della normale limitata al minimo e massimo misurati del settore. `NUM_CAMPIONI_MC=200` e `SEME_MONTE_CARLO=42` sono modificabili. Il numero consentito è 2–2000. Media e deviazione standard descrivono la normale prima del troncamento, non necessariamente i campioni risultanti.
- **Valori dei transetti:** le pendenze misurate distinte, come nel percorso precedente.
- **Intervallo minimo-massimo:** `NUM_PENDENZE` valori equidistanti fra gli estremi del singolo settore.

Con un solo transetto o pendenze tutte uguali si usa una sola pendenza fissa, senza inventare una dispersione. Gli istogrammi permettono di confrontare misure e valori usati. Non si applica una ponderazione per lunghezza di costa né si stimano errori del rilievo.

Ogni pendenza viene applicata a ciascuna formula empirica. I campioni sono salvati nella configurazione e nel CSV `pendenze_campionate.csv`, con i metadati in `campionamento_pendenze.json`; il servizio usa gli stessi valori nei cicli successivi. Un seme derivato dall’ID del settore rende le estrazioni indipendenti dall’ordine dei settori. L’importazione verifica la coerenza con i transetti assegnati; modificando assegnazioni o pendenze occorre ricampionare. Le configurazioni precedenti prive di questi metadati conservano il comportamento precedente.

Il campionamento descrive una **sensibilità alla variabilità della spiaggia**, non probabilità di allagamento né affidabilità delle formule. Il filtro ±3σ dei risultati e i percentili P75/P95 restano distinti dal campionamento delle pendenze e non vengono modificati.

## Risoluzione e riferimento verticale

L’ortofoto pubblicata parte da **0,5 m/pixel**, indipendentemente dal DEM originale usato per i profili. Il campo è `RISOLUZIONE_ORTOFOTO_M`. Il singolo ritaglio deve rientrare in 4096 pixel per asse e 12 MiB: un passo troppo fine produce un errore esplicito, senza degradazione silenziosa. L’esterno del poligono e le zone senza ortofoto sono trasparenti, lasciando visibile OpenStreetMap.

Il DEM cartografico è preparato su una griglia leggera, fino a 1024 pixel per asse. Il ricampionamento può perdere opere strette: controllare muri, varchi, dune e NoData. Un punto valido nel raster originale può cadere su NoData nella griglia cartografica. Per ogni transetto orientato mare–terra, il notebook cerca quindi la prima cella cartografica valida lungo il tratto iniziale dello stesso transetto, entro `MAX_AVANZAMENTO_AVVIO_M` (predefinito: 5 m) e `MAX_RIALZO_AVVIO_M` (0,5 m rispetto alla prima quota valida). La ricerca si arresta al primo superamento del rialzo consentito nel profilo originale; non cerca lateralmente né modifica le quote o i NoData.

Controllare gli spostamenti nella tabella, nei file diagnostici `avvii_mare_<settore>.csv` e nell’anteprima con i punti rossi. Questi limiti sono controlli di preparazione, non parametri del modello di runup. Se un transetto non offre una cella valida, la preparazione si ferma e lo segnala: non viene escluso automaticamente. Nel modulo 7C si possono indicare `UNITA_AVVII_MANUALI` e `PUNTI_AVVIO_MANUALI_JSON` per un singolo settore; i punti manuali devono già cadere su celle valide della griglia preparata e non vengono spostati.

### Prova sul DSM: limite originale e linea regolarizzata

Il passaggio **7.1** permette di lavorare direttamente sul DSM con **sole linee**, senza riempire celle o preparare un DTM. È una prova facoltativa di rappresentazione cartografica, separata dalle pendenze, dalle quote delle strutture e dalle previsioni pubblicate.

1. Eseguire prima **Prepara i ritagli per il sito**.
2. Impostare `ESEGUI_PROVA_LINEA=True` nella cella **Quota di prova e regolarizzazione della linea**.
3. Scegliere `QUOTA_TWL_PROVA_M`, nello stesso riferimento del DEM cartografico già corretto. Il valore iniziale di 1,4 m è una quota di prova, non una previsione.
4. Impostare `TOLLERANZA_LINEA_M`: inizialmente 1 m, da controllare rispetto a risoluzione e precisione del rilievo; 0 mantiene il limite originale. Il parametro agisce sul disegno della linea e non sulle celle raggiunte.
5. Lasciare `UNITA_LINEA_DA_VEDERE` vuoto per il primo settore, oppure inserire uno degli ID stampati; poi eseguire **Confronta il limite originale e la linea regolarizzata**.

La mappa interattiva mostra l’ortofoto, oppure il DEM con legenda delle quote se l’ortofoto manca, e la linea regolarizzata; il menu dei livelli permette di accendere il limite originale tratteggiato. Compare anche un confronto statico affiancato. Le uscite sono salvate in `prova_linee/` nella cartella del sito; l’HTML è consultabile separatamente.

Il fronte originale deriva dal consueto riempimento connesso al mare. I contorni degli isolotti interni vengono omessi, senza dichiarare raggiunte le celle al loro interno. Le interfacce con NoData e i bordi del ritaglio non vengono trasformati in limiti di risalita. La linea è semplificata con Douglas–Peucker e conservazione della topologia; viene ritagliata nuovamente sulla copertura valida e sul poligono da mostrare. Nei tratti regolarizzati il disegno può differire dal bordo delle celle: non usarlo per misurare superfici o valutare strutture.

Se il risultato non ha un fronte osservabile, il notebook lo segnala: può dipendere da quota troppo bassa/alta, copertura insufficiente o NoData. Non viene inventato un limite sul bordo del DEM. Un ombrellone che blocca il calcolo come falsa barriera resta un problema del DSM: la regolarizzazione del disegno non ricostruisce la propagazione oltre l’ostacolo.

Con la prova attiva, il pacchetto include GeoJSON delle due linee, PNG di confronto e metadati nella sola diagnostica. Il controllo prima dell’esportazione verifica che quota, tolleranza, settore e griglia corrispondano all’anteprima corrente. Questi allegati non attivano la regolarizzazione sul sito; griglie originali e calcoli scientifici restano invariati. Con `ESEGUI_PROVA_LINEA=False` il setup prosegue come prima.

DEM, TWL e quote delle strutture devono usare lo stesso riferimento verticale. `CORREZIONE_QUOTE_DEM_M` riguarda i profili; `CORREZIONE_DEM_MAPPA_M` riguarda il DEM delle mappe. Non confermare il raccordo verticale prima della verifica. Le mappe mostrano un’estensione statica potenziale, non profondità, durata o probabilità di inondazione.

Il riferimento SSH storico Copernicus, quando usato, resta comune all’area e si applica soltanto al relativo fornitore. Non viene sottratto a NOAA + MeteOcean. ERA5 e il riferimento SSH sono distinti: il setup mantiene le procedure già presenti per entrambi.

Gli strumenti Python che importano CSV di profili già campionati restano disponibili (`forecast_service.site_setup` e `scripts/setup_location.py`); il percorso principale del notebook usa direttamente GeoJSON e DEM.

Riferimento delle pendenze: notebook fornito `Stockdon_runup_soluzione.ipynb`, celle 24–25; Stockdon et al. (2006), https://doi.org/10.1016/j.coastaleng.2005.12.005. Le formule e le citazioni dei modelli del portale restano invariate.

## Quote delle strutture da punti GeoJSON (facoltativo)

Puoi aggiungere un unico GeoJSON di **punti** per tutta l’area, anche con tipi di struttura diversi tra settori costieri. Imposta `FILE_PUNTI_STRUTTURE` nel passaggio dei file oppure attiva `USA_PUNTI_STRUTTURE` per caricarlo dal computer.

Il campo richiesto è **`struttura`**, un nome testuale come `Chiosco`, `Passeggiata` o `Prima fila di ombrelloni`. Usa lo stesso valore per punti dello stesso tipo; maiuscole e spazi ripetuti vengono normalizzati. Nomi diversi restano tipi diversi. Non servono quote nel GeoJSON: la Z delle geometrie viene ignorata e la quota viene campionata dal **DEM originale**.

Il notebook:

1. assegna il punto al poligono del settore costiero, oppure alla spiaggia intera se non suddivisa;
2. legge la cella DEM, applicando scala/offset del raster e la correzione verticale dell’area;
3. raggruppa per **settore costiero + struttura** e propone la **media aritmetica dei punti validi**, con uguale peso per punto;
4. mostra anche minimo, massimo, punti esclusi e numero di celle DEM distinte;
5. riempie il modulo delle strutture soltanto con le voci mappate nel relativo settore, senza aggiungere gli esempi non osservati. Puoi modificare nomi, quote, stagione e presenza prima di esportare.

Campi facoltativi nei punti:

- `stagione`: `estiva`/`summer` oppure `annuale`/`all_year`. Se manca si propone attività annuale da verificare nel modulo. Valori discordanti nello stesso gruppo richiedono di correggere il file.
- `settore_costiero`: ID del poligono da usare per un punto sul confine o in poligoni sovrapposti. Il settore indicato deve effettivamente contenere il punto.
- `id`: identificativo leggibile per ritrovare il punto nella diagnostica. Se manca, il report usa il numero progressivo del punto nel file.

Punti senza quota, fuori DEM o fuori dai settori, con geometria non valida o assegnazione ambigua non valgono zero e non vengono assegnati a un settore arbitrario. Il notebook mostra il problema e richiede correzione o conferma esplicita dell’esclusione tramite `ESCLUDI_PUNTI_STRUTTURE_NON_VALIDI`. Un gruppo senza quote valide non riceve una quota inventata; i settori senza punti validi restano senza voci proposte.

**Mappa la quota fisicamente esposta all’acqua:** terreno alla base, ingresso o altro punto di confronto definito nello studio. Se il raster contiene i tetti, la lettura sui tetti non rappresenta la quota del terreno. La media non descrive il primo punto che potrebbe essere raggiunto: per questo rimangono visibili minimo e massimo. Nessuna quota è ricavata dall’ortofoto ricampionata.

Poiché punti e mappa usano lo stesso DEM, il notebook verifica che le correzioni verticali coincidano. Se la quota proposta viene modificata a mano, il pacchetto conserva separatamente la media osservata e segnala `manual_override`. Vengono inclusi GeoJSON dei punti e CSV di dettaglio/riepilogo nella diagnostica, insieme agli hash e ai parametri di estrazione; i GeoTIFF originali restano fuori dal pacchetto.
