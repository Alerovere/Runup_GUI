'use strict';
const $ = id => document.getElementById(id);
const esc = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (value, digits=2) => Number.isFinite(value) ? value.toLocaleString('it-IT', {minimumFractionDigits:digits, maximumFractionDigits:digits}) : '—';
const local = (value, options={}) => new Date(value).toLocaleString('it-IT', {timeZone:'Europe/Rome', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', ...options});
const hourMs = 3600000;
const thresholdColors=['#a6a15c','#c49b54','#bf7848','#ab4d40'];
let bulletin;
let map;

// Calendar grouping uses Italian dates; chart coordinates remain absolute UTC
// milliseconds so the repeated autumn hour never folds the forecast backwards.
function italianTime(value) {
  const parts = new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/Rome', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));
  const p = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

function windowRows(location, now=Date.now()) {
  const start = Math.floor(now/hourMs)*hourMs;
  return location.hourly.filter(row => new Date(row.time).getTime() >= start && new Date(row.time).getTime() < start + bulletin.display_hours*hourMs);
}

function setNotice(extra='') {
  const demo = bulletin.mode === 'demo';
  const age = (Date.now()-new Date(bulletin.generated_at))/hourMs;
  $('notice').className = `notice${demo ? ' demo' : ''}`;
  const message = demo ? '<strong>MODALITÀ DIMOSTRATIVA.</strong> Onde e livello del mare sintetici: questi grafici non sono previsioni meteo-marine.' : `<strong>Dati Copernicus Marine.</strong> Elaborazione del ${esc(local(bulletin.generated_at))} (ora italiana).`;
  $('notice').innerHTML = message + (age > 18 ? ' <strong>Aggiornamento in ritardo: il bollettino ha più di 18 ore.</strong>' : '') + (extra ? ' '+esc(extra) : '');
}

function locationCards() {
  $('location-cards').innerHTML = Object.entries(bulletin.locations).map(([slug, location], index) => {
    const rows = windowRows(location);
    const maximum = rows.length ? Math.max(...rows.filter(r => Number.isFinite(r.twl_max_m)).map(r => r.twl_max_m)) : NaN;
    return `<a class="location-card" href="?localita=${encodeURIComponent(slug)}"><div><div class="card-top"><span class="card-index">LOCALITÀ / 0${index+1}</span><span class="card-arrow" aria-hidden="true">↗</span></div><h3>${esc(location.name)}</h3><p>${esc(location.area)}</p></div><div class="card-bottom"><span>${rows.length ? `Massimo scenari: <strong>${num(maximum)} m</strong>` : 'Nessun dato futuro disponibile'}</span><span>Esplora le previsioni →</span></div></a>`;
  }).join('');
}

function setupMap() {
  if (map || !window.L) return;
  $('map').replaceChildren();
  map = L.map('map', {scrollWheelZoom:false}).setView([44.6,10.2],6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:18, attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
  const points = [];
  for (const [slug, location] of Object.entries(bulletin.locations)) {
    const point = [location.map_point.latitude, location.map_point.longitude];
    points.push(point);
    const visit = () => navigate(slug);
    L.circle(point, {radius:10000,color:'#194e4c',weight:1,fillOpacity:.08}).addTo(map).on('click',visit);
    L.marker(point, {title:location.name, icon:L.divIcon({className:'map-pin',iconSize:[20,20],iconAnchor:[10,10]})})
      .addTo(map).bindTooltip(esc(location.name),{permanent:true,direction:'top',offset:[0,-15]}).on('click',visit);
  }
  map.fitBounds(points,{padding:[60,70],maxZoom:7});
}

function navigate(slug) {
  const url = new URL(window.location.href);
  if (slug) url.searchParams.set('localita',slug); else url.searchParams.delete('localita');
  history.pushState({},'',url);
  renderRoute();
  window.scrollTo({top:0,behavior:'smooth'});
}

function groupsByDay(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = italianTime(row.time).slice(0,10);
    if (!groups.has(key)) groups.set(key,[]);
    groups.get(key).push(row);
  }
  return [...groups.values()];
}

function thresholdState(threshold, rows) {
  const samples = rows.map(row => ({time:row.time, ...row.thresholds.find(t => t.id===threshold.id)}));
  const available = samples.filter(s => s.active!==false && Number.isFinite(s.fraction));
  const max = available.length ? Math.max(...available.map(s => s.fraction)) : null;
  let season = 'Tutto l’anno';
  if (threshold.season==='summer') {
    season = samples.some(s => s.active===null) ? 'Stagione estiva: date da definire · confronto indicativo' : samples.some(s=>s.active===true) ? 'Stagione estiva: attiva nel periodo' : 'Fuori stagione · soglia non applicata';
  }
  return {samples,available,max,season};
}

function assetName(threshold) {
  return threshold.short_label || threshold.description;
}

function assessImpact(location, rows) {
  const valid=rows.filter(row=>row.n_estimates>0);
  const active=[];
  const seasonal=[];
  for (const threshold of location.thresholds) {
    const samples=rows.map(row=>({time:row.time,n:row.n_estimates,...row.thresholds.find(t=>t.id===threshold.id)}));
    const known=samples.filter(s=>s.active===true && Number.isFinite(s.fraction));
    const peak=known.length?known.reduce((best,s)=>s.fraction>best.fraction?s:best):null;
    if (peak && peak.fraction>0) active.push({threshold,peak,samples:known});
    if (samples.some(s=>s.active===null && s.fraction>0)) seasonal.push(threshold);
  }
  active.sort((a,b)=>a.threshold.elevation_m-b.threshold.elevation_m);
  const mostShared=active.filter(s=>s.peak.fraction>=.5).at(-1);
  const upper=active.at(-1);
  let title='Strutture fisse: quote non raggiunte negli scenari disponibili';
  let explanation='I livelli calcolati restano sotto le quote configurate per chioschi e passeggiata.';
  if (!valid.length) {
    title='Dati insufficienti per descrivere gli impatti';
    explanation='Nessuno scenario valido nelle ore disponibili.';
  } else if (mostShared) {
    title=`Possibile interessamento: ${assetName(mostShared.threshold).toLowerCase()}`;
    explanation=`La quota di ${num(mostShared.threshold.elevation_m)} m è superata da almeno metà degli scenari in una o più ore.`;
  } else if (upper) {
    title=`Alcuni scenari raggiungono la quota associata a ${assetName(upper.threshold).toLowerCase()}`;
    explanation='Il superamento compare in meno della metà degli scenari: il risultato è poco condiviso.';
  }
  const focus=mostShared||upper;
  const hours=focus?focus.samples.filter(s=>s.fraction>0):[];
  const upperNote=upper && mostShared && upper.threshold.id!==mostShared.threshold.id
    ? `Negli scenari superiori può essere raggiunta anche la quota associata a ${assetName(upper.threshold).toLowerCase()} (${num(upper.threshold.elevation_m)} m).` : '';
  return {title,explanation,focus,hours,upperNote,seasonal,validCount:valid.length};
}

function renderDaily(location, rows) {
  $('daily').innerHTML=groupsByDay(rows).map(group=>{
    const result=assessImpact(location,group);
    const valid=group.filter(r=>Number.isFinite(r.twl_max_m));
    const maximum=valid.length?Math.max(...valid.map(r=>r.twl_max_m)):NaN;
    const peak=valid.length?valid.reduce((best,r)=>r.twl_max_m>best.twl_max_m?r:best):null;
    const date=new Date(group[0].time).toLocaleDateString('it-IT',{timeZone:'Europe/Rome',weekday:'long',day:'numeric',month:'short'});
    const intervals=result.focus?exceedanceEvents(result.focus.samples):[];
    const window=intervals.length?intervals.map(event=>`${local(event.start,{day:undefined,month:undefined})}–${local(event.end,{day:undefined,month:undefined})}`).join(' · '):'Nessuna fascia di superamento delle soglie attive';
    return `<article class="day-card impact-day"><h3>${esc(date)}</h3><div class="day-impact">${esc(result.title)}</div><p>${esc(result.explanation)}</p><div class="day-time">${esc(window)}</div><p class="day-range">Livello massimo degli scenari: <strong>${num(maximum)} m</strong>${peak?` · picco alle ${local(peak.time,{day:undefined,month:undefined})}`:''}</p>${result.upperNote?`<p>${esc(result.upperNote)}</p>`:''}${result.seasonal.length?'<p class="season-note">Ombrelloni / strutture stagionali: calendario da definire.</p>':''}<p>${group.length} ore disponibili${group.length<24?' · giornata parziale':''}${valid.length<group.length?' · alcuni risultati mancanti':''}</p></article>`;
  }).join('');
  const outlook=assessImpact(location,rows);
  $('outlook').innerHTML=`<h3>${esc(outlook.title)}</h3><p>${esc(outlook.explanation)}</p>${outlook.upperNote?`<p>${esc(outlook.upperNote)}</p>`:''}<p class="small muted">Le associazioni fra quote e strutture sono esempi da verificare sul posto. ${outlook.seasonal.length?'Le soglie estive sono mostrate a titolo indicativo perché il calendario non è ancora definito.':''}</p>`;
}

function exceedanceEvents(samples) {
  const events = [];
  let event = null;
  for (const sample of samples) {
    const exceeds = sample.active!==false && Number.isFinite(sample.fraction) && sample.fraction>0;
    if (!exceeds) {event=null; continue;}
    const time = new Date(sample.time).getTime();
    if (!event || time-event.lastTime!==hourMs) {
      event = {start:sample.time,end:sample.time,lastTime:time,peak:sample.fraction};
      events.push(event);
    } else {
      event.end=sample.time; event.lastTime=time; event.peak=Math.max(event.peak,sample.fraction);
    }
  }
  return events;
}

function renderThresholds(location, rows) {
  const events = [];
  $('thresholds').innerHTML = location.thresholds.map(threshold => {
    const state = thresholdState(threshold,rows);
    for (const event of exceedanceEvents(state.samples)) events.push({...event,threshold,state});
    const crossed=state.available.filter(s=>s.fraction>0);
    const peak=crossed.length?crossed.reduce((best,s)=>s.fraction>best.fraction?s:best):null;
    const n=peak?rows.find(r=>r.time===peak.time).n_estimates:0;
    const message=state.max===null?'Confronto non applicabile o dati non disponibili':!crossed.length?'Quota non raggiunta negli scenari disponibili':`L’acqua potrebbe raggiungere questa quota in ${crossed.length} ore del periodo.`;
    return `<article class="threshold-explained"><div class="threshold-level">${num(threshold.elevation_m)}<span class="small"> m</span></div><div><h3>${esc(assetName(threshold))}</h3><p>${esc(message)}</p><p class="threshold-season">${esc(state.season)}</p>${peak?`<p class="small">Massima concordanza: <strong>${Math.round(peak.fraction*n)} scenari su ${n}</strong> alle ${esc(local(peak.time))}. ${state.samples.some(s=>s.active===null)?'Confronto stagionale indicativo.':''}</p>`:''}<details><summary>Come leggere questa soglia</summary><p>Se il livello totale dell’acqua supera ${num(threshold.elevation_m)} m rispetto al riferimento usato, può essere raggiunta la quota associata a ${esc(assetName(threshold).toLowerCase())}. La posizione reale e l’estensione degli allagamenti richiedono quote e profili locali verificati.</p>${state.max!==null?`<p>Frazione massima degli scenari sopra soglia: ${num(state.max*100,0)}%. È un confronto fra calcoli, non una probabilità di allagamento.</p>`:''}</details></div></article>`;
  }).join('');
  $('events').innerHTML = events.length ? `<h3 class="event-title">Finestre di possibile interessamento</h3><p class="small muted">Prima e ultima ora con almeno uno scenario sopra quota. Le righe estive con calendario da definire sono confronti indicativi.</p><div class="events-wrap"><table class="events-table"><thead><tr><th>Struttura e quota</th><th>Inizio (Italia)</th><th>Ultima ora (Italia)</th><th>Concordanza massima</th></tr></thead><tbody>${events.sort((a,b)=>new Date(a.start)-new Date(b.start)).map(event=>`<tr><td>${esc(assetName(event.threshold))} · ${num(event.threshold.elevation_m)} m${event.threshold.season==='summer'?' · estiva':''}</td><td>${esc(local(event.start))}</td><td>${esc(local(event.end))}</td><td>${num(event.peak*100,0)}% degli scenari</td></tr>`).join('')}</tbody></table></div>` : '<p class="small muted">Nessun superamento nelle soglie applicabili e nei campioni orari disponibili.</p>';
}

function chartLayout(yTitle, x, height=350) {
  const ticks=x.filter((_,index)=>index%12===0);
  return {height,margin:{l:52,r:30,t:20,b:85},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'DM Sans, Arial, sans-serif',color:'#637775',size:11},hovermode:'closest',showlegend:true,legend:{orientation:'h',y:-.25,x:0,font:{size:10}},xaxis:{type:'date',title:{text:'Ora italiana · Europe/Rome',font:{size:10}},showgrid:false,tickvals:ticks,ticktext:ticks.map(t=>local(t)),automargin:true},yaxis:{title:{text:yTitle,font:{size:11}},gridcolor:'#e8ede5',zerolinecolor:'#c7d5c5',rangemode:'tozero'},hoverlabel:{font:{family:'DM Sans, Arial, sans-serif',size:11}}};
}
const plotOptions = {responsive:true,displaylogo:false,modeBarButtonsToRemove:['select2d','lasso2d'],toImageButtonOptions:{format:'png',filename:'onde-a-riva'}};

function renderCharts(location, rows) {
  $('threshold-key').innerHTML=location.thresholds.map((t,i)=>`<div style="--threshold-color:${thresholdColors[i%thresholdColors.length]}"><span class="threshold-swatch"></span><strong>${num(t.elevation_m)} m</strong><span>${esc(assetName(t))}${t.season==='summer'?' · estiva':''}</span></div>`).join('');
  if (!window.Plotly) {
    for (const id of ['twl-chart','wave-chart','sealevel-chart']) $(id).innerHTML='<p class="muted">Grafico non disponibile. Le tabelle e il download CSV restano accessibili.</p>';
    return;
  }
  const x = rows.map(row=>new Date(row.time).getTime());
  const text=rows.map(row=>local(row.time));
  const line = (key,name,color,width=1,extra={}) => ({x,text,y:rows.map(r=>r[key]),name,type:'scatter',mode:'lines',connectgaps:false,line:{color,width},hovertemplate:'%{text}<br>%{y:.2f} m<extra>'+name+'</extra>',...extra});
  const traces = [
    line('twl_p05_m','5–95%','#dbe7d5',0,{showlegend:false,hoverinfo:'skip'}),
    line('twl_p95_m','5–95%','#dbe7d5',0,{fill:'tonexty',fillcolor:'#e5eddf',hoverinfo:'skip'}),
    line('twl_p25_m','25–75%','#99b690',0,{showlegend:false,hoverinfo:'skip'}),
    line('twl_p75_m','25–75%','#99b690',0,{fill:'tonexty',fillcolor:'#b9cfad',hoverinfo:'skip'}),
    line('twl_min_m','Minimo','#93a99b',1,{line:{color:'#93a99b',width:1,dash:'dot'}}),
    line('twl_max_m','Massimo','#93a99b',1,{line:{color:'#93a99b',width:1,dash:'dot'}}),
    line('twl_mean_m','Media degli scenari','#194e4c',2.5)
  ];
  location.thresholds.forEach((t,i)=>traces.push({x,y:rows.map(()=>t.elevation_m),name:assetName(t),showlegend:false,mode:'lines',line:{color:thresholdColors[i%thresholdColors.length],width:1,dash:'dash'},hovertemplate:`${esc(assetName(t))}: ${num(t.elevation_m)} m<extra></extra>`}));
  const layout = chartLayout('Livello totale [m; riferimento provvisorio]',x);
  layout.legend.font.size=9;
  Plotly.react('twl-chart',traces,layout,plotOptions);
  const waveLayout=chartLayout('Hs [m]',x);
  waveLayout.margin.r=48;
  waveLayout.yaxis2={title:{text:'Tp [s]',font:{size:11}},overlaying:'y',side:'right',showgrid:false,rangemode:'tozero'};
  const waveTraces=[
    {x,text,y:rows.map(r=>r.hs_m),name:'Hs [m]',mode:'lines',line:{color:'#194e4c',width:2},fill:'tozeroy',fillcolor:'#e6eddf',customdata:rows.map(r=>r.direction_deg),hovertemplate:'%{text}<br>Hs: %{y:.2f} m<br>Provenienza: %{customdata:.0f}°<extra></extra>'},
    {x,text,y:rows.map(r=>r.tp_s),name:'Tp [s]',mode:'lines',yaxis:'y2',line:{color:'#c49b54',width:2},hovertemplate:'%{text}<br>Tp: %{y:.1f} s<extra></extra>'}
  ];
  if (location.climatology?.status==='available') {
    for (const [key,label,color] of [['p95_m','95° percentile storico','#a6a15c'],['p99_m','99° percentile storico','#bd784f']]) {
      waveTraces.push({x,y:rows.map(()=>location.climatology[key]),name:label,mode:'lines',line:{color,width:1,dash:'dot'},hovertemplate:label+': %{y:.2f} m<extra></extra>'});
    }
  }
  Plotly.react('wave-chart',waveTraces,waveLayout,plotOptions);
  const seaLayout=chartLayout('Livello marino [m sul riferimento medio]',x,260);
  Plotly.react('sealevel-chart',[{x,text,y:rows.map(r=>r.water_level_m),name:'Livello del mare',mode:'lines',line:{color:'#426b96',width:2},fill:'tozeroy',fillcolor:'#e2eaf2',hovertemplate:'%{text}<br>Livello del mare: %{y:.2f} m<extra></extra>'}],seaLayout,plotOptions);
}

function renderClimate(location,rows) {
  const climate=location.climatology;
  if (!climate || climate.status!=='available') {
    $('climate-summary').innerHTML='<h3>Quanto sono insolite queste onde?</h3><p>Il confronto con la climatologia ERA5 non è ancora disponibile per questa località. Le onde previste sono già consultabili; il riferimento storico verrà aggiunto dopo la preparazione della serie locale.</p>';
    return;
  }
  const valid=rows.filter(r=>Number.isFinite(r.hs_percentile));
  const peak=valid.length?valid.reduce((best,r)=>r.hs_percentile>best.hs_percentile?r:best):null;
  $('climate-summary').innerHTML=`<h3>Quanto sono insolite queste onde?</h3>${peak?`<p>Al picco, l’altezza prevista di <strong>${num(peak.hs_m)} m</strong> è pari o superiore al <strong>${num(peak.hs_percentile,1)}%</strong> delle altezze nella serie ${esc(climate.source)}.</p>`:'<p>Confronto non disponibile nelle ore selezionate.</p>'}<p class="small">Riferimento ${new Date(climate.start).getUTCFullYear()}–${new Date(climate.end).getUTCFullYear()}, tutte le stagioni e direzioni. Il 95° percentile è ${num(climate.p95_m)} m; il 99° è ${num(climate.p99_m)} m. Massimo storico osservato: ${num(climate.max_hs_m)} m. Copertura dei campioni nel periodo: ${num(climate.coverage_fraction*100,1)}%.</p><p class="small muted">${esc(climate.comparison_note)}</p>`;
}

function renderDetail(slug) {
  const location=bulletin.locations[slug];
  const rows=windowRows(location);
  document.title=`${location.name} · Onde a riva`;
  $('location-title').textContent=location.name;
  $('area').textContent=location.area;
  $('water-level-title').textContent=bulletin.mode==='demo'?'Livello marino dimostrativo':'Onde + livello marino Copernicus';
  $('water-level-note').textContent=bulletin.mode==='demo'?'Onde e livello marino sono sintetici nell’anteprima. La previsione reale userà il livello Copernicus con marea inclusa; il riferimento delle quote resta da validare.':bulletin.water_level.description;
  $('sealevel-caption').textContent=bulletin.mode==='demo'?'Esempio sintetico del contributo del livello marino, sommato al runup. Non è una previsione di marea.':'Livello marino Copernicus (zos), con marea del modello, riferito alla superficie media fissa e alla correzione locale configurata. Non viene sottratta la media dei giorni di previsione.';
  $('download').href=location.csv;
  const valid=rows.filter(r=>Number.isFinite(r.twl_max_m));
  const futureEnd=Math.floor(Date.now()/hourMs)*hourMs + bulletin.display_hours*hourMs;
  const insufficient = new Date(location.valid_to).getTime()<futureEnd;
  const invalid=rows.filter(r=>!r.n_estimates).length;
  setNotice(!rows.length ? 'Bollettino scaduto: nessun campione futuro disponibile. È necessario un aggiornamento.' : `${insufficient?'Copertura parziale: non sono disponibili tutte le prossime 96 ore. ':''}${invalid?`${invalid} ore senza risultati validi dei modelli.`:''}`);
  $('period').textContent=rows.length ? `${local(rows[0].time)} — ${local(rows[rows.length-1].time)} · ${rows.length} campioni orari · ora italiana` : 'Nessuna previsione futura disponibile';
  const peak=valid.length ? valid.reduce((best,row)=>row.twl_max_m>best.twl_max_m?row:best) : null;
  const hs=rows.length ? Math.max(...rows.map(r=>r.hs_m)) : null;
  $('metrics').innerHTML=[
    ['Massimo livello totale stimato',`${num(peak?.twl_max_m)} <small>m</small>`,peak ? `Scenario superiore · ${local(peak.time)} · quote provvisorie` : 'Dati non disponibili'],
    ['Massima altezza delle onde',`${num(hs)} <small>m</small>`,'Hs nel punto offshore'],
    ['Modelli con risultati validi',`${location.valid_models.length} <small>/ ${bulletin.model_order.length}</small>`,`${location.slopes.length} pendenze illustrative · numero di scenari variabile`]
  ].map(([label,value,note])=>`<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${value}</div><div class="metric-note">${esc(note)}</div></div>`).join('');
  renderDaily(location,rows);
  renderClimate(location,rows);
  renderThresholds(location,rows);
  $('parameters').innerHTML=`<dl><dt>Pendenze β</dt><dd>${location.slopes.map(s=>num(s,3)).join(' · ')} (valori illustrativi)</dd><dt>Rugosità</dt><dd>${num(location.roughness_m,4)} m</dd><dt>Punto offshore richiesto</dt><dd>${num(location.wave_point.latitude,5)}° N, ${num(location.wave_point.longitude,5)}° E</dd><dt>Cella estratta</dt><dd>${location.source.selected_point ? esc(JSON.stringify(location.source.selected_point)) : 'Non applicabile ai dati dimostrativi'}</dd><dt>Modelli disponibili</dt><dd>${esc(location.valid_models.join('; '))}</dd><dt>Senza risultati validi</dt><dd>${esc(location.missing_models.join('; ')||'Nessuno')}</dd><dt>Motore di calcolo</dt><dd>${esc(bulletin.model_backend)}</dd><dt>Riferimento verticale</dt><dd>SSH meno superficie media fissa del modello, più correzione locale. Raccordo con il livello medio mare locale da validare.</dd><dt>Note della località</dt><dd>${esc(location.notes)}</dd><dt>Download CSV</dt><dd>Contiene tutti gli scenari sull’intero periodo scaricato (120 ore); tempi in UTC.</dd></dl>`;
  renderCharts(location,rows);
}

function renderRoute() {
  const slug=new URL(location.href).searchParams.get('localita');
  const selected=slug && Object.hasOwn(bulletin.locations,slug);
  $('home').hidden=!!selected;
  $('detail').hidden=!selected;
  if (selected) renderDetail(slug);
  else {
    document.title='Onde a riva · Previsioni locali';
    setNotice(slug ? 'Località non trovata: scegli una delle aree disponibili.' : '');
    locationCards(); setupMap();
    if (map) setTimeout(()=>map.invalidateSize(),0);
  }
}

async function boot() {
  try {
    const response=await fetch(`data/forecast.json?t=${Math.floor(Date.now()/300000)}`,{cache:'no-cache'});
    if (!response.ok) throw new Error('Bollettino non disponibile');
    bulletin=await response.json();
    if (bulletin.schema_version!==1 || !bulletin.locations || !['demo','copernicus'].includes(bulletin.mode)) throw new Error('Formato del bollettino non riconosciuto');
    $('updated').textContent=`Ultima elaborazione: ${local(bulletin.generated_at)} · Italia`;
    $('model-references').innerHTML=bulletin.model_order.map(name=>`<p>${esc(bulletin.citations[name]||name)}</p>`).join('');
    document.addEventListener('click',event=>{
      const link=event.target.closest('a[href]');
      if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button!==0) return;
      const url=new URL(link.href);
      if (url.origin===location.origin && url.pathname===location.pathname && !url.hash && !link.hasAttribute('download')) {
        event.preventDefault(); navigate(url.searchParams.get('localita'));
      }
    });
    window.addEventListener('popstate',renderRoute);
    // Refresh the rolling display for tabs left open; never silently extend expired data.
    setInterval(renderRoute,5*60*1000);
    renderRoute();
  } catch (error) {
    $('notice').className='notice error';
    $('notice').textContent='Bollettino non disponibile. Il primo aggiornamento potrebbe non essere stato ancora pubblicato. Riprova più tardi.';
    console.error(error.message);
  }
}
boot();
