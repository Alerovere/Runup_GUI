# Portale delle previsioni locali

Sito autonomo in italiano per Venezia e Borghetto Santo Spirito, ospitabile su GitHub Pages nella stessa repository dell’app Streamlit. Il portale legge un bollettino JSON precalcolato. L’app esistente continua a usare `app.py` e `pages/`.

## Assunzioni della prima versione

- Configurazione predefinita: onde e surge MeteOcean, marea astronomica NOAA STOFS-2D-Global HTP. Bollettino giornaliero su quattro giorni, con inizio all’ora UTC di elaborazione e fine dopo 96 ore. Le ore già trascorse vengono nascoste; la finestra non è estesa artificialmente. Si conservano fino a 120 ore disponibili nei CSV. L’alternativa Copernicus mantiene la finestra scorrevole precedente. Dettagli e ripristino in [METEOCEAN_NOAA.md](METEOCEAN_NOAA.md).
- Pendenze: 19 valori derivati dai transetti per Borghetto; 0,03, 0,05 e 0,07 ancora illustrativi per Venezia. Punti offshore e tratto del Lido di Venezia sono provvisori. Tutte le direzioni sono incluse e non si applica una trasformazione delle onde verso riva.
- Nella configurazione attiva: TWL = runup da onde MeteOcean + surge MeteOcean + sola marea NOAA HTP. La media storica Copernicus non viene applicata a questi dati; il raccordo locale delle quote resta provvisorio. Nell’alternativa Copernicus: TWL = runup + livello marino Copernicus. La variabile `zos` del prodotto fisico mediterraneo comprende la marea del modello; si usa `zos - mean_reference_m + datum_offset_m`. Per Borghetto il riferimento fisso è la media oraria Copernicus del 2025 nella stessa cella, circa −0,4032 m, documentata in `sea_level_reference`. Per siti non ancora preparati resta il riferimento MDT, esplicitamente provvisorio. Non si rimuove la media dei giorni di previsione. Il raccordo con il livello medio mare locale resta provvisorio; La media storica del modello non certifica il livello medio mare misurato sulla spiaggia. Anno, cella e versione del prodotto vengono verificati prima del calcolo. Il livello non viene separato artificialmente in marea e sovralzo e non si aggiunge un’altra previsione di marea sopra `zos`.
- Le soglie 0,70 / 0,90 / 1,10 / 1,40 m sono esempi da validare. Per le prime due la stagione estiva è ancora da definire: il confronto viene mostrato come indicativo, con applicabilità sconosciuta.
- Il calcolo richiama `src/runup_models.py` senza modificarlo. Mantiene anche l’uscita swash del modello Passarella e l’associazione Power2019/Power2018 già presenti. Le uscite non rappresentano tutte una stessa statistica R₂. I risultati non finiti vengono esclusi e i modelli senza risultati sono elencati.
- Percentili e frazioni di superamento descrivono gli scenari modello × pendenza; non sono probabilità calibrate. Il numero di scenari validi può cambiare da un’ora all’altra.
- Modalità demo: onde sintetiche esplicitamente etichettate nel sito, nel JSON e nei CSV. Non sostituisce mai automaticamente un download fallito.

## File da configurare

`config/locations.json`: punti della mappa e offshore, eventuale punto distinto `sealevel_point`, elenco di pendenze, rugosità, correzione verticale `datum_offset_m`, riferimento fisso opzionale `mean_reference_m`, stagione estiva opzionale per località e file climatologico. Il livello marino viene scaricato dallo stesso account Copernicus già usato per le onde.

`config/impact_thresholds.json`: quote e descrizioni delle soglie per località. Per attivare il calendario estivo, compilare entrambi i campi `summer_season.start_month_day` e `end_month_day`, per esempio `"06-01"` e `"09-30"` solo se queste date sono appropriate al sito. Sono date locali italiane con estremi inclusi. Il calendario generale è usato come valore predefinito; `summer_season` nella configurazione di una località lo sostituisce per quella località.

## Anteprima locale

Dalla radice della repository, usare un ambiente Python separato. L’esempio usa Python 3.11, come il workflow:

```sh
python3.11 -m venv .venv-forecast
source .venv-forecast/bin/activate
python -m pip install -r forecast_service/requirements.txt
python -B -m unittest discover -s tests/forecast -v
python -B scripts/update_forecasts.py --demo
python -m http.server 8765 --directory forecast_site
```

Aprire http://localhost:8765. Le schede e le aree sulla mappa aprono le località; il parametro `?localita=venezia` permette un collegamento diretto. Leaflet, Plotly e i font usano CDN; la mappa usa le tessere OpenStreetMap. Serve una connessione per questi elementi. Le tabelle e i CSV rimangono utilizzabili se i grafici non si caricano.

Il file demo incluso è solo un esempio generato durante lo sviluppo: rigenerarlo prima dell’anteprima se risulta scaduto. Non pubblicare come previsione reale un bollettino demo.

## Setup su GitHub

1. Pubblicare i nuovi file nella stessa repository, dopo revisione e unione nel ramo predefinito. L’app Streamlit conserva il proprio avvio. Le aggiunte non cambiano le dipendenze del suo `requirements.txt`.
2. In **Settings → Pages → Build and deployment → Source**, scegliere **GitHub Actions**. Non occorre scegliere una cartella o creare un ramo dati. Il workflow pubblica solo `_site`, contenente HTML, CSS, JavaScript, JSON e CSV.
3. In **Settings → Secrets and variables → Actions → Secrets**, creare `COPERNICUSMARINE_USERNAME` e `COPERNICUSMARINE_PASSWORD`. Servono solo per riattivare l’alternativa Copernicus; MeteOcean e NOAA non richiedono account o token. I secrets Streamlit non vengono copiati in GitHub.
4. In **Actions → Previsioni locali → Run workflow**, scegliere `demo` per una prima verifica della pubblicazione e aprire l’URL dell’ambiente `github-pages`. Il workflow deve essere nel ramo predefinito per mostrare il pulsante. La modalità `demo` pubblica il sito dimostrativo e sostituisce il precedente portale Pages, se esistente: usarla solo per il setup.
5. Eseguire **Run workflow** scegliendo `meteocean` (predefinito), oppure `copernicus` per il ripristino. Controllare che tutte le fasi siano verdi, che il sito indichi MeteOcean e marea NOAA, oppure Copernicus quando selezionato e che le due località abbiano copertura futura. Il backend registra la cella effettivamente estratta. Il sito mostra la fine dell’elaborazione e la corsa del modello quando verificata; il download resta nei metadati tecnici.
6. In **Settings → Secrets and variables → Actions → Variables**, aggiungere `FORECAST_ENABLED` con valore `true`. Questo abilita una esecuzione al giorno alle **06:40 UTC**, dopo l’aggiornamento MeteOcean delle **06:20 UTC** confermato dal fornitore: 07:40 italiane in inverno, 08:40 in estate, con possibili ritardi di GitHub. La variabile opzionale `FORECAST_PROVIDER=copernicus` cambia il fornitore anche per le esecuzioni programmate; in assenza si usa `meteocean`. L’orario è quello del download, non della corsa del modello. Gli orari dei flussi sono UTC. Si verifica la copertura dei quattro giorni prima di pubblicare, rifiutando dati precedenti insufficienti.
7. Attivare nelle preferenze GitHub le notifiche dei workflow falliti. Per sospendere gli aggiornamenti programmati, impostare `FORECAST_ENABLED=false`; l’esecuzione manuale resta disponibile.

Per una repository pubblica con GitHub Free, Pages e i runner standard pubblici di Actions sono disponibili senza canone. Le repository private dipendono dal piano. Gli avvii programmati possono ritardare o essere saltati; i workflow pubblici possono essere disattivati dopo 60 giorni senza attività. Un dato più vecchio di 30 ore viene segnalato nel portale, e le ore scadute non vengono presentate come future.

Un download fallito viene tentato fino a tre volte. Si pubblica solo quando entrambe le località sono complete e i test passano; altrimenti il sito precedente resta online. I risultati reali vengono pubblicati come artifact Pages, senza commit automatici nella repository. Un’interruzione prolungata può lasciare meno di 96 ore disponibili: il sito segnala la copertura parziale.

## Controlli

```sh
python -B -m unittest discover -s tests/forecast -v
node --check forecast_site/app.js
```

I controlli coprono confronto con il wrapper scientifico esistente, TWL con offset, superamento strettamente maggiore della soglia, valori mancanti, calendario locale, etichettatura demo, copertura Copernicus e mancata pubblicazione parziale. La chiamata Copernicus nei test è simulata; l’accesso reale va verificato con il primo workflow `copernicus`.

## Documentazione dei servizi

- [Pubblicazione Pages tramite Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Secrets GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [Workflow programmati e relativi limiti](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Prodotto onde mediterraneo Copernicus](https://data.marine.copernicus.eu/product/MEDSEA_ANALYSISFORECAST_WAV_006_017/description)

## Preparazione delle località e climatologia ERA5

La [guida al setup delle località](SETUP_LOCALITA.md) descrive il wizard, i transetti, il download storico ERA5 con cache e il riuso dei CSV della precedente app. Il download ERA5 è separato dai workflow giornalieri e non richiede un secret CDS nel sito pubblico.

## Esposizione e tempi di ritorno settoriali

Il notebook consente di definire i settori di provenienza ai quali la spiaggia è esposta: il portale usa queste informazioni per avvertenze, senza correggere o azzerare i calcoli. Separatamente, il setup ERA5 può preparare una Gumbel dei massimi annuali per ogni settore statistico di provenienza, con banda bootstrap al 95%. Il sito confronta il picco Hs delle 96 ore con il settore della direzione in quell’ora e consente di scegliere i picchi degli altri settori presenti. Il tempo di ritorno riguarda le onde al largo, non gli allagamenti. Un riferimento senza direzioni continua a supportare i percentili ma lascia il confronto degli estremi esplicitamente non disponibile. Vedere `SETUP_LOCALITA.md` e `notebooks/README.md` per preparazione, requisiti e limiti scientifici.

## Date del bollettino e uscita del modello

Con MeteOcean la riga iniziale indica elaborazione, fornitori e prossima acquisizione giornaliera; non inventa una corsa non esposta dai CSV. Nell’alternativa Copernicus distingue fine dell’elaborazione, riferimento del ciclo delle onde (solo se esplicito e coerente nei metadati) e prossima pubblicazione nominale Copernicus. Il prodotto Med-WAV indica finestre nominali alle 06:00 e 20:00 UTC; il sito le converte in Europe/Rome e non le confonde con l’orario del workflow. La dicitura “prevista” non certifica che il nuovo ciclo sia già disponibile.

Il dataset continuo ARCO può conservare `bulletin_date=2023-11-01` e `bulletin_type=analysis`, riferiti all’archivio: questi attributi non sono usati come data del ciclo corrente. Se manca un riferimento esplicito attendibile, il backend legge i file NetCDF originali dello stesso prodotto, ricavati dal catalogo Copernicus. Conferma `bulletin_date` (data e ora UTC, coerenti con il nome del file) solo quando Hs, Tp e direzione di tutte le ore scaricate coincidono con la stessa corsa, nella stessa cella. Le letture HTTP parziali usano `If-Match` per evitare cambi di versione durante il controllo; il bollettino conserva gli URL, le firme ETag e il numero di ore verificate. Il controllo aggiunge tempo al workflow, con un limite di quattro minuti fra i file e timeout delle singole richieste. Se i file mancano, sono in aggiornamento o il controllo fallisce, il calcolo resta valido e il sito indica “Corsa del modello Copernicus non disponibile in questo bollettino”. La data di acquisizione non è mostrata al suo posto. La homepage usa un ciclo comune solo se confermato per tutte le località; per corse diverse rimanda alle singole pagine. Gli avvisi di dati scaduti o copertura incompleta restano presenti.

Fonte degli orari nominali: [manuale Copernicus del prodotto onde mediterraneo](https://documentation.marine.copernicus.eu/PUM/CMEMS-MED-PUM-006-017.pdf).


### Lettura della pagina della località

Le statistiche TWL usano `sigma_clip_3_population_v1`: un passaggio per località/ora su tutti i risultati modello × pendenza, μ e σ della popolazione (`ddof=0`), esclusione strettamente oltre μ±3σ. Valori sui limiti inclusi; con σ=0 si conserva tutto. Percentili e frazioni sono ricalcolati sui risultati conservati. I CSV mantengono ogni risultato grezzo e aggiungono `included_in_summary`; il JSON registra conteggi e parametri del filtro. Minimo/massimo restano soltanto come dati di compatibilità, senza uso nelle categorie o nella pagina TWL. Questo criterio statistico non assegna probabilità ai modelli.

Il riferimento resta `strutture_turistiche_fisse` (chioschi). Scala: bianco se P95≤quota, giallo se P75≤quota<P95, arancione se quota<P75. Media e massimo non classificano. Le ore non frontali non ricevono una categoria numerica: se costituiscono l’intero confronto valido il box è grigio. Nei periodi misti restano valutate tutte le ore frontali, anche se il picco Hs è non frontale. Direzioni mancanti non sono interpretate come riparo. Il grigio non esclude effetti di marea/sovralzo o onde trasformate verso riva.

Le finestre delle strutture richiedono P95 sopra quota e onde frontali, con campioni orari consecutivi e stagione applicabile (o esplicitamente indicativa). Percentuali basate sui risultati filtrati; non sono probabilità di allagamento. Un vecchio bollettino senza metadati del filtro richiede un aggiornamento: il sito non ne rietichetta le vecchie statistiche.

Onde, direzione e “Marea + Storm surge” condividono un asse temporale Plotly. Con MeteOcean il livello è la somma NOAA HTP + surge MeteOcean; le due componenti sono anche disegnate separatamente. Nell’alternativa Copernicus resta il segnale complessivo originale. Il raccordo Tp è solo visivo e non modifica valori orari o calcoli. Le linee ERA5 95°/99° percentile mantengono la frequenza storica 5/1 ore su 100; il filtro riguarda il confronto dei modelli di runup, non la climatologia.

`metodo.html` raccoglie spiegazioni, limiti, configurazioni e tutte le citazioni, con finanziamento e disclaimer. Il workflow include questa pagina nell’artefatto Pages. Per rigenerare i dati dimostrativi dopo una modifica delle statistiche: `python -B scripts/update_forecasts.py --demo --output forecast_site/data`.

## Prova isolata degli ensemble

Per verificare l’accesso anonimo a NOAA GEFS-Wave ed ECMWF ENS-WAM senza modificare il bollettino, vedere [PROVA_ENSEMBLE.md](PROVA_ENSEMBLE.md). Script e dipendenze sono separati dal workflow di pubblicazione.

Per la prova isolata delle 72 ore giornaliere, con tutti i 51 membri ECMWF via GribStream e NOAA diretto, vedere [PROVA_GIORNALIERA.md](PROVA_GIORNALIERA.md). Il documento distingue quota nominale ed effettiva e descrive il controllo ECMWF separato. Non modifica ancora il bollettino pubblico.

Configurazione corrente MeteOcean + sola marea NOAA e ripristino Copernicus: [METEOCEAN_NOAA.md](METEOCEAN_NOAA.md).

## Settori, DEM e ortofotomosaici (opzionali)

Il notebook di setup permette di assegnare i transetti a settori di spiaggia e aggiungere cartografia con crediti del rilievo. Senza queste opzioni i siti esistenti restano rappresentati come prima. Vedi [SETTORI_E_MAPPE.md](SETTORI_E_MAPPE.md) per configurazione, raccordo verticale, importazione e significato delle mappe della media e del limite superiore della fascia centrale nelle 96 ore, orari rappresentati e download GeoJSON/KMZ.


### Surge filtrato e curve (26 novembre 2026)

Con MeteOcean il TWL usa una media mobile **centrata di 6 ore**, pesata sul tempo dei campioni nativi ogni 30 minuti. La marea NOAA resta invariata. Ai bordi si riduce la finestra ai dati disponibili e si rinormalizza; non si estrapola né si coprono lacune. `config/meteocean.json: surge_smoothing_hours` controlla la finestra (0 disattiva il filtro; massimo 24 ore). Il filtro modifica TWL, confronti, categorie e mappe, senza modificare i modelli empirici o il campionamento delle pendenze. Copernicus resta disponibile e non riceve questo filtro.

I CSV dei calcoli mantengono `surge_raw_m`, `surge_m`, `surge_filter_support_hours` e `water_level_raw_m` (marea + surge originale). `data/<località>-surge-native.csv` conserva tutti i campioni nativi originali e filtrati ed è linkato sotto i grafici; `source.surge_processing` documenta metodo, finestra e bordi. I timestamp sono UTC. I file sorgenti sono identificati dai loro SHA-256 già presenti nei metadati.

PCHIP serve soltanto a disegnare curve temporali fra i campioni orari (punti ogni 10 minuti, distinti nel tooltip). Conserva i valori orari, non estrapola, non aggiunge estremi fra due campioni e non copre dati mancanti. Le direzioni restano marcatori orari senza interpolazione angolare. I bordi delle fasce restano ordinati: se PCHIP li incrocia, nell’intervallo si usa l’interpolazione lineare. Statistiche, riepiloghi e mappe non usano i punti interpolati. Nessuna nuova dipendenza.


### Infografiche social 4:5

Ogni nuova elaborazione genera una PNG **1080 × 1350** per settore, oppure per l’intera località se non ci sono settori. Il pulsante è accanto al CSV e usa `social_card` della selezione corrente. A sinistra mostra altezza significativa, periodo e provenienza delle onde; a destra un profilo schematico della spiaggia con strutture, quota media TWL, P95 e linea punteggiata al P99,5. Restano invariati i due valori principali, il riepilogo giornaliero, avvertenze e riconoscimenti UE/ERC. La mappa interattiva del sito rimane disponibile nella pagina locale.

L’immagine fotografa le **96 ore fisse dell’elaborazione**, non la finestra futura scorrevole del browser. Il profilo rappresenta l’ora con il TWL medio filtrato più alto fra le ore frontali nelle 96 ore: media, P95, P99,5 e strutture si riferiscono tutti a quell’ora. Il valore TWL alto nel riquadro superiore resta il massimo temporale del P95, con il suo orario. I picchi possono quindi avere orari diversi. Il profilo generalizzato non è un transetto misurato e non rappresenta distanze orizzontali di inondazione. La provenienza delle onde mantiene i campioni orari, senza interpolazione angolare; le curve di Hs e Tp usano PCHIP solo per il disegno.

I giorni mostrano separatamente le percentuali per chioschi e passeggiata (quote effettive del settore), con gli stessi colori ed esclusioni per esposizione, stagione e dati mancanti. Sono massimi orari delle frazioni di risultati, non frequenze temporali né probabilità. Le altre strutture configurate restano nel bollettino e nel CSV.

Il file timestampato è in `data/social/` e conserva nel campo testuale PNG `Onde-a-riva` anche i tempi, l’identificativo del settore e le statistiche rappresentate. Il portale offre solo l’infografica della stessa elaborazione del bollettino. L’immagine contiene l’avvertenza sperimentale, le fonti e il riconoscimento MARINA/UE/ERC. I font DejaVu sono inclusi con la relativa licenza. La generazione è offline e non legge ortofoto, DEM o mappe: un eventuale errore della sola infografica non sopprime il bollettino. Per i vecchi bollettini occorre una nuova elaborazione prima di avere il pulsante disponibile.


### Canale Telegram privato di prova — Borghetto

Dopo il job `deploy` riuscito, `Previsioni locali` invia una foto con didascalia e pulsanti per ciascun settore di **Borghetto Santo Spirito**, oppure una per l’intera località se non è suddivisa. L’invio giornaliero comprende tutte le categorie, incluse le giornate tranquille o con onde non frontali. Nessun messaggio per Venezia, demo o esecuzioni su rami diversi dal ramo predefinito. Il contenuto è sperimentale e conserva l’avvertenza nell’immagine e nella didascalia, con link alla pagina locale e alle condizioni d’uso. I calcoli scientifici non vengono rieseguiti né modificati.

Configurazione: nei **Repository secrets** impostare `TELEGRAM_BOT_TOKEN` (BotFather) e `TELEGRAM_CHAT_ID` (ID numerico del canale, incluso il meno iniziale). Il bot deve essere amministratore del canale privato con il permesso di pubblicare messaggi. In presenza dei due secret il job è attivo; la **Repository variable** facoltativa `TELEGRAM_ENABLED=false` sospende solo Telegram. Non inserire token nel codice, negli URL del browser, nei log o nei file del repository. Non occorrono server aggiuntivi, webhook o polling continuo: gli invii seguono l’elaborazione giornaliera programmata alle **06:40 UTC**, con i possibili ritardi di GitHub Actions.

Il job riceve le stesse PNG dell’elaborazione pubblicata tramite l’artifact `telegram-borghetto-bulletin` (3 giorni). Prima di inviare verifica tutte le 96 ore, filtro dei risultati, validità dei file e corrispondenza del periodo/ciclo; rifiuta elaborazioni più vecchie di 6 ore. Le date delle didascalie sono italiane (CET/CEST). Le immagini inviate come foto possono essere ricompresse da Telegram; sul sito è disponibile la PNG originale.

Il registro `telegram-borghetto-state-v1` (90 giorni, esterno a Pages) conserva ricevute per giorno **UTC**, canale e settore; il canale è identificato con un hash e il token non viene salvato. Il job ripristina il registro più recente dello stesso workflow, repository e ramo predefinito. Una nuova elaborazione o un nuovo tentativo nella stessa giornata salta i settori già inviati, completando quelli rimasti. Per un altro canale la registrazione è distinta. Se non si riesce a leggere un registro esistente, l’invio viene sospeso anziché azzerare lo storico. Le ricevute interne più vecchie di 30 giorni vengono eliminate.

Il trasporto registra `pending` prima di ciascuna richiesta e `sent` dopo la conferma. Un rifiuto esplicito di Telegram permette un successivo tentativo dopo la correzione; i soli errori 429 vengono ritentati entro un limite breve. In caso di timeout o conferma incerta il settore rimane `pending`: **controllare il canale prima di ritentare**. La Bot API non offre una chiave di idempotenza, quindi non è possibile garantire l’invio esattamente una volta se il runner termina prima di salvare/caricare la ricevuta, o se gli artifact vengono eliminati. Le cancellazioni del registro possono causare duplicati. Un errore Telegram lascia il sito già pubblicato e rende visibile il problema nel job dedicato.

Per il primo test: commit e push delle modifiche, quindi **Actions → Previsioni locali → Run workflow**, ramo predefinito, modalità **meteocean**. Dopo `build` e `deploy` controllare il job **Bollettino Telegram Borghetto** e le tre immagini nel canale. Ripetere l’esecuzione nello stesso giorno non reinvia i settori confermati. Per una verifica locale senza rete e senza token: `python -B scripts/send_telegram_bulletin.py --data /percorso/dati-generati`; l’invio reale richiede esplicitamente `--send`.

Riferimenti: [Telegram Bot API — sendPhoto](https://core.telegram.org/bots/api#sendphoto), [artifact GitHub Actions](https://docs.github.com/en/rest/actions/artifacts), [GitHub CLI](https://cli.github.com/manual/gh_api).


### Lettura per giorno e per settore

La pagina mostra inizialmente soltanto le ore ancora future del bollettino. I pulsanti giornalieri selezionano invece l’intera data italiana, comprese eventuali ore trascorse, e aggiornano insieme sintesi, valori, grafici e mappa. Una previsione di 96 ore può attraversare cinque date: gli estremi sono indicati come giornate parziali. I parametri URL `settore`, `giorno=AAAA-MM-GG` e `stima` conservano la selezione nei collegamenti.

I colori mantengono il confronto con P75/P95 dopo il filtro di 3 sigma. Le percentuali contano risultati modello × pendenza sopra quota nelle ore valutabili: non sono probabilità di allagamento o percentuali di superficie. Bianco può comprendere superamenti isolati; grigio non equivale a condizioni sicure. La guida illustrata e il modulo di riscontro sono nella pagina Dati e metodo. Le risposte si scaricano localmente in TXT: nessuna raccolta automatica.

La PNG e Telegram fotografano le 96 ore dell’elaborazione, mentre il pulsante Telegram apre l’ultima elaborazione disponibile. Il bollettino include una sintesi per struttura e, dal secondo invio con il nuovo registro, la variazione della fascia rispetto al bollettino precedente; i periodi differiscono. Il registro salva solo la fascia necessaria al confronto, fuori da Pages, senza credenziali. Invio, protezione dai duplicati e permessi del bot restano invariati.

Dopo un aggiornamento del codice fare commit e push, poi avviare **Previsioni locali → Run workflow** sul branch aggiornato. Le mappe giornaliere vengono generate da questa nuova esecuzione. “Re-run jobs” su una vecchia esecuzione usa il suo vecchio commit. Per verificare localmente: `python -B -m unittest discover -s tests/forecast -v` e `node --test tests/forecast/*.cjs`.


### Primo riquadro: profilo generalizzato della spiaggia

Nel sito il profilo usa l’ora di maggiore media TWL fra le ore frontali visualizzate (finestra futura oppure intera data selezionata). Le percentuali delle strutture accanto al profilo sono quelle della **stessa ora**, e possono quindi differire dai massimi nelle schede giornaliere. I colori del profilo si riferiscono a quell’ora e mantengono il confronto P75/P95; il P99,5 non determina categorie, soglie o mappe.

Il nuovo campo orario `twl_p995_m` viene calcolato direttamente dagli stessi risultati modello × pendenza conservati dopo il filtro μ±3σ; la percentuale sopra quota resta un conteggio diretto su tutti i risultati conservati, anche quelli oltre P99,5. I vecchi bollettini senza il nuovo campo mostrano esplicitamente che P99,5 non è disponibile, senza estrapolarlo da altri percentili. Serve una nuova elaborazione dopo commit e push per pubblicare il nuovo campo.

Il profilo e le posizioni orizzontali delle strutture sono schematici; solo le quote e i risultati provengono dai dati del settore. La scala verticale si adatta ai valori, mentre non viene stimata una distanza di risalita. Per le onde non frontali la grafica è grigia e il confronto percentuale non è valutabile; le strutture fuori stagione e i dati mancanti mantengono indicazioni distinte.


### Filtro direzionale per la rappresentazione costiera

Profilo, quota TWL di sintesi, infografica e mappe usano soltanto ore con onde nei settori di esposizione configurati (`wave_is_exposed is True`). Le onde offshore, i contributi di marea e surge e tutti i risultati originali restano invariati; non viene imposto un mare calmo o un runup nullo. Senza ore frontali valide il profilo e il TWL di sintesi non riportano quote, e le mappe non generano aree, linee o download. La ragione è esplicita, distinguendo direzione esterna da esposizione/direzione non verificata.

Il grafico TWL interrompe curve e fasce nelle ore fuori settore o con direzione non verificata. Non si interpola attraverso queste ore e non si modifica il calcolo originale nel CSV; non è una correzione fisica della propagazione verso riva. Nei periodi misti un massimo teorico più alto fuori settore non può determinare la quota rappresentata. Le statistiche per colore restano basate su P75/P95 filtrati e sulle ore frontali, come prima.

Le nuove mappe dichiarano `exposure_policy=frontal_hours_only_v1`, conteggi delle ore e metodo `connected_static_twl_filtered_mean_p75_frontal_v3`. Ogni giorno senza ore idonee ha uno stato esplicito e download vuoti, senza ereditare quelli dell’intero bollettino. Il sito nasconde le vecchie mappe prive della nuova verifica fino alla rigenerazione dopo commit, push e nuova esecuzione della Action.

## Identità di ricerca e file condivisi

Tutte le pagine pubbliche indicano «Prototipo di ricerca — non validato per uso operativo» e rimandano alle avvertenze. Il gestore indicato resta il Prof. Alessio Rovere (alessio.rovere@unive.it). Le percentuali confrontano stime modello × pendenza con le quote rilevate: non attestano l’allagamento delle strutture.

Le nuove elaborazioni includono l’avvertenza nelle PNG (anche nei metadati) e nelle didascalie Telegram. Ogni riga dei CSV pubblici — località, settori e surge nativo — conserva tutti i campi originali e aggiunge `research_status`, `use_warning` e `disclaimer_url`. Nessun commento precede l’intestazione CSV, per mantenere la lettura con pandas e GIS. I valori numerici e il filtro dei calcoli restano invariati. I file e i messaggi già scaricati o inviati non vengono aggiornati retroattivamente; occorre una nuova elaborazione per generare i nuovi file.
