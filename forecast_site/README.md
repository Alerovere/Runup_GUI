# Portale delle previsioni locali

Sito autonomo in italiano per Venezia e Borghetto Santo Spirito, ospitabile su GitHub Pages nella stessa repository dell’app Streamlit. Il portale legge un bollettino JSON precalcolato. L’app esistente continua a usare `app.py` e `pages/`.

## Assunzioni della prima versione

- Onde reali: solo Copernicus Marine, dataset `cmems_mod_med_wav_anfc_4.2km_PT1H-i`, variabili VHM0, VTPK e VMDR. Si richiedono 120 ore contigue per visualizzare le successive 96 ore anche fra due aggiornamenti.
- Pendenze illustrative: 0,03, 0,05 e 0,07 per entrambe le località. Punti offshore e tratto del Lido di Venezia sono provvisori. Tutte le direzioni sono incluse e non si applica una trasformazione delle onde verso riva.
- TWL = runup + livello marino Copernicus. La variabile `zos` del prodotto fisico mediterraneo comprende la marea del modello; si usa `zos - mdt + datum_offset_m`, dove `mdt` è la superficie media fissa della stessa cella nel dataset statico. Non si rimuove la media dei giorni di previsione. Il raccordo con il livello medio mare locale resta provvisorio; una `mean_reference_m` locale validata può sostituire MDT. Il livello non viene separato artificialmente in marea e sovralzo e non si aggiunge un’altra previsione di marea sopra `zos`.
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
3. In **Settings → Secrets and variables → Actions → Secrets**, creare `COPERNICUSMARINE_USERNAME` e `COPERNICUSMARINE_PASSWORD`. Usare i valori del proprio account Copernicus Marine. I secrets Streamlit non vengono copiati in GitHub.
4. In **Actions → Previsioni locali → Run workflow**, scegliere `demo` per una prima verifica della pubblicazione e aprire l’URL dell’ambiente `github-pages`. Il workflow deve essere nel ramo predefinito per mostrare il pulsante. La modalità `demo` pubblica il sito dimostrativo e sostituisce il precedente portale Pages, se esistente: usarla solo per il setup.
5. Ripetere **Run workflow** scegliendo `copernicus`. Controllare che tutte le fasi siano verdi, che il sito riporti “Dati Copernicus Marine” e che le due località abbiano copertura futura. Il backend registra la cella effettivamente estratta. Non inventa la data del ciclo: mostra la data di elaborazione e quella del download.
6. In **Settings → Secrets and variables → Actions → Variables**, aggiungere `FORECAST_ENABLED` con valore `true`. Questo abilita le esecuzioni programmate alle **06:37 e 20:37 UTC**: 07:37/21:37 italiane in inverno e 08:37/22:37 in estate. Gli orari sono configurabili nel workflow e includono margine rispetto alle finestre nominali Copernicus delle 06:00 e 20:00 UTC.
7. Attivare nelle preferenze GitHub le notifiche dei workflow falliti. Per sospendere gli aggiornamenti programmati, impostare `FORECAST_ENABLED=false`; l’esecuzione manuale resta disponibile.

Per una repository pubblica con GitHub Free, Pages e i runner standard pubblici di Actions sono disponibili senza canone. Le repository private dipendono dal piano. Gli avvii programmati possono ritardare o essere saltati; i workflow pubblici possono essere disattivati dopo 60 giorni senza attività. Un dato più vecchio di 18 ore viene segnalato nel portale, e le ore scadute non vengono presentate come future.

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
