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

test('Gli impatti stagionali ignoti non vengono presentati come impatti annuali',()=>{
  context.fixture={thresholds:[{id:'a',elevation_m:.7,season:'summer',short_label:'Ombrelloni'},{id:'b',elevation_m:1.1,season:'all_year',short_label:'Chioschi'}]};
  context.rows=[{time:'2026-11-05T10:00Z',n_estimates:30,thresholds:[{id:'a',active:null,fraction:.8},{id:'b',active:true,fraction:0}]}];
  const result=call('assessImpact(fixture,rows)');
  assert.equal(result.seasonal.length,1);
  assert.equal(result.focus,undefined);
  assert.match(result.title,/non raggiunte/);
});

test('Una quota superata da pochi scenari resta distinta da un esito condiviso',()=>{
  context.rows=[{time:'2026-11-05T10:00Z',n_estimates:30,thresholds:[{id:'a',active:false,fraction:.8},{id:'b',active:true,fraction:.1}]}];
  const result=call('assessImpact(fixture,rows)');
  assert.match(result.title,/Alcuni scenari/);
  assert.equal(result.focus.threshold.short_label,'Chioschi');
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
  assert.match(result.text,/fuori/);
});

test('La frequenza storica distingue ore, campioni e altezze oltre tutta la serie',()=>{
  assert.match(call('climateFrequency(95,1)'),/5,0 ore su 100/);
  assert.match(call('climateFrequency(99.5,1)'),/meno di un’ora su 100/);
  assert.match(call('climateFrequency(95,3)'),/campioni su 100/);
  assert.match(call('climateFrequency(100,1)'),/non compaiono onde più alte/);
});

test('Il confronto storico usa la vera altezza massima anche con percentili saturi',()=>{
  const nodes={};
  context.document.getElementById=id=>(nodes[id]??={});
  context.climateFixture={climatology:{status:'available',source:'ERA5',start:'2000-01-01',end:'2020-12-31',time_step_hours:1,n_records:100,coverage_fraction:1,p95_m:2,p99_m:2.5,max_hs_m:2.8,comparison_note:'Confronto indicativo.'}};
  call("renderClimate(climateFixture,[{time:'2026-11-07T06:00Z',hs_m:3,hs_percentile:100},{time:'2026-11-07T07:00Z',hs_m:4,hs_percentile:100}])");
  assert.match(nodes['climate-summary'].innerHTML,/4,00 m/);
  assert.match(nodes['climate-summary'].innerHTML,/non compaiono onde più alte/);
  assert.match(nodes['climate-summary'].innerHTML,/tutte le direzioni/);
});

test('La soglia usa una frase italiana con data, ora e accordo singolare o plurale',()=>{
  const nodes={};
  context.document.getElementById=id=>(nodes[id]??={});
  context.thresholdFixture={thresholds:[{id:'a',elevation_m:.7,season:'all_year',short_label:'Struttura'}]};
  call("renderThresholds(thresholdFixture,[{time:'2026-11-07T06:00Z',n_estimates:30,thresholds:[{id:'a',active:true,fraction:.9}]}])");
  assert.match(nodes.thresholds.innerHTML,/Il 7 novembre, alle 07:00/);
  assert.match(nodes.thresholds.innerHTML,/27 scenari su 30<\/strong> superano questa quota/);
  call("renderThresholds(thresholdFixture,[{time:'2026-11-07T06:00Z',n_estimates:30,thresholds:[{id:'a',active:true,fraction:1\/30}]}])");
  assert.match(nodes.thresholds.innerHTML,/1 scenario su 30<\/strong> supera questa quota/);
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
