# Settori di spiaggia e cartografia facoltativa

L’app Streamlit resta separata. Queste opzioni riguardano il notebook di setup e il portale statico. Non occorrono nuovi account o servizi web.

## 1. Settori nel notebook Colab

Aprire la versione aggiornata di `notebooks/Definisci_siti_studio.ipynb`, caricare i profili e verificare le pendenze come prima. La sezione **5A** contiene `SETTORI_SPIAGGIA`:

```python
SETTORI_SPIAGGIA = {}
```

Lasciandolo vuoto si mantiene la spiaggia intera. Per suddividere un sito, aggiungere una voce per ogni settore con `name` e `transect_ids`. Gli identificativi sono quelli della tabella dei transetti inclusi, trattati come stringhe. Ogni transetto incluso deve essere assegnato una volta: duplicati, ID sconosciuti e transetti dimenticati impediscono l’esportazione. Non si deducono settori dal loro ordine numerico.

```python
# Esempio di formato per un sito con quattro transetti: non è una suddivisione reale di Borghetto.
SETTORI_SPIAGGIA = {
    "ponente": {"name": "Ponente", "transect_ids": ["1", "2"]},
    "levante": {"name": "Levante", "transect_ids": ["3", "4"],
                "thresholds": soglie_settore([0.65, 0.85, 1.05, 1.35])},
}
```

Ogni settore usa le pendenze misurate dei propri transetti, deduplicando valori identici. Non applica il campionamento sintetico minimo–massimo del riepilogo della spiaggia. Può avere `wave_exposure`, `summer_season`, `thresholds` e `notes` propri; in loro assenza eredita quelli del sito. Non cambiano le formule né le citazioni. Il filtro ±3σ e i percentili sono calcolati per ora e settore. I percentili non sono probabilità calibrate.

I download di onde, surge e marea rimangono uno per località; ERA5 resta condiviso. Il portale offre il selettore del tratto, un riepilogo dell’intera spiaggia e un CSV per settore. Località senza settori e pacchetti precedenti restano validi. Lo script locale `scripts/setup_location.py` accetta anche `--sectors-json` per una nuova bozza.

## 2. DEM e ortofotomosaico nel notebook

La sezione **5B** contiene `CARTOGRAFIE = []`: vuoto significa nessuna mappa. Una voce può riguardare `whole` (spiaggia intera) o l’ID di un settore, anche soltanto uno dei settori configurati.

In alternativa ai profili CSV, il notebook può estrarre i profili dalle linee GeoJSON e dal DEM originale dell’intera area, e assegnarli ai settori caricati come poligoni GeoJSON. Vedi anche `notebooks/README.md`.

Occorrono:

- DEM GeoTIFF a una banda, georeferenziato, con quote in metri, anche dell’intera area. Attivare `clip_to_polygon` oppure il flusso automatico dalle aree: si prepara un dominio locale con margine prima del calcolo. Il limite di 0,2° per asse si applica al dominio preparato, non al raster sorgente.
- Ortofotomosaico GeoTIFF facoltativo, georeferenziato a 8 bit, grigio/RGB/RGBA. L’ortofoto è lo sfondo, non contiene le quote per il calcolo.
- Poligono GeoJSON del settore e punti di avvio verso mare, in WGS84 `[longitudine, latitudine]`. Nel flusso automatico i punti sono ricavati dai profili orientati; si possono correggere nell’anteprima. I punti devono ricadere su celle valide e sufficientemente basse del DEM. NoData rimane una barriera; il mare non viene inventato.
- Crediti del DEM e dell’ortofoto, data del rilievo, licenza di pubblicazione e riferimento verticale. Se diversi, indicare entrambi gli autori/date nel testo dei crediti.
- Raccordo verificato tra zero del DEM e zero del TWL. `dem_offset_m` viene **sommato** al raster una volta sola; non è automaticamente la correzione dei profili. Confermare `vertical_alignment_confirmed=True` solo dopo questa verifica.

Il notebook mostra un esempio completo commentato di `CARTOGRAFIE`. I file possono essere caricati dal computer oppure letti da Drive. Installa Rasterio soltanto nel setup; la produzione usa le griglie già preparate e NumPy.

Gli originali non entrano nel pacchetto: si esportano `grid.npz` e, se presente, `orthophoto.png`, allineati in EPSG:3857 (la proiezione della mappa web, con estensione riportata in WGS84). La griglia DEM preparata ha normalmente fino a 768 pixel per asse, massimo 1024. L’ortofoto può usare un passo indipendente in metri/pixel, fino a 4096 pixel per asse e 12 MiB: non viene ridotta silenziosamente se il passo richiesto produce un file troppo grande. Questa riduzione e il ricampionamento al vicino più prossimo possono alterare muri e varchi: controllare il risultato; non sono sostituti di un rilievo adeguato. Preferire un terreno depurato dagli artefatti, con rappresentazione verificata delle opere: un DSM con vegetazione o edifici non equivale automaticamente a un DTM idraulicamente corretto.

## 3. Esportazione, importazione e pubblicazione

Eseguire tutte le celle fino all’esportazione del pacchetto ZIP. Conservare gli originali e il progetto di rilievo in `notebooks/dati originali/`, cartella locale esclusa da Git tramite `.gitignore`. Il push contiene soltanto i derivati scelti e la relativa documentazione, non i GeoTIFF completi. Per aggiornare una località già presente:

```sh
python scripts/import_site_package.py /percorso/sito_studio.zip --replace
```

L’importatore verifica configurazione, allegati, griglia e crediti prima di scrivere. I file preparati finiscono in `config/study_sites/<località>/cartography/<unità>/`. Il pacchetto ha un limite complessivo di 100 MiB non compressi. Il riferimento Copernicus esistente, quando applicabile e compatibile, continua a essere conservato come prima.

Controllare le modifiche, fare commit e push e avviare **Previsioni locali → meteocean**. Il workflow già esistente genera le mappe in `_site/data/maps/` insieme al nuovo bollettino. Il successivo aggiornamento automatico le rigenera. Nessuna modifica a credenziali o programmazione è necessaria.

## 4. Cosa rappresenta la mappa

Per ogni ora si calcola TWL con i contributi contemporanei di runup, marea e surge. Dopo il filtro ±3σ si estraggono P75 e P95, poi la quota maggiore nelle **96 ore fisse dell’elaborazione** per ciascun percentile. Non si usa il massimo dei singoli modelli e non si sommano massimi avvenuti in ore diverse. La mappa dichiara periodo e ora di ciascun picco; quel periodo non scorre con l’orologio del browser.

Si propaga sul DEM un livello uniforme dalle celle di avvio verso mare, attraverso celle più basse della quota, con otto vicini. Le depressioni isolate non vengono riempite. La propagazione usa tutto il dominio DEM preparato con margine; il poligono del settore ritaglia soltanto l’output, evitando che il confine del settore diventi una barriera artificiale. Non viene simulata l’interazione idraulica fra settori con quote diverse.

È un’**estensione statica potenziale**, non una simulazione dinamica: il runup è intermittente. Non fornisce durata, profondità effettiva, velocità, portate, infiltrazione o sormonto delle opere. Un bacino connesso dopo il superamento di una cresta può essere sovrastimato dal riempimento statico. Le ore con onde non frontali o direzione sconosciuta sono indicate; non si applica una trasformazione delle onde verso riva.

Dati mancanti o un errore della cartografia rendono indisponibile la sola mappa, con motivazione visibile, senza impedire i grafici. Nessuna mappa viene prodotta con copertura inferiore alle 96 ore o statistiche obsolete. Rimangono tutte le avvertenze sperimentali e le condizioni d’uso del portale.
