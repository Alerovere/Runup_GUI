# Settori di spiaggia e cartografia facoltativa

L’app Streamlit resta separata. Queste opzioni riguardano il notebook di setup e il portale statico. Non occorrono nuovi account o servizi web.

## 1. Un’area, eventuali settori costieri

Per il percorso principale del notebook servono DEM e GeoJSON delle linee dei transetti. Ortofotomosaico e poligoni GeoJSON dei **settori costieri** sono facoltativi. Senza poligoni la spiaggia intera rimane rappresentata.

Le pendenze possono provenire da profili campionati sul DEM oppure da transetti **GNSS LineString XYZ già sulla battigia**. Il percorso GNSS offre menu per i campi ID, β e R² e usa tutti i vertici senza Zmin/Zmax: si può ricalcolare β o importare esplicitamente la pendenza dal campo scelto. Il DEM resta la sorgente di cartografia e quote delle strutture; le quote GNSS hanno correzione e riferimento separati. I campioni DEM lungo i transetti GNSS servono soltanto agli avvii cartografici. Vedi `notebooks/README.md` per formato e procedura.

Le direzioni di esposizione, le previsioni di onda/surge/marea e il riferimento storico ERA5 sono comuni all’area. Ogni settore costiero ha i propri transetti e le proprie strutture esposte, anche con nomi, quote ed elenchi diversi. Un’esposizione diversa nel singolo settore costiero viene rifiutata dalla configurazione. I settori statistici di provenienza ERA5 non sono settori costieri.

I transetti sono assegnati con i poligoni usando il centro della battigia selezionata per il fit. I casi ambigui richiedono una scelta esplicita. Il filtro ±3σ e i percentili sono calcolati per settore costiero e ora, mantenendo le formule scientifiche. È possibile non configurare strutture esposte, continuando a calcolare runup, TWL e mappe.

Il notebook offre menu per le assegnazioni ambigue e caselle per i nomi pubblici dei settori, lasciando invariati gli ID. Le pendenze possono essere campionate con Monte Carlo da una normale troncata agli estremi misurati del singolo settore (200 campioni e seme 42 iniziali, modificabili). I campioni sono salvati e validati nel pacchetto, poi riutilizzati nelle previsioni. Restano disponibili i valori misurati e un intervallo regolare. Non sono probabilità di allagamento; vedi `notebooks/README.md` per ipotesi e casi con una sola pendenza.

## 2. File, strutture e ritagli nel notebook

Il caricamento dei sorgenti è unico. Nel passaggio delle strutture compare una scheda per ogni settore costiero, oppure una sola scheda per la spiaggia intera: modificare nome, quota e stagione delle strutture, deselezionare le assenti o aggiungerne altre. Le quattro voci iniziali sono esempi da validare. La tendenza del portale dichiara la struttura di riferimento effettivamente utilizzata; non presuppone che siano presenti chioschi in tutti i settori costieri.

I raster completi possono risiedere in `notebooks/dati originali/`, esclusa da Git. Il preprocessing prepara un dominio DEM con margine e ritaglia le immagini al poligono del settore costiero. In assenza di poligoni usa l’estensione del DEM. I punti di avvio verso mare derivano dai profili orientati e sono modificabili. Compilare crediti, data e licenza, e confermare il raccordo delle quote con lo zero del TWL.

La risoluzione dell’ortofoto pubblicata parte da **0,5 m/pixel**, separatamente dal DEM originale dei profili. La griglia DEM della mappa rimane leggera (massimo 1024 pixel per asse). Il PNG ortofoto, allineato in EPSG:3857, può arrivare a 4096 pixel per asse e 12 MiB. I limiti producono un errore esplicito; non viene alterato silenziosamente il passo richiesto. Le zone esterne o non coperte restano trasparenti e mostrano OpenStreetMap.

Se l’ortofoto non è fornita, il servizio genera dalla griglia preparata uno sfondo DEM con legenda delle quote, sotto le fasce di possibile raggiungimento. NoData ed esterno del poligono sono trasparenti. La scala cromatica satura sotto il 2° e sopra il 98° percentile delle quote visualizzate per rendere leggibile il rilievo della spiaggia: cambia soltanto il colore, non le quote o il calcolo. Le zone fuori scala mantengono il colore estremo. Crediti e riferimento verticale rimangono quelli del rilievo.

Istruzioni dettagliate, ordine dei passaggi e dati richiesti: `notebooks/README.md`. Il notebook non richiede di preparare un CSV dei profili né di attivare separatamente le mappe dopo aver caricato i raster.

## 3. Esportazione, importazione e pubblicazione

Eseguire tutte le celle fino all’esportazione del pacchetto ZIP. Conservare gli originali e il progetto di rilievo in `notebooks/dati originali/`, cartella locale esclusa da Git tramite `.gitignore`. Il push contiene soltanto i derivati scelti e la relativa documentazione, non i GeoTIFF completi. Per aggiornare una località già presente:

```sh
python scripts/import_site_package.py /percorso/sito_studio.zip --replace
```

L’importatore verifica configurazione, allegati, griglia e crediti prima di scrivere. I file preparati finiscono in `config/study_sites/<località>/cartography/<unità>/`. Il pacchetto ha un limite complessivo di 100 MiB non compressi. Il riferimento Copernicus esistente, quando applicabile e compatibile, continua a essere conservato come prima.

Controllare le modifiche, fare commit e push e avviare **Previsioni locali → meteocean**. Il workflow già esistente genera le mappe in `_site/data/maps/` insieme al nuovo bollettino. Il successivo aggiornamento automatico le rigenera. Nessuna modifica a credenziali o programmazione è necessaria.

## 4. Cosa rappresenta la mappa

Per ogni ora si calcola TWL con i contributi contemporanei di runup, marea e surge. Dopo il filtro ±3σ si calcolano media e P75. La mappa propone **Inondazione media prevista dai modelli**, selezionata inizialmente, e **Inondazione massima (fascia centrale)**: rispettivamente la quota oraria maggiore della media e quella del P75 nelle **96 ore fisse dell’elaborazione**. Il P75 è il limite superiore della fascia centrale del 50% (P25–P75), non il massimo assoluto. La media riguarda i risultati contemporanei dei modelli, non le 96 ore nel loro insieme. Non si usa il massimo dei singoli modelli e non si sommano massimi avvenuti in ore diverse. Le viste sono alternative: viene mostrata una sola area alla volta. Il P75 può essere inferiore alla media per alcune distribuzioni: non si impone un ordinamento artificiale alle due aree. Sopra e dentro la mappa vengono dichiarate data e fascia oraria della stima selezionata, in ora italiana con fuso; se il massimo si ripete, si raggruppano le ore consecutive in finestre. Un avviso indica gli orari già trascorsi. Il periodo rimane quello dell’elaborazione e non scorre con l’orologio del browser.

Si propaga sul DEM un livello uniforme dalle celle di avvio verso mare, attraverso celle più basse della quota, con otto vicini. Le depressioni isolate non vengono riempite. La propagazione usa tutto il dominio DEM preparato con margine; il poligono del settore ritaglia soltanto l’output, evitando che il confine del settore diventi una barriera artificiale. Non viene simulata l’interazione idraulica fra settori con quote diverse.

È un’**estensione statica potenziale**, non una simulazione dinamica: il runup è intermittente. Non fornisce durata, profondità effettiva, velocità, portate, infiltrazione o sormonto delle opere. Un bacino connesso dopo il superamento di una cresta può essere sovrastimato dal riempimento statico. Le ore con onde non frontali o direzione sconosciuta sono indicate; non si applica una trasformazione delle onde verso riva.

Dati mancanti o un errore della cartografia rendono indisponibile la sola mappa, con motivazione visibile, senza impedire i grafici. Nessuna mappa viene prodotta con copertura inferiore alle 96 ore o statistiche obsolete. Rimangono tutte le avvertenze sperimentali e le condizioni d’uso del portale.

## GeoJSON datati e archivio per ogni elaborazione

Quando una mappa è disponibile, il servizio genera due GeoJSON WGS84 per località o settore, usando gli stessi risultati media/P75 dei PNG:

- `maps/<località>/<settore>-AAAAMMGGThhmmssZ-aree.geojson`: due geometrie MultiPolygon, una per ciascuna vista, delle celle potenzialmente raggiunte, con i vuoti interni e le componenti distinte conservati. Non è applicata semplificazione alle aree.
- `maps/<località>/<settore>-AAAAMMGGThhmmssZ-limiti.geojson`: due limiti esterni, uno per ciascuna vista, senza i contorni degli isolotti interni, semplificati soltanto per la rappresentazione con tolleranza iniziale di 3 m. Non si inventano linee ai bordi NoData o del ritaglio. L’eventuale campo di configurazione `mapping.line_tolerance_m` può scegliere un valore fra 0 e 20 m. Questo parametro è distinto dalla tolleranza dell’anteprima Colab.

La data nel nome è **l’inizio dell’elaborazione in UTC**, non un riferimento stimato del ciclo del modello. Ogni feature contiene `issued_at_utc`, `generated_at_utc`, inizio/fine delle 96 ore (`forecast_from_utc`, `forecast_to_utc`, estremo finale escluso), `peak_time_utc`, tipo di stima (`estimate=mean` oppure `central_upper`), statistica, percentile (`null` per la media, 75 per il limite centrale), quota TWL, conteggio celle, modalità dei dati, settore, metodo statistico, riferimento verticale, correzione, crediti e hash della griglia. Un’area o un fronte vuoto ha geometria `null` ed è marcato `empty=true`.

I link **Scarica le aree / Scarica i limiti (GeoJSON)**, accanto alla mappa, riguardano l’ultima elaborazione pubblicata. Ogni file contiene anche `peak_to_utc` e `peak_windows_utc`, con fine esclusa. Il metodo cartografico è `connected_static_twl_filtered_mean_p75_v2`; gli archivi precedenti possono contenere P75/P95. Questi inviluppi coprono il periodo di quattro giorni: non sono 96 mappe orarie e non attribuiscono probabilità all’allagamento. I limiti semplificati non vanno usati per misurare superfici.

È disponibile anche un **KMZ per Google Earth**, con aree, limiti, crediti e date leggibili nel nome e nella descrizione. La cartella della media è visibile all’apertura, quella della fascia centrale è disattivata; selezionare una stima alla volta. Le date sono riportate come informazioni, senza un filtro temporale che potrebbe rendere invisibile il file all’apertura. Il KMZ non include l’ortofoto: utilizza lo sfondo dell’app. Formato e importazione su Android/iOS: [documentazione Google Earth](https://developers.google.com/maps/documentation/earth/import-data).

Il **link diretto alla mappa** conserva settore e stima nella URL (`stima=mean` o `central_upper`) e porta alla sezione della mappa nel browser, anche su telefono. Rappresenta l’ultima elaborazione, non una copia immutabile: la copia datata è nei download o nell’archivio.

La Action salva GeoJSON e KMZ in un artifact distinto per ogni esecuzione e tentativo, chiamato `inondazione-<run_id>-<run_attempt>`. Si trova in **GitHub → Actions → Previsioni locali → esecuzione → Artifacts**. La conservazione richiesta è **90 giorni**, entro il limite consentito dalle impostazioni del repository; non è un archivio permanente. Scaricare le copie da conservare più a lungo prima della scadenza. Il sito Pages viene sostituito a ogni deploy e non conserva da solo le uscite precedenti. Riferimento: [conservazione degli artifact GitHub](https://docs.github.com/en/actions/tutorials/store-and-share-data#configuring-a-custom-artifact-retention-period).

Se la quota di una stima è sotto tutti gli avvii disponibili sul DEM, l’area corrispondente è vuota e viene segnalata come `seed_condition=below_seed_level`, con nota sulla copertura; non si dichiara assenza di interessamento della costa. L’altra vista rimane disponibile.

Un errore della sola esportazione GIS viene segnalato accanto alla mappa e nei log, senza nascondere immagini di previsione valide. Le dipendenze GIS sono incluse in `forecast_service/requirements.txt`; non occorrono account aggiuntivi. Il notebook viene mantenuto autosufficiente, ma l’archivio giornaliero viene prodotto dal servizio di previsione, non dal setup Colab.

## Quote delle strutture campionate dal DEM

Il notebook accetta un GeoJSON facoltativo di punti con campo `struttura`. Per ogni settore costiero e tipo di struttura campiona il DEM originale e propone la media delle quote valide. Senza suddivisione, il raggruppamento riguarda la spiaggia intera. Minimo, massimo, numero di punti e osservazioni escluse restano nella diagnostica. Il modulo permette di modificare la proposta, conservando l’origine della quota e la media iniziale nel pacchetto.

I punti devono identificare la quota da confrontare con l’acqua (per esempio terreno o accesso): quote di tetti lette da un DSM non equivalgono alle quote del terreno. La media non è la quota del punto più basso, né una probabilità di interessamento. Vedi `notebooks/README.md` per formato, attività stagionale, casi ambigui e controllo delle correzioni verticali.
