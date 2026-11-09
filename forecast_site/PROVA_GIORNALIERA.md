# Prova giornaliera delle onde su tre giorni

`scripts/probe_daily_waves.py` prepara una finestra di 72 ore dal momento di riferimento, usando la corsa 00 UTC e campioni ogni tre ore. È una prova separata: non calcola runup o TWL, non modifica Streamlit, i file pubblicati o il workflow attuale.

Il download giornaliero proposto è alle **09:37 UTC** (10:37 italiane in inverno, 11:37 in estate). La corsa 00 UTC non è disponibile a mezzanotte: prima bisogna attendere elaborazione, pubblicazione e acquisizione del fornitore. L'orario proposto non è una garanzia di disponibilità e non è ancora attivato. Nei dati si verifica sempre la corsa effettiva; una corsa vecchia o una serie incompleta viene rifiutata.

## Crediti e membri ECMWF

Per coprire le 72 ore successive alle 09:37 occorrono anche i campioni ai margini: scadenze da +9 a +84 ore, 26 orari. Non basta fermarsi a +72 dalla mezzanotte del modello.

Per entrambe le località richieste insieme, tre parametri e tutti i membri: **26 × 3 × 51 = 3.978 crediti**, prima di eventuali sconti della cache. Con solo 1.200 crediti effettivi non sarebbe possibile mantenere questa risoluzione.

Il 9 novembre 2026 l'endpoint quota del token di prova ha restituito `plan_name=Free Plan`, `plan_daily_limit=1200`, `overage_multiplier=5`, `effective_daily_limit=6000`. La quota effettiva attuale consente quindi la prova completa. Non assumere che questa concessione sia permanente. Lo script ricontrolla piano, quota, consumi e crediti residui prima di ogni richiesta. Non acquista abbonamenti, non modifica il token e non aggira i limiti del fornitore.

Per default il limite locale resta 1.200. Per il test completo si può scegliere esplicitamente `--daily-credit-cap 5000`: il codice ammette un limite superiore a 1.200 solo se l'API conferma **Free Plan** e una quota effettiva sufficiente; resta un margine di almeno 30 crediti. La quota è comune a tutte le richieste del token, non soltanto a questo script.

**I 51 membri non sono 51 modelli indipendenti:** sono 50 previsioni perturbate e una previsione di controllo del sistema ECMWF. Il catalogo GribStream elenca 0–50 in `ifswaef`, ma il test del 9 novembre ha restituito solo i 50 perturbati. Il controllo si scarica separatamente da `ifswave`. Il codice conserva questa provenienza e verifica corsa, orari, cella marina e tutte e tre le variabili anche sul controllo; non duplica un membro per arrivare a 51.

Si richiedono `swh` (altezza significativa), `pp1d` (periodo di picco), `mwd` (direzione media). La scelta della cella marina riprende quella verificata nella prova GRIB: Borghetto 44,00 N / 8,50 E; Venezia 45,25 N / 12,50 E. Questi punti non descrivono direttamente le onde sulla battigia.

## Risultato del test completo del 9 novembre 2026

La corsa **00 UTC del 9 novembre 2026** è stata verificata con tutti i 51 membri, entrambe le località e le 26 scadenze da +9 a +84 ore: **2.652 righe** complete. Sono presenti 2.600 righe perturbate e 52 del controllo. Ogni riga contiene altezza, periodo di picco e direzione; si verificano la corsa esatta, la cella marina e l’assenza di orari o membri mancanti/duplicati.

Il consumo massimo calcolato era 3.978 crediti. L’API ha registrato il passaggio da 778 a 4.200 crediti consumati: **3.422 crediti effettivi** per questa prova completa, con sconti della cache del fornitore. Per programmare gli aggiornamenti considerare comunque il costo pieno di 3.978, non lo sconto osservato. La quota residua effettiva dopo tutti i test del giorno era 1.800 su 6.000. Le due richieste dei dati sono durate circa 62 e 4 secondi, oltre alle verifiche della quota; i tempi futuri non sono garantiti.

Passati **87 test Python**, inclusi i controlli di compatibilità esistenti e quelli nuovi per completezza, credenziali, quote, cache e controllo separato. NOAA è stato verificato ai due estremi della finestra come descritto sotto. Nessun dato è stato pubblicato e nessun modello scientifico è stato modificato.

## Esecuzione

Installare le dipendenze separate in un ambiente dedicato:

```sh
python -m pip install -r forecast_service/ensemble-probe-requirements.txt
```

Stampare solo il piano, senza rete o credenziali:

```sh
python -B scripts/probe_daily_waves.py --at 2026-11-09T09:37:00Z
```

Il token deve restare fuori dalla repository, in un file con permessi 600 oppure nella variabile d'ambiente `GRIBSTREAM_TOKEN`. Non passarlo direttamente sulla riga di comando e non inserirlo in notebook, output o file pubblici.

Una prima richiesta minima costa circa 3 crediti:

```sh
python -B scripts/probe_daily_waves.py --smoke --download \
  --token-file /percorso/privato/gribstream-token \
  --output /tmp/runup-gribstream-minimo
```

Per la finestra completa con tutti i 51 membri, dopo aver verificato la quota del proprio piano gratuito:

```sh
python -B scripts/probe_daily_waves.py --members 51 --download \
  --daily-credit-cap 5000 \
  --token-file /percorso/privato/gribstream-token \
  --output /tmp/runup-gribstream-72h
```

Usare una cartella di output distinta per ciclo e finestra. Una risposta validata in cache locale viene riutilizzata senza rete, quindi senza crediti. La cache locale è distinta dallo sconto del 10% della cache del fornitore: non si può presumere tale sconto per una nuova corsa giornaliera. Dopo un timeout ambiguo lo script non ripete automaticamente la stessa richiesta: il marcatore `attempted-*` impone di controllare la quota prima di riprovare. Non cancellarlo senza questa verifica.

La modalità `--smoke` scarica solo +24 ore, un membro ECMWF e una località: non è una previsione completa di 72 ore. Aggiungere `--members 51` per verificare tutti i membri a quella singola scadenza. Un sottoinsieme esplicito, ad esempio `--members 8`, è un test tecnico e non va presentato come ensemble completo.

## NOAA e Copernicus

NOAA GEFS-Wave si scarica direttamente da NOMADS, senza token e senza crediti GribStream:

```sh
python -B scripts/probe_daily_waves.py --source noaa --download \
  --output /tmp/runup-noaa-72h
```

Il piano completo prevede 31 membri × 26 scadenze = 806 richieste, con entrambe le località nello stesso rettangolo. Si mantengono richieste sequenziali e avvii distanziati di almeno due secondi: servono almeno circa 27 minuti, più eventuali latenze. Non inserirlo invariato nell'Action di pubblicazione con timeout 25 minuti.

Nel test del 9 novembre, tutti i 31 membri NOAA sono stati verificati a +9 e +84 ore: 124 righe, 51.563 byte e circa 199 secondi. Questo verifica i due estremi della finestra, non tutte le scadenze intermedie. Periodo e direzione NOAA restano nativi (`PERPW/DIRPW`): il loro uso nel runup richiede ancora la verifica delle definizioni rispetto alle variabili Copernicus.

Copernicus resta nel motore esistente. Questo passo non modifica ancora le 96 ore del portale o le sue due esecuzioni giornaliere. Il passaggio del bollettino pubblico a 72 ore e a una sola esecuzione deve aggiornare insieme configurazione, testi, avviso di ritardo e workflow, dopo la verifica del download dei nuovi servizi. Per il primo confronto mantenere i fornitori separati, evitando di assegnare automaticamente più peso a quello con più membri.

## Riferimenti

- [GribStream: conteggio crediti e cache](https://gribstream.com/faq)
- [GribStream: endpoint quota e API](https://gribstream.com/docs)
- [Catalogo GribStream ifswaef](https://gribstream.com/api/v2/catalog/datasets/ifswaef)
- [GribStream: condizioni del servizio](https://gribstream.com/tos.html)
- [ECMWF: ensemble delle onde](https://www.ecmwf.int/en/forecasts/datasets/set-iv)
- [NOAA NOMADS](https://nomads.ncep.noaa.gov/)

La disponibilità tecnica del Free Plan non costituisce da sola una verifica delle condizioni per uso commerciale e ridistribuzione dei risultati: restano da chiarire con il fornitore prima di un impiego commerciale del portale.
