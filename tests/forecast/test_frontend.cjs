const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const context=vm.createContext({document:{getElementById:()=>({})},fetch:()=>new Promise(()=>{}),console,Intl,Date,URL,window:{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../forecast_site/app.js'),'utf8'),context);
const call=(code)=>vm.runInContext(code,context);

test('Il periodo scorre su 96 ore e non ripropone ore passate',()=>{
  call('bulletin={display_hours:96}');
  const rows=Array.from({length:120},(_,i)=>({time:new Date(Date.UTC(2026,10,5,0)+i*3600000).toISOString()}));
  context.locationFixture={hourly:rows};
  const result=call('windowRows(locationFixture, Date.UTC(2026,10,5,13,30))');
  assert.equal(result.length,96);
  assert.equal(result[0].time,'2026-11-05T13:00:00.000Z');
  assert.equal(call('windowRows(locationFixture, Date.UTC(2026,10,11)).length'),0);
});

test('Le ore mancanti separano gli eventi di superamento',()=>{
  context.samples=[{time:'2026-11-05T10:00Z',active:true,fraction:.5},{time:'2026-11-05T12:00Z',active:true,fraction:.7},
                   {time:'2026-11-05T13:00Z',active:false,fraction:1},{time:'2026-11-05T14:00Z',active:null,fraction:.3}];
  const events=call('exceedanceEvents(samples)');
  assert.equal(events.length,3);
  assert.equal(events[1].peak,.7);
});

test('Valori mancanti e soglie fuori stagione non diventano superamenti',()=>{
  context.samples=[{time:'2026-11-05T10:00Z',active:true,fraction:null},{time:'2026-11-05T11:00Z',active:false,fraction:1}];
  assert.equal(call('exceedanceEvents(samples).length'),0);
});

test('Il calendario usa Europe/Rome anche vicino alla mezzanotte UTC',()=>{
  assert.equal(call("italianTime('2026-07-01T22:30:00Z')"),'2026-07-02T00:30:00');
  assert.equal(call("italianTime('2026-11-01T23:30:00Z')"),'2026-11-02T00:30:00');
});




test('I settori di provenienza gestiscono direzioni arbitrarie, estremi e attraversamento dello zero',()=>{
  context.exposureFixture={sectors_deg:[[20,120],[250,300]]};
  assert.equal(call('isExposed(90,exposureFixture)'),true);
  assert.equal(call('isExposed(275,exposureFixture)'),true);
  assert.equal(call('isExposed(180,exposureFixture)'),false);
  assert.equal(call('isExposed(20,exposureFixture)'),true);
  assert.equal(call('isExposed(300,exposureFixture)'),true);
  assert.equal(call('isExposed(0,{sectors_deg:[[315,45]]})'),true);
  assert.equal(call('isExposed(360,{sectors_deg:[[315,45]]})'),true);
  assert.equal(call('isExposed(180,{sectors_deg:[[315,45]]})'),false);
  assert.equal(call('isExposed(0,{sectors_deg:[[270,360]]})'),true);
  assert.equal(call('isExposed(180,{sectors_deg:[[0,360]]})'),true);
});

test('Esposizione mancante, direzione mancante e mare calmo non diventano una falsa protezione',()=>{
  assert.equal(call('isExposed(90,null)'),null);
  assert.equal(call('isExposed(NaN,{sectors_deg:[[20,120]]})'),null);
  assert.equal(call('exposureAtPeak({wave_exposure:{sectors_deg:[[20,120]]}},[{hs_m:0,direction_deg:275}]).status'),null);
  assert.equal(call('exposureAtPeak({},[{hs_m:2,direction_deg:90}]).status'),null);
});

test('L’avviso direzionale si riferisce al picco Hs e non al picco TWL',()=>{
  const result=call('exposureAtPeak({wave_exposure:exposureFixture},[{hs_m:1,direction_deg:90,twl_max_m:4},{hs_m:2,direction_deg:180,twl_max_m:3}])');
  assert.equal(result.status,false);
  assert.equal(result.peak.hs_m,2);
  assert.match(result.text,/Sud \(180°\)/);
  assert.match(result.text,/direzione diversa da quelle a cui questa spiaggia è esposta/);
});

test('La frequenza storica distingue ore, campioni e altezze oltre tutta la serie',()=>{
  assert.match(call('climateFrequency(95,1)'),/5,0 ore su 100/);
  assert.match(call('climateFrequency(99.5,1)'),/meno di un’ora su 100/);
  assert.match(call('climateFrequency(95,3)'),/campioni su 100/);
  assert.match(call('climateFrequency(100,1)'),/non compaiono onde più alte/);
});




test('Il confronto degli estremi usa il settore al picco Hs, e può selezionare altri settori previsti',()=>{
  context.extremeLocation={climatology:{directional_extremes:{status:'available',sectors:[{id:'a',fit:{status:'available'}},{id:'b',fit:{status:'available'}}]}}};
  context.extremeRows=[{hs_m:3,direction_deg:90,wave_sector_id:'a',hs_return_period_years:5},{hs_m:2,direction_deg:180,wave_sector_id:'b',hs_return_period_years:20}];
  assert.equal(call('extremeComparison(extremeLocation,extremeRows).sector.id'),'a');
  assert.equal(call('extremeComparison(extremeLocation,extremeRows,"b").peak.hs_m'),2);
  assert.equal(call('extremeComparison(extremeLocation,extremeRows,"b").peak.hs_return_period_years'),20);
  assert.match(call('extremeComparison({},extremeRows).reason'),/non è ancora disponibile/);
});

test('Un riferimento per settore insufficiente non genera una curva o un tempo di ritorno',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  context.noFitLocation={climatology:{directional_extremes:{status:'available',sectors:[{id:'a',start_deg:20,end_deg:120,center_deg:70,width_deg:100,fit:{status:'insufficient_years',reason:'Anni insufficienti.'}}]}}};
  call('renderExtremes(noFitLocation,extremeRows.filter(r=>r.wave_sector_id==="a"))');
  assert.match(nodes['extremes-summary'].innerHTML,/Stima non disponibile/);
  assert.match(nodes['extremes-summary'].innerHTML,/Anni insufficienti/);
  assert.doesNotMatch(nodes['extremes-summary'].innerHTML,/id="extreme-chart"/);
});


test('Il grafico mostra la curva e il picco del solo settore selezionato',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  let plotted;
  context.Plotly={react:(id,traces,layout)=>{plotted={id,traces,layout};}};
  context.window.Plotly=context.Plotly;
  const fit={status:'available',n_years:40,first_year:1980,last_year:2019,bootstrap_replicates:100,return_period_years:[2,5,40,100],return_level_m:[2,3,4,5],ci95_low_m:[1,2,3,4],ci95_high_m:[3,4,5,6],empirical:[{year:2000,hs_m:3,return_period_years:5}]};
  context.graphLocation={climatology:{directional_extremes:{status:'available',sector_width_deg:180,sectors:[
    {id:'a',start_deg:270,end_deg:90,center_deg:0,width_deg:180,fit},
    {id:'b',start_deg:90,end_deg:270,center_deg:180,width_deg:180,fit:{...fit,return_level_m:[3,4,5,6]}}
  ]}}};
  call('renderExtremes(graphLocation,extremeRows)');
  assert.equal(plotted.id,'extreme-chart');
  assert.equal(plotted.traces.at(-1).y[0],3);
  assert.equal(plotted.traces.at(-1).x[0],5);
  nodes['extreme-sector'].onchange({target:{value:'b'}});
  assert.equal(plotted.traces.at(-1).y[0],2);
  assert.equal(plotted.traces.at(-1).x[0],20);
  assert.equal(plotted.traces[2].y[0],3);
  assert.match(nodes['extremes-summary'].innerHTML,/circa 20 anni/);
  delete context.window.Plotly;delete context.Plotly;
});


test('Il grafico identifica lo zero storico e la demo non viene etichettata come dato reale',()=>{
  call("bulletin={mode:'copernicus'}");
  context.levelLocation={datum_offset_m:0,mean_reference_m:-.4,sea_level_reference:{kind:'copernicus_historical_mean',year:2025,n_records:8760,mean_ssh_m:-.4,dataset_version:'202511',selected_point:{latitude:44.0625,longitude:8.333333}}};
  assert.equal(call('seaLevelReference(levelLocation).label'),'media Copernicus 2025');
  assert.match(call('seaLevelReference(levelLocation).caption'),/mantenuta fissa/);
  assert.match(call('seaLevelReference(levelLocation).detail'),/8[.\s]?760 ore/);
  call("bulletin={mode:'demo'}");
  assert.equal(call('seaLevelReference(levelLocation).label'),'riferimento sintetico');
});


test('Il livello costante non viene scambiato con un riferimento storico eventualmente presente',()=>{
  call("bulletin={mode:'copernicus'}");
  context.constantLevelLocation={...context.levelLocation,sea_level_source:{mode:'constant_msl',offset_m:0}};
  assert.equal(call('seaLevelReference(constantLevelLocation).label'),'livello medio mare assunto');
  assert.match(call('seaLevelReference(constantLevelLocation).caption'),/fissato a 0,00 m/);
});


test('La prossima uscita segue Copernicus in UTC, con conversione italiana in inverno ed estate',()=>{
  call("bulletin={wave_model:{publication_hours_utc:[6,20]}}");
  assert.equal(call("nextWavePublication(Date.parse('2026-11-05T19:00Z'))"),'2026-11-05T20:00:00.000Z');
  assert.match(call("noticeDate(nextWavePublication(Date.parse('2026-11-05T19:00Z')))"),/21:00/);
  assert.match(call("noticeDate(nextWavePublication(Date.parse('2026-07-05T05:00Z')))"),/08:00/);
  assert.equal(call("nextWavePublication(Date.parse('2026-11-05T06:00Z'))"),'2026-11-05T20:00:00.000Z');
  assert.equal(call("nextWavePublication(Date.parse('2026-11-05T20:00Z'))"),'2026-11-06T06:00:00.000Z');
});

test('La data di acquisizione non diventa una data del ciclo e la homepage gestisce cicli diversi',()=>{
  context.noticeLocations={a:{source:{downloaded_at:'2026-11-05T16:17Z',forecast_reference_time:'2026-11-05T00:00Z'}},b:{source:{downloaded_at:'2026-11-05T16:18Z',forecast_reference_time:'2026-11-05T12:00Z'}}};
  call('bulletin={locations:noticeLocations}');
  assert.equal(call('noticeWaveSource().kind'),'mixed');
  assert.equal(call('noticeWaveSource(noticeLocations.a).kind'),'cycle');
  assert.equal(call("noticeWaveSource({source:{downloaded_at:'2026-11-05T16:17Z'}}).kind"),'unknown');
});

test('Il bollettino mostra le tre informazioni richieste e mantiene gli avvisi di copertura',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  call("bulletin={mode:'copernicus',generated_at:'2026-11-05T16:20Z',wave_model:{publication_hours_utc:[6,20]}}");
  call("setNotice('Copertura parziale.',{source:{forecast_reference_time:'2026-11-05T12:00Z',downloaded_at:'2026-11-05T16:17Z'}},Date.parse('2026-11-05T16:30Z'))");
  assert.match(nodes.notice.innerHTML,/Elaborazione del/);
  assert.match(nodes.notice.innerHTML,/Corsa del modello Copernicus del/);
  assert.match(nodes.notice.innerHTML,/13:00/);
  assert.match(nodes.notice.innerHTML,/Prossima uscita prevista/);
  assert.match(nodes.notice.innerHTML,/21:00/);
  assert.match(nodes.notice.innerHTML,/Copertura parziale/);
  assert.doesNotMatch(nodes.notice.innerHTML,/Dati Copernicus Marine\./);
  call("setNotice('',{source:{downloaded_at:'2026-11-05T16:17Z'}},Date.parse('2026-11-05T16:30Z'))");
  assert.match(nodes.notice.innerHTML,/Corsa del modello Copernicus non disponibile/);
  assert.doesNotMatch(nodes.notice.innerHTML,/acquisiti il/);
});

test('La modalità demo resta esplicita e non promette uscite reali del modello',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  call("bulletin={mode:'demo',generated_at:'2026-11-05T00:00Z',locations:{}}");
  call("setNotice('',null,Date.parse('2026-11-06T00:00Z'))");
  assert.match(nodes.notice.innerHTML,/Modalità dimostrativa/);
  assert.match(nodes.notice.innerHTML,/sintetici/);
  assert.match(nodes.notice.innerHTML,/Aggiornamento in ritardo/);
  assert.doesNotMatch(nodes.notice.innerHTML,/Prossima uscita/);
});


const fixedThreshold={id:'strutture_turistiche_fisse',elevation_m:1.1,season:'all_year',short_label:'Chioschi e strutture fisse'};
const exposure={sectors_deg:[[112,247]]};
const makeRow=(extra={})=>({time:'2026-11-06T05:00Z',statistics_method:'sigma_clip_3_population_v1',n_estimates:190,n_estimates_raw:190,n_outliers:0,twl_max_m:100,twl_mean_m:.7,twl_p05_m:.2,twl_p25_m:.4,twl_p75_m:.9,twl_p95_m:1.2,hs_m:1,tp_s:5,direction_deg:180,water_level_m:.15,thresholds:[{id:fixedThreshold.id,active:true,fraction:5/190}],...extra});

test('La scala usa soltanto i percentili filtrati, con uguaglianza esclusa dal superamento',()=>{
  context.fixedThreshold=fixedThreshold;
  for (const [rank,extra] of [[0,{twl_p95_m:1.1}],[1,{}],[2,{twl_p75_m:1.2}]]) {
    context.colorRow=makeRow(extra);assert.equal(call('rowImpact(fixedThreshold,colorRow).rank'),rank);
  }
  context.colorRow=makeRow({twl_mean_m:1000,twl_max_m:10000,twl_p75_m:.8,twl_p95_m:1});
  assert.equal(call('rowImpact(fixedThreshold,colorRow).rank'),0);
  assert.equal(call('rowImpact({...fixedThreshold,elevation_m:2},colorRow).rank'),0);
});

test('Bollettini precedenti, direzioni ignote e dati mancanti non ricevono categorie rassicuranti',()=>{
  context.colorLocation={thresholds:[fixedThreshold],wave_exposure:exposure};
  for (const extra of [{n_estimates:0},{twl_p95_m:null},{statistics_method:null},{thresholds:[]}]) {
    context.colorRow=makeRow(extra);assert.equal(call('rowImpact(fixedThreshold,colorRow,colorLocation).rank'),null);
  }
  context.colorRow=makeRow();
  assert.equal(call('assessTrend({thresholds:[fixedThreshold]},[colorRow]).key'),'unavailable');
  context.colorRow=makeRow({direction_deg:null});assert.equal(call('assessTrend(colorLocation,[colorRow]).key'),'unavailable');
});

test('Le ore non frontali sono grigie e non cancellano le ore frontali dello stesso periodo',()=>{
  context.colorLocation={thresholds:[fixedThreshold],wave_exposure:exposure};
  context.colorRows=[makeRow({direction_deg:85,twl_p75_m:99,twl_p95_m:100})];
  assert.equal(call('assessTrend(colorLocation,colorRows).key'),'gray');
  context.colorRows.push(makeRow({twl_p95_m:1}));
  assert.equal(call('assessTrend(colorLocation,colorRows).key'),'white');
  context.colorRows.push(makeRow({twl_p75_m:1.3}));
  assert.equal(call('assessTrend(colorLocation,colorRows).key'),'orange');
});

test('Tendenza e giornate usano la stessa scala e la percentuale dell’ora selezionata',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  context.colorLocation={thresholds:[fixedThreshold],wave_exposure:exposure};
  context.colorRows=[makeRow({twl_p75_m:1.3}),makeRow({time:'2026-11-07T05:00Z',direction_deg:85})];
  call('bulletin={display_hours:96};renderDaily(colorLocation,colorRows)');
  assert.equal(nodes['outlook-panel'].className,'panel outlook-panel impact-orange');
  assert.match(nodes.daily.innerHTML,/impact-orange/);assert.match(nodes.daily.innerHTML,/impact-gray/);
  assert.match(nodes.outlook.innerHTML,/2,6%/);assert.doesNotMatch(nodes.outlook.innerHTML,/scenar|Rosso|Verde/);
  assert.equal(nodes['outlook-title'].textContent,'Tendenza a 4 giorni');
});

test('Una piccola coda sopra quota non rende il bianco un falso “nessun modello supera”',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  context.structureLocation={thresholds:[fixedThreshold],wave_exposure:exposure};context.structureRows=[makeRow({twl_p95_m:1})];
  call('renderThresholds(structureLocation,structureRows)');
  assert.match(nodes.thresholds.innerHTML,/impact-white/);assert.match(nodes.thresholds.innerHTML,/fascia delle stime non supera/);
  assert.doesNotMatch(nodes.thresholds.innerHTML,/Orari del possibile|nessun risultato|quota non è superata dai modelli/i);
});

test('Le finestre richiedono P95 sopra quota e onde frontali, con separazione ai cambi di direzione',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  context.structureLocation={thresholds:[fixedThreshold],wave_exposure:exposure};
  context.structureRows=[makeRow(),makeRow({time:'2026-11-06T06:00Z',direction_deg:85}),makeRow({time:'2026-11-06T07:00Z'}),makeRow({time:'2026-11-06T08:00Z',twl_p95_m:1}),makeRow({time:'2026-11-06T09:00Z'})];
  call('renderThresholds(structureLocation,structureRows)');
  assert.equal((nodes.thresholds.innerHTML.match(/<li>/g)||[]).length,3);
  assert.match(nodes.thresholds.innerHTML,/2,6%/);assert.match(nodes.thresholds.innerHTML,/class="asset-icon"/);
  assert.match(nodes.thresholds.innerHTML,/impact-yellow/);assert.doesNotMatch(nodes.thresholds.innerHTML,/scenar|<table|<details/);
  context.structureRows=[makeRow({direction_deg:85})];call('renderThresholds(structureLocation,structureRows)');
  assert.match(nodes.thresholds.innerHTML,/impact-gray/);assert.doesNotMatch(nodes.thresholds.innerHTML,/<li>/);
});

test('Il calendario estivo continua a distinguere stagione ignota e non attiva',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  context.seasonLocation={thresholds:[{...fixedThreshold,season:'summer'}],wave_exposure:exposure};
  context.seasonRows=[makeRow({thresholds:[{id:fixedThreshold.id,active:false,fraction:1}]})];
  call('renderThresholds(seasonLocation,seasonRows)');assert.match(nodes.thresholds.innerHTML,/Fuori stagione/);assert.doesNotMatch(nodes.thresholds.innerHTML,/Orari del possibile/);
  context.seasonRows=[makeRow({thresholds:[{id:fixedThreshold.id,active:null,fraction:.5}]})];
  call('renderThresholds(seasonLocation,seasonRows)');assert.match(nodes.thresholds.innerHTML,/Calendario estivo da definire/);assert.match(nodes.thresholds.innerHTML,/50%/);
});

test('Il TWL non disegna estremi e non presenta statistiche vecchie come filtrate',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  const plots={};context.Plotly={react:(id,traces,layout)=>plots[id]={traces,layout}};context.window.Plotly=context.Plotly;
  context.graphLocation={thresholds:[],wave_exposure:exposure,sea_level_source:{mode:'constant_msl',offset_m:0}};
  context.graphRows=[makeRow(),makeRow({statistics_method:null})];
  call("bulletin={mode:'copernicus'};renderCharts(graphLocation,graphRows)");
  assert.doesNotMatch(plots['twl-chart'].traces.map(t=>t.name).join(' '),/Massimo|Minimo/);
  const mean=plots['twl-chart'].traces.find(t=>t.name==='Media dei calcoli');
  assert.deepEqual(Array.from(mean.y),[.7,null]);
  delete context.window.Plotly;delete context.Plotly;
});

test('Onde, provenienza e livello marino conservano date e valori originali',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  const plots={};context.Plotly={react:(id,traces,layout)=>plots[id]={traces,layout}};context.window.Plotly=context.Plotly;
  context.waveLocation={thresholds:[],wave_exposure:exposure,sea_level_source:{mode:'constant_msl',offset_m:0},climatology:{status:'available',time_step_hours:1,p95_m:2,p99_m:3}};
  context.waveRows=[makeRow({direction_deg:85}),makeRow({tp_s:8}),makeRow({hs_m:0,direction_deg:90,tp_s:null})];
  call("bulletin={mode:'copernicus'};renderCharts(waveLocation,waveRows)");
  const wave=plots['wave-chart'],away=wave.traces.find(t=>t.name==='Onde da altre direzioni'),toward=wave.traces.find(t=>t.name==='Onde verso la costa');
  const sea=wave.traces.find(t=>t.name==='Marea + Storm surge'),tp=wave.traces.find(t=>t.name==='Tempo tra le onde (Tp)');
  assert.equal(away.y[0],85);assert.equal(away.y[1],null);assert.equal(toward.y[1],180);assert.equal(toward.y[2],null);
  assert.deepEqual(Array.from(sea.y),[.15,.15,.15]);assert.equal(sea.x,wave.traces[0].x);assert.equal(wave.layout.xaxis.anchor,'y4');
  assert.deepEqual(Array.from(tp.y),[5,8,null]);assert.equal(tp.line.shape,'spline');assert.equal(tp.connectgaps,false);
  assert.match(nodes['wave-series-key'].innerHTML,/5 ore su 100/);assert.doesNotMatch(nodes['wave-series-key'].innerHTML,/percentile/);
  assert.equal(wave.traces.find(t=>t.name.startsWith('Onde alte')).y[0],2);assert.equal(wave.traces.find(t=>t.name.startsWith('Onde molto alte')).y[0],3);
  delete context.window.Plotly;delete context.Plotly;
});

test('Le percentuali rare non diventano zero e un accordo incompleto non diventa cento',()=>{
  assert.equal(call('percentage(5/190)'),'2,6%');assert.equal(call('percentage(.0001)'),'<0,1%');assert.equal(call('percentage(.9999)'),'>99,9%');
});


test('La finestra giornaliera MeteOcean termina dopo quattro giorni senza riproporre ore passate',()=>{
  call("bulletin={display_hours:96,display_to:'2026-11-13T00:00:00Z'}");
  context.dailyWindow={hourly:Array.from({length:120},(_,i)=>({time:new Date(Date.UTC(2026,10,9)+i*3600000).toISOString()}))};
  assert.equal(call('windowRows(dailyWindow,Date.UTC(2026,10,9,14,30)).length'),82);
  assert.equal(call('windowRows(dailyWindow,Date.UTC(2026,10,13)).length'),0);
});

test('MeteOcean e NOAA sono descritti senza riutilizzare la media Copernicus',()=>{
  const reference=call("seaLevelReference({sea_level_source:{mode:'noaa_tide_meteocean_surge'},mean_reference_m:-.403,sea_level_reference:{kind:'copernicus_historical_mean',year:2025}})");
  assert.match(reference.caption,/NOAA/);
  assert.match(reference.caption,/MeteOcean/);
  assert.doesNotMatch(reference.axis,/2025/);
});


test('La prossima acquisizione MeteOcean è una data valida e il ritardo segue la cadenza giornaliera',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  call("bulletin={mode:'meteocean',generated_at:'2026-11-09T00:00Z',stale_after_hours:30,wave_model:{publication_hours_utc:[]},locations:{}}");
  call("setNotice('',null,Date.parse('2026-11-10T02:00Z'))");
  assert.match(nodes.notice.innerHTML,/MeteOcean/);assert.match(nodes.notice.innerHTML,/NOAA/);
  assert.match(nodes.notice.innerHTML,/07:40/);assert.doesNotMatch(nodes.notice.innerHTML,/data non disponibile|Aggiornamento in ritardo|Corsa del modello Copernicus/);
  call("setNotice('',null,Date.parse('2026-11-10T07:00Z'))");
  assert.match(nodes.notice.innerHTML,/più di 30 ore/);
});


test('Marea e surge sono separati con scala comune, somma e campioni mancanti conservati',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={style:{}});
  const plots={};context.Plotly={react:(id,traces,layout)=>plots[id]={traces,layout}};context.window.Plotly=context.Plotly;
  context.separateLocation={thresholds:[],wave_exposure:exposure,sea_level_source:{mode:'noaa_tide_meteocean_surge'}};
  context.separateRows=[makeRow({tide_m:-.2,surge_m:.1,water_level_m:-.1}),makeRow({tide_m:.3,surge_m:null,water_level_m:null})];
  call("bulletin={mode:'meteocean'};renderCharts(separateLocation,separateRows)");
  const graph=plots['wave-chart'];
  const tide=graph.traces.find(t=>t.name==='Marea astronomica NOAA');
  const surge=graph.traces.find(t=>t.name==='Storm surge MeteOcean');
  const sum=graph.traces.find(t=>t.name==='Marea + Storm surge');
  assert.equal(tide.yaxis,'y4');assert.equal(surge.yaxis,'y5');assert.equal(sum.yaxis,'y6');
  assert.equal(tide.x,surge.x);assert.equal(surge.x,sum.x);assert.equal(graph.layout.xaxis.anchor,'y6');
  assert.deepEqual(Array.from(tide.y),[-.2,.3]);assert.deepEqual(Array.from(surge.y),[.1,null]);assert.deepEqual(Array.from(sum.y),[-.1,null]);
  assert.equal(surge.connectgaps,false);assert.equal(sum.connectgaps,false);
  assert.deepEqual(Array.from(graph.layout.yaxis4.range),Array.from(graph.layout.yaxis5.range));
  assert.deepEqual(Array.from(graph.layout.yaxis5.range),Array.from(graph.layout.yaxis6.range));
  assert.ok(graph.layout.yaxis4.range[0]<-.2);assert.ok(graph.layout.yaxis4.range[1]>.3);
  assert.equal(nodes['wave-chart'].style.height,'1150px');
  call("bulletin={mode:'copernicus'};renderCharts(separateLocation,[{...separateRows[0],tide_m:undefined,surge_m:undefined}])");
  assert.equal(plots['wave-chart'].layout.yaxis6,undefined);assert.equal(nodes['wave-chart'].style.height,'650px');
  delete context.window.Plotly;delete context.Plotly;
});


test('Pubblicazione 06:20 UTC e acquisizione 06:40 UTC restano distinte anche con ora legale',()=>{
  call("bulletin={wave_model:{publication_hours_utc:[6],publication_minute_utc:20},update_schedule:{hours_utc:[6],minute_utc:40}}");
  assert.equal(call("nextWavePublication(Date.parse('2026-11-09T06:19:00Z'))"),'2026-11-09T06:20:00.000Z');
  assert.equal(call("nextSiteAcquisition(Date.parse('2026-11-09T06:20:00Z'))"),'2026-11-09T06:40:00.000Z');
  assert.equal(call("nextSiteAcquisition(Date.parse('2026-11-09T06:40:00Z'))"),'2026-11-10T06:40:00.000Z');
  assert.match(call("noticeDate(nextSiteAcquisition(Date.parse('2026-11-09T06:35:00Z')))"),/07:40/);
  assert.match(call("noticeDate(nextSiteAcquisition(Date.parse('2026-07-09T06:35:00Z')))"),/08:40/);
});

test('La selezione opzionale usa il settore valido e mantiene la spiaggia senza settori',()=>{
  context.beachFixture={name:'Spiaggia',hourly:[{hs_m:1}],sectors:{ponente:{name:'Ponente',hourly:[{hs_m:2}]}}};
  assert.equal(call('selectedBeachUnit(beachFixture,"ponente").name'),'Ponente');
  assert.equal(call('selectedBeachUnit(beachFixture,"sconosciuto").name'),'Spiaggia');
  assert.equal(call('selectedBeachUnit({name:"Spiaggia unica"},null).name'),'Spiaggia unica');
  assert.equal(call('selectedBeachUnit(beachFixture,"__proto__").name'),'Spiaggia');
});

test('La mappa dichiara periodo fisso, direzioni non frontali, incertezza e scadenza',()=>{
  context.mapFixture={status:'available',period_from:'2026-11-11T06:00Z',period_to:'2026-11-15T06:00Z',hours_non_frontal:12,hours_direction_unknown:2};
  const text=call('inundationMapText(mapFixture,Date.UTC(2026,10,11,12))');
  assert.match(text,/Inviluppo delle 96 ore/);
  assert.match(text,/12 ore/);assert.match(text,/2 ore/);
  assert.match(text,/Non sono probabilità/);
  assert.doesNotMatch(text,/Periodo concluso/);
  assert.match(call('inundationMapText(mapFixture,Date.UTC(2026,10,16))'),/Periodo concluso/);
  assert.match(call('inundationMapText({status:"unavailable",reason:"DEM mancante"})'),/DEM mancante/);
});

test('Una spiaggia senza settori nasconde il selettore e senza cartografia nasconde la mappa',()=>{
  const nodes={};context.document.getElementById=id=>(nodes[id]??={});
  call('renderSectorSelector({name:"Spiaggia unica"},null)');
  assert.equal(nodes['sector-selection'].hidden,true);
  call('renderInundation({name:"Spiaggia unica"})');
  assert.equal(nodes['inundation-panel'].hidden,true);
});
