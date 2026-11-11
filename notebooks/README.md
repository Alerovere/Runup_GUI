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

Tre file obbligatori per un’area reale:

- **DEM GeoTIFF** dell’intera area, con CRS e quote in metri.
- **Ortofotomosaico GeoTIFF** dell’intera area, georeferenziato e a 8 bit, grigio/RGB/RGBA.
- **GeoJSON delle linee dei transetti**, con un ID univoco per linea; il campo iniziale è `TR_ID`, modificabile.

Un file facoltativo:

- **GeoJSON dei poligoni dei settori costieri**, con ID e nome; i campi iniziali sono `sector_id` e `name`, modificabili. Gli ID usano minuscole, numeri e trattini. `whole` è riservato alla spiaggia intera.

Non serve un CSV di punti né ritagliare manualmente i raster. Per GeoJSON standard usare EPSG:4326; se il file dichiara un altro CRS, indicarlo esplicitamente. Il CRS di lavoro dei profili deve essere proiettato in metri, per esempio quello effettivamente usato nel rilievo. Le Z del GeoJSON vengono ignorate: le quote si estraggono dal DEM.

Conservare i sorgenti in **`notebooks/dati originali/`**, esclusa da Git. La cartella resta sul Mac e non entra nel push. Da Colab caricare i file oppure indicare percorsi su Drive: i percorsi del Mac non sono leggibili dal runtime Colab. I GeoTIFF originali non entrano nel pacchetto esportato.

## Il percorso nel notebook

1. **Ambiente e cartella di lavoro.** Installare le librerie e scegliere modalità demo o dati reali, con eventuale salvataggio su Drive.
2. **Area e dati marini comuni.** Definire nome, coordinate e punto offshore; scegliere le direzioni di provenienza che espongono l’area. Questi dati valgono per tutta l’area. I flussi reali di previsione sono configurati nel servizio, non scaricati separatamente per ogni settore costiero dal notebook.
3. **File dell’area.** Caricare DEM, ortofoto e transetti una sola volta. Caricare anche i poligoni se si vogliono settori costieri. `PASSO_CAMPIONAMENTO_M=0` usa il passo del DEM; un numero positivo sceglie il passo in metri. NoData e punti esterni al raster restano quote mancanti.
4. **Pendenze e controllo dei transetti.** Verificare tabella, grafici e orientamento mare→terra. Correggere o escludere esplicitamente i profili non validi. La pendenza segue il notebook didattico: distanza euclidea X/Y dal primo punto a mare, arresto prima del primo punto sopra `Z_MAX` e regressione sui punti precedenti con quota almeno `Z_MIN`. Le linee dovrebbero essere rettilinee. Nessuna modifica alle formule di runup.
5. **Settori costieri facoltativi.** Con i poligoni, il centro della battigia usata per il fit assegna ogni transetto al settore costiero. I casi ambigui richiedono una correzione o `ASSEGNAZIONI_MANUALI`; le linee non vengono tagliate. Senza poligoni si conserva una sola spiaggia.
6. **Strutture esposte.** Compare una scheda per ogni settore costiero, oppure una sola scheda per la spiaggia intera. Modificare nomi, quote e attività estiva/annuale; deselezionare le strutture assenti o aggiungerne altre. Gli elenchi possono essere diversi e anche vuoti: grafici e mappa restano disponibili. Eseguire la verifica sotto il modulo dopo le modifiche.
7. **Ritagli e crediti.** I raster sono già caricati. Compilare autore, data, licenza e riferimento delle quote. Il notebook prepara il dominio con margine e le immagini ritagliate senza altri selettori di sorgente o interruttori per attivare le mappe. Senza settori costieri usa l’estensione del DEM. L’anteprima controlla terreno e avvio verso mare, non contiene ancora la previsione.
8. **Serie storica ERA5 comune.** Scaricare una volta per l’area oppure importare una serie disponibile. Distribuzione, massimi annuali, Gumbel per provenienza e citazioni restano conservati. I dati di previsione sono scaricati dal servizio giornaliero e condivisi tra i settori costieri.
9. **Controllo ed esportazione.** Il riepilogo legge nuovamente le strutture dal modulo corrente. Il pacchetto comprende configurazione, profili, diagnostica, ritagli e climatologia disponibile. Gli originali, i token e i NetCDF completi non vengono inclusi. Un pacchetto demo è marcato come tale.
10. **Importazione locale.** Eseguire `python scripts/import_site_package.py /percorso/sito_studio.zip --replace` per aggiornare una località esistente, omettendo `--replace` per una nuova. Dopo il controllo locale, commit/push e workflow pubblicano i derivati.

## Risoluzione e riferimento verticale

L’ortofoto pubblicata parte da **0,5 m/pixel**, indipendentemente dal DEM originale usato per i profili. Il campo è `RISOLUZIONE_ORTOFOTO_M`. Il singolo ritaglio deve rientrare in 4096 pixel per asse e 12 MiB: un passo troppo fine produce un errore esplicito, senza degradazione silenziosa. L’esterno del poligono e le zone senza ortofoto sono trasparenti, lasciando visibile OpenStreetMap.

Il DEM cartografico è preparato su una griglia leggera, fino a 1024 pixel per asse. Il ricampionamento può perdere opere strette: controllare muri, varchi, dune e NoData. I punti di avvio verso mare sono ricavati dai primi punti validi dei profili orientati, verificabili nell’anteprima e sostituibili con `PUNTI_MARE_MANUALI`.

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
