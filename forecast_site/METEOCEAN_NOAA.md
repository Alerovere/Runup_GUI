# MeteOcean + sola marea NOAA: configurazione del portale

La configurazione attiva sostituisce le onde Copernicus con i CSV Wavewatch MeteOcean e combina **marea astronomica NOAA HTP + surge MeteOcean**. Il motore empirico `src/runup_models.py`, le pendenze, le soglie, la climatologia ERA5, i filtri e le citazioni sono mantenuti. Streamlit e le sue pagine non sono modificati. Le prove degli ensemble ECMWF/NOAA restano separate dal bollettino.

## Contributi e riferimenti

- Onde: `Hs` in metri, `Tp` in secondi, `Dirp` nella convenzione nautica WW3 di provenienza (0° Nord, 90° Est). Sono orari UTC, confermati dal fornitore tramite l’utente. Dirp è la direzione al picco; non è identica alla direzione media usata da Copernicus/ERA5. Il confronto climatologico per settore mantiene questo limite.
- Surge: CSV senza intestazione, primo dato conservato, passo 30 minuti; valori in metri e anomalia rispetto al livello medio, senza marea, confermati dal fornitore tramite l’utente. Ai tempi orari delle onde si usano i corrispondenti campioni nativi, senza ricampionamento o riempimento di buchi.
- Marea: NOAA STOFS-2D-Global **HTP**, non CWL (livello completo) o SWL (surge NOAA). Il codice verifica anche l’assenza di forzanti meteorologiche nel file (`nws=0`).
- Livello marino utilizzato: `tide_m + surge_m`. TWL: questo livello più il runup dei modelli empirici. Non si sommano due surge, non si sottrae la media del periodo previsto e non si trasferisce la media SSH Copernicus 2025 ai nuovi dati.
- NOAA documenta i campi NetCDF in metri rispetto a MSL; il nome standard NetCDF resta quello generico “above geoid”. Il raccordo con le quote dei rilievi locali resta provvisorio, come dichiarato nel sito. Non si tratta di una calibrazione su mariegrafi locali.

Configurazioni: `config/meteocean.json` contiene i quattro URL; `config/noaa_tide_points.json` contiene gli indici dei due nodi marini e la provenienza della selezione. `config/locations.json` mantiene anche le impostazioni Copernicus, oltre a `forecast_provider=meteocean`.

## Accesso NOAA leggero e controllo della griglia

STOFS ha copertura globale. I file `.points.htp.nc` non hanno stazioni adeguatamente vicine alle due località: non si sostituisce Venezia con Trieste o Borghetto con una stazione distante. Si leggono i campi nativi `.fields.htp.nc` tramite **HTTP Range**.

Il setup una tantum del 9 novembre 2026 ha letto circa 205 MB di sole coordinate, evitando il campo da circa 19,6 GB. Sono stati selezionati nodi marini a profondità positiva:

| Località | Latitudine / longitudine del nodo | Distanza dal punto configurato |
|---|---|---:|
| Borghetto | 44,07551722 N / 8,31697333 E | 1,15 km |
| Venezia Lido | 45,36509094 N / 12,49049399 E | 1,84 km |

Questi nodi non coincidono necessariamente con le celle dei CSV MeteOcean, che non espongono coordinate nel file. Il dato rappresenta un punto del modello, non una misura alla battigia o una previsione dentro la laguna di Venezia.

Gli indici salvati bastano per i download successivi. A ogni corsa si controllano versione/griglia, numero dei nodi e coordinate effettive degli indici. Una griglia diversa interrompe il bollettino e richiede di rifare il setup; non si continua usando indici sbagliati.

La prova reale completa del 9 novembre ha estratto marea per 120 ore e due località leggendo **19.312 byte di dati NOAA** con 367 piccole richieste Range, oltre al traffico di intestazioni HTTP/TLS. Il trasferimento è piccolo, ma ci sono molte richieste: quattro letture in parallelo sul bucket pubblico S3. Non si usano i filtri NOMADS per questa operazione. Se il server ignora Range, il client interrompe la risposta prima di leggere il campo globale. Budget locale: 1 MB di payload e 450 richieste per acquisizione.

## Aggiornamento giornaliero dopo l’uscita delle 06:20 UTC

Il fornitore conferma che tutti gli orari dei CSV sono **UTC** e che i dati si aggiornano ogni giorno alle **06:20 UTC**. Il workflow `Previsioni locali` è programmato alle **06:40 UTC**, con 20 minuti di margine: 07:40 italiane in inverno e 08:40 in estate. GitHub può ritardare l’avvio. Pubblicazione dei dati, acquisizione del sito e corsa del modello sono informazioni distinte; le 06:20 non sono usate come data di inizializzazione del modello.

Il bollettino MeteOcean copre una finestra di **96 ore dall’ora UTC di avvio dell’elaborazione**, arrotondata all’ora: nel programma corrente dalle 06 UTC fino alle 06 UTC di quattro giorni dopo. Le ore già trascorse non sono ripresentate come future; non si promettono 96 nuove ore a ogni visita e non si inventano dati oltre la fine dei CSV. Si conservano anche le ore aggiuntive disponibili fino al limite di download (120 ore).

Dopo l’uscita delle 06:20 UTC si verifica comunque la copertura effettiva: i CSV sono accettati solo se coprono tutte le 96 ore della finestra richiesta. Un vecchio flusso che non arriva alla fine dei quattro giorni viene rifiutato. Si rifiutano buchi, duplicati, giorni iniziali diversi fra onde/surge e fra località, e valori non finiti. I CSV non espongono la data della corsa: l’inizio della serie e `Last-Modified` non vengono spacciati per data di emissione.

Per NOAA si usa una corsa già disponibile, con almeno un’ora di margine nominale di pubblicazione e copertura effettiva verificata. La corsa preferita non è successiva all’inizio della finestra, così include anche le ore iniziali necessarie alla ricostruzione giornaliera. Un file 404 consente di cercare una delle precedenti tre corse; altri errori non vengono mascherati.

L’avviso di aggiornamento in ritardo scatta dopo **30 ore**, coerentemente con la cadenza giornaliera. I bollettini precedenti senza questo campo mantengono il comportamento storico. Un download fallito impedisce la pubblicazione: resta online il precedente artefatto. Non c’è un passaggio automatico e silenzioso fra fornitori.

## Uso e ripristino Copernicus

Non servono nuovi account, token o secrets per MeteOcean e NOAA. Per generare i dati in una cartella locale:

```sh
python -B scripts/update_forecasts.py --provider meteocean --output /tmp/ondeariva-meteocean/data
```

Per GitHub Pages: effettuare commit/push con GitHub Desktop, poi **Actions → Previsioni locali → Run workflow → meteocean**. La variabile repository `FORECAST_ENABLED=true` continua ad abilitare il programma giornaliero. Verificare il sito dopo il workflow: il push da solo non pubblica i dati.

Ripristino manuale: **Run workflow → copernicus**, usando i secrets già configurati. Per mantenere Copernicus anche nelle esecuzioni programmate, impostare la variabile repository **`FORECAST_PROVIDER=copernicus`**. Per tornare alla nuova configurazione, impostare **`FORECAST_PROVIDER=meteocean`**, oppure rimuovere quella variabile (il default è MeteOcean).

Da terminale:

```sh
python -B scripts/update_forecasts.py --provider copernicus --output /tmp/ondeariva-copernicus/data
```

Il codice originale di download Copernicus, il riferimento SSH fisso e le citazioni restano disponibili. Non occorre riconfigurare le pendenze o riscaricare ERA5.

## Fonte e riconoscimenti

Il logo orizzontale ufficiale MeteOcean è conservato in `forecast_site/assets/meteocean-unige.svg`, con provenienza in `assets/README.md`. Ringraziamento e collegamento al gruppo sono presenti in homepage/località, metodo e disclaimer. Il riconoscimento UE/ERC rimane distinto e invariato.

- [MeteOcean – DICCA, Università di Genova](https://meteocean.science/)
- [NOAA STOFS: HTP, SWL, CWL e formati dei file](https://noaa-gestofs-pds.s3.amazonaws.com/README.html)
- [Accesso e condizioni NOAA NODD](https://registry.opendata.aws/noaa-gestofs/)
- [Dataset NOAA e CC0](https://repository.library.noaa.gov/view/noaa/71554)

L’accesso NOAA è pubblico, senza account, e i dati sono riutilizzabili anche commercialmente secondo le condizioni del fornitore. Le condizioni di riutilizzo dei CSV MeteOcean vanno concordate con il fornitore: l’accessibilità dell’URL non equivale a una licenza generale.
