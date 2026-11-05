# Definizione dei siti in Colab

Aprire `Definisci_siti_studio.ipynb` in [Google Colab](https://colab.research.google.com/) usando **File → Carica notebook**. Le funzioni sono incluse nel notebook: non occorre clonare la repository, pubblicare il sito o configurare GitHub per eseguirlo.

## Prima prova

1. Eseguire le celle in ordine con `DEMO=True`. Non servono token né richieste a servizi esterni; i profili e la distribuzione delle onde sono sintetici e dichiarati come tali.
2. Controllare la tabella delle pendenze e il grafico: i punti arancioni sono quelli usati per la regressione. Il terreno dietro il primo punto sopra Z_MAX deve essere escluso anche se torna a quote inferiori.
3. Esportare il pacchetto demo per familiarizzare con i contenuti. L’importatore del portale lo rifiuta per impostazione predefinita.

## I propri siti di studio

1. Impostare `DEMO=False`, poi rieseguire tutte le celle.
2. Compilare nome, identificativo, tratto di costa e coordinate del sito e del punto onde offshore. Si può impostare un punto distinto per il livello marino. La mappa mostra i punti e restituisce coordinate al clic; riportare quelle scelte nei campi e rieseguire la cella.
3. Caricare il CSV QGIS o indicare un file già presente. I nomi iniziali sono quelli del notebook fornito: `TR_ID`, `distance`, `SAMPLE_1`, `X`, `Y`. Sono modificabili. Indicare il CRS proiettato in metri; EPSG:32632 è solo il valore iniziale per Borghetto. Le quote devono riferirsi a un riferimento dichiarato, con correzione esplicita se necessaria.
4. Impostare Z_MIN e Z_MAX. Il metodo è quello del notebook didattico: orientamento dalla media delle prime/ultime 10 quote, distanza X/Y dal primo punto a mare, arresto al primo punto sopra Z_MAX e regressione lineare sul tratto precedente con quota almeno Z_MIN. Con profili corti l’orientamento può essere ambiguo: verificarlo e scegliere il verso esplicitamente se necessario. Il segno della pendenza non viene nascosto con un valore assoluto.
5. Esaminare grafici e diagnostica. Correggere i transetti non validi oppure escluderli esplicitamente. Scegliere se esportare le pendenze dei transetti o campionare uniformemente l’intervallo minimo–massimo.
6. Definire stagione estiva, rugosità e soglie delle strutture. Le soglie proposte restano esempi da validare.
7. Scaricare ERA5 dal CDS oppure importare un CSV già disponibile. Il default storico è 1991–2020, modificabile. Il download richiede il consenso esplicito nella cella e le condizioni dei dataset accettate personalmente sul CDS. Il token si legge dai Secrets Colab `CDS_KEY` o tramite input protetto; non scriverlo nei campi del notebook. Per conservare la cache fra sessioni si può attivare il salvataggio su Drive.
8. Verificare distribuzione, percentili 95/99, massimo osservato e massimi annuali. ERA5 fornisce periodo medio, non Tp; il portale continua a usare Tp Copernicus per il runup. Il confronto storico non è una stima dei periodi di ritorno.
9. Rivedere il riepilogo e scaricare lo ZIP del sito. Dopo aver cambiato modalità o parametri, rieseguire caricamento, calcolo, grafico e selezione prima dell’esportazione: il notebook verifica la coerenza di questi passaggi.

## Importazione nel portale

Dalla radice di Runup_GUI, per aggiornare Borghetto già presente:

```sh
python scripts/import_site_package.py /percorso/borghetto-santo-spirito_studio.zip --replace
```

Per Venezia usare il suo identificativo. Per località nuove omettere `--replace`. L’importatore valida la configurazione prima di aggiornare i file, copia la climatologia quando disponibile e conserva la documentazione del sito in `config/study_sites/IDENTIFICATIVO/`. Non effettua commit, push o pubblicazioni. Per una prova locale esplicita con lo ZIP demo occorre anche `--allow-demo`.

Il pacchetto comprende configurazione, soglie, tabella delle pendenze, profili normalizzati, un grafico del transetto scelto e il riferimento climatologico quando calcolato. I token e i NetCDF della cache non vengono inclusi. Conservare la cache o il CSV storico separatamente per eventuali aggiornamenti.

La stima delle pendenze usa il metodo del notebook fornito, senza cambiare le formule di runup già presenti nell’app. Non viene simulata la propagazione dell’acqua a terra e il riferimento delle quote richiede ancora verifica locale.

## Aggiornare il notebook come sviluppatore

Le funzioni condivise sono in `forecast_service/site_setup.py`, `era5_download.py`, `climate.py`, `time_utils.py` e `site_package.py`. Dopo una modifica, rigenerare il notebook per aggiornare la copia inclusa:

```sh
python -m pip install nbformat
python scripts/build_setup_notebook.py
```

Il test `test_notebook_embeds_current_sources` verifica che la copia inclusa non diverga dai moduli del progetto. Il notebook distribuito non contiene output o credenziali salvati.
