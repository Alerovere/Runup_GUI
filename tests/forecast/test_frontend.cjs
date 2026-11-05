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
