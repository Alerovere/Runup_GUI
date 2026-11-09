# Prova di download degli ensemble di onda

Questo script esegue un esperimento separato dal portale: scarica campioni NOAA GEFS-Wave ed ECMWF IFS ENS-WAM, ne verifica i metadati GRIB ed estrae i punti configurati per Borghetto Santo Spirito e Venezia. Non calcola runup o TWL, non aggiorna il bollettino, non modifica Streamlit e non viene eseguito dal workflow di pubblicazione.

## Account e ambiente

Gli endpoint usati sono pubblici e non richiedono account, password o API key. Le credenziali Copernicus e CDS/ERA5 non sono coinvolte. Restano applicabili licenze e attribuzioni dei fornitori.

Usare un ambiente separato; non aggiungere queste dipendenze all’app operativa. Dalla radice della repository:

```sh
python3 -m venv /tmp/runup-ensemble-venv
source /tmp/runup-ensemble-venv/bin/activate
python -m pip install -r forecast_service/ensemble-probe-requirements.txt
python scripts/probe_wave_ensembles.py --help
```

## Esecuzione incrementale

Scegliere una corsa 00 o 12 UTC già pubblicata da entrambi i servizi e ancora presente nei cataloghi. `--cycle` contiene data e ora UTC nel formato `YYYYMMDDHH`. Non viene dedotta dalla data di download; il GRIB deve confermarla. L’esempio storico della prova può non essere più disponibile negli archivi mobili: sostituire la corsa se necessario.

```sh
python scripts/probe_wave_ensembles.py \
  --cycle 2026110812 \
  --smoke \
  --output /tmp/runup-wave-probe
```

La modalità `--smoke` scarica controllo e primi due membri perturbati per ogni servizio, alle scadenze +24 e +96 ore. Senza `--smoke`, verifica tutti i 31 membri NOAA e i 50 ECMWF più il controllo, alle stesse due scadenze:

```sh
python scripts/probe_wave_ensembles.py \
  --cycle 2026110812 \
  --output /tmp/runup-wave-probe
```

Per verificare nuovamente i file già scaricati senza alcun accesso di rete, ripetere lo stesso comando con `--offline` e la stessa cartella di output. Un file mancante o alterato interrompe la verifica.

Altre opzioni: `--source noaa` o `--source ecmwf`, `--steps 24`, `--max-download-mb 200`, `--noaa-pause 2`. Mantenere gli output fuori da `forecast_site`. I file di report sono sovrascritti a ogni esecuzione nella stessa cartella; la cache è riutilizzata. Per conservare confronti fra esecuzioni, usare cartelle distinte.

La prova **non verifica una serie oraria continua di quattro giorni**. Due scadenze servono per controllare accesso, membri, variabili e celle marine e misurare il trasferimento. Prima dell’integrazione occorrerà verificare tutte le scadenze, gli aggiornamenti e la gestione delle indisponibilità.

## Risultati e limiti

- `points.csv`: una riga per fornitore, località, membro e scadenza; include corsa e validità UTC, coordinate richieste ed estratte, distanza e valori nativi.
- `report.json`: esito, errori, durata, byte trasferiti e richieste HTTP con stato, cache, ETag, SHA-256 e data di acquisizione.
- `cache/`: risposte e metadati per ripetere la lettura senza nuovi download. Non pubblicare questa cartella.

I byte contano i corpi HTTP letti da questa esecuzione, non l’overhead di rete; le risposte già in cache contano zero. La durata comprende download, attese ed estrazione. Le unità dei valori sono metri, secondi e gradi.

NOAA: tre parametri `HTSGW/PERPW/DIRPW`, un piccolo rettangolo che comprende entrambe le località, una richiesta per membro e scadenza. Richieste sequenziali con almeno due secondi fra gli avvii; nessuna concorrenza sul fornitore. Il limite può essere ulteriormente ridotto aumentando la pausa.

ECMWF: si leggono gli indici delle sole variabili `swh/pp1d/mwd` e si scaricano i messaggi GRIB selezionati con richieste HTTP multipart Range in gruppi di massimo dieci membri. L’ensemble usa il file `waef/ef`; il controllo usa `wave/fc`. Il download viene interrotto se il server ignora Range. Non è un ritaglio geografico lato server: i singoli campi trasferiti restano globali, quindi il carico per una serie completa può essere elevato anche per soli due siti.

Il tetto predefinito è 200 MB trasferiti per esecuzione. Non ci sono tentativi automatici illimitati né selezione silenziosa di una corsa diversa. Un errore produce `status: failed` e codice di uscita diverso da zero; l’altro fornitore viene comunque provato. La prova non è ancora un downloader operativo con ripartenza e recupero di serie parziali.

La cella viene scelta fra le quattro più vicine con Hs valido e una distanza massima di 40 km. La stessa cella deve fornire tutti e tre i parametri. Un valore mancante non viene interpretato come onda alta; non si interpola fra celle marine e terrestri. Le diverse maschere terra/mare possono far scegliere celle differenti ai due modelli, anche sulla stessa griglia nominale 0,25°.

La verifica delle direzioni tiene conto del `packingError` dichiarato dal GRIB: per esempio, 360,00026° con errore di codifica di 0,25° non è un valore impossibile. Il CSV conserva `direction_native_deg`, aggiunge `direction_wrapped_deg` nell’intervallo [0, 360) e registra `direction_packing_error_deg`. Questo riporto modulo 360 non modifica la convenzione di provenienza/propagazione del fornitore. Valori oltre la tolleranza documentata vengono rifiutati.

`PERPW/DIRPW` NOAA restano **periodo e direzione nativi**, senza assimilarli automaticamente a `VTPK/VMDR` Copernicus: definizioni e convenzioni devono essere verificate prima del runup e del confronto direzionale. ECMWF distingue `pp1d` (periodo di picco) da `mwp` (periodo medio); qui si richiede `pp1d`. Non sono ancora applicati filtri ±3σ, percentili, pesi fra fornitori o colori.

## Controlli offline

```sh
python -B -m unittest discover -s tests/forecast -p test_wave_download_probe.py -v
```

I test verificano risposta GRIB, messaggi troncati, indici incompleti/duplicati, corrispondenza dei range multipart, valori mancanti, tetto di trasferimento e blocco del download globale quando Range non è rispettato. Non eseguono richieste ai fornitori.

## Prima verifica reale — 9 novembre 2026

Corsa comune: **8 novembre 2026, ore 12 UTC**. Scadenze campionate: **+24 e +96 ore**. Esito: **entrambi i fornitori completi**, 328 righe puntuali con terne valide, senza interpolazione temporale né calcolo del runup.

| Fonte | Membri verificati per scadenza | Righe per le due località e scadenze | Risposte HTTP necessarie | Volume delle risposte, inclusa cache |
|---|---:|---:|---:|---:|
| NOAA GEFS-Wave | 31 | 124 | 62 | 51.677 byte, circa 0,052 MB |
| ECMWF ENS-WAM + controllo | 51 | 204 | 16 | 135.740.359 byte, circa 135,7 MB |

I due tentativi della verifica completa hanno richiesto complessivamente circa 11 minuti e 29 secondi, escludendo la precedente prova ridotta. Parte dei file era già in cache: durata e trasferimento di una ripetizione dipendono dalla cache e dalla connessione. Il primo tentativo aveva intercettato il valore angolare 360,00026° di un membro ECMWF; è stato conservato come dato originale e gestito con la precisione GRIB documentata, senza escludere il membro.

Celle marine estratte: Borghetto NOAA 44,00 N / 8,25 E (10,96 km dal punto richiesto); Borghetto ECMWF 44,00 N / 8,50 E (16,24 km). Venezia: 45,25 N / 12,50 E per entrambi (11,12 km). Non si tratta di misure direttamente sulla spiaggia.

**L’accesso gratuito è confermato, ma il download operativo va ancora ottimizzato.** Estrapolando il volume dei soli GRIB ECMWF del campione a 41 scadenze (0–120 ore ogni 3 ore), si ottengono circa **2,8 GB per aggiornamento**. È una stima di volume, non una misura di un download completo né una previsione dei tempi su GitHub Actions. Con lo schema NOAA attuale sarebbero **1.271 richieste per aggiornamento** e almeno circa 42 minuti con avvii distanziati di 2 secondi, nonostante un volume molto piccolo. Non inserire questa configurazione invariata nell’Action attuale con limite di 25 minuti.

Il prossimo incremento dovrà scegliere accesso, cache e organizzazione del lavoro in base a questi risultati, poi verificare una serie continua prima di attivare il calcolo o cambiare la pagina pubblica.

## Documentazione ufficiale

- [NOAA: inventario GEFS](https://www.nco.ncep.noaa.gov/pmb/products/gens/)
- [NOAA: catalogo dei file](https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/)
- [NOAA: politica di accesso NOMADS](https://www.weather.gov/media/notification/pdf2/scn21-32nomad_changes.pdf)
- [ECMWF: dati aperti e licenza](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [ECMWF: flussi, ensemble e controllo](https://confluence.ecmwf.int/spaces/DAC/pages/272310539/ECMWF%2Bopen%2Bdata%2Breal-time%2Bforecasts%2Bfrom%2BIFS%2Band%2BAIFS)
- [ECMWF: selezione per indici e richieste parziali](https://github.com/ecmwf/ecmwf-opendata)
