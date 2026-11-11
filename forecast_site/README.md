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

Il notebook di setup permette di assegnare i transetti a settori di spiaggia e aggiungere cartografia con crediti del rilievo. Senza queste opzioni i siti esistenti restano rappresentati come prima. Vedi [SETTORI_E_MAPPE.md](SETTORI_E_MAPPE.md) per configurazione, raccordo verticale, importazione e significato degli inviluppi statici P75/P95 nelle 96 ore.
