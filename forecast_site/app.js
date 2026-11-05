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


function dateInWords(value) {
  return new Date(value).toLocaleDateString('it-IT',{timeZone:'Europe/Rome',day:'numeric',month:'long'});
}

function wavePeak(rows) {
  return rows.filter(row=>Number.isFinite(row.hs_m)).reduce((best,row)=>!best || row.hs_m>best.hs_m ? row : best,null);
}

function directionLabel(degrees) {
  if (!Number.isFinite(degrees)) return 'direzione non disponibile';
  const angle=((degrees%360)+360)%360;
  const names=['Nord','Nord-est','Est','Sud-est','Sud','Sud-ovest','Ovest','Nord-ovest'];
  return `${names[Math.round(angle/45)%8]} (${num(angle,0)}°)`;
}

function isExposed(degrees, exposure) {
  const sectors=exposure?.sectors_deg;
  if (!Number.isFinite(degrees) || !Array.isArray(sectors) || !sectors.length) return null;
  const angle=((degrees%360)+360)%360;
  return sectors.some(([start,end])=>end-start===360 || ((angle-start+360)%360)<=(end-start+360)%360);
}

function exposureAtPeak(location, rows) {
  const peak=wavePeak(rows);
  if (!peak || peak.hs_m<=0) return {peak,status:null,text:'Direzione non valutabile nelle ore con altezza delle onde nulla o mancante.'};
  const status=isExposed(peak.direction_deg,location.wave_exposure);
  const prefix=`Al picco delle onde al largo: ${directionLabel(peak.direction_deg)}.`;
  return {peak,status,text:prefix+' '+(status===false?'Provenienza fuori dai settori di esposizione configurati: il risultato a riva richiede cautela.':status===true?'Provenienza compresa nei settori di esposizione configurati.':'Esposizione della spiaggia o direzione non ancora definita.')};
}

function renderExposure(location, rows) {
  const result=exposureAtPeak(location,rows);
  const available=rows.filter(row=>row.hs_m>0 && Number.isFinite(row.direction_deg));
  const outside=available.filter(row=>isExposed(row.direction_deg,location.wave_exposure)===false).length;
  const configured=!!location.wave_exposure?.sectors_deg?.length;
  $('direction-summary').innerHTML=`<h3>Le onde al largo raggiungono questa spiaggia?</h3><p>${esc(result.text)}</p>${!configured?'<p>Per questa località i settori di esposizione della spiaggia non sono ancora definiti. Onde alte al largo possono avere effetti diversi su una spiaggia esposta o riparata.</p>':''}${outside?`<p>La provenienza è fuori settore in <strong>${outside} ${outside===1?'ora':'ore'} su ${available.length}</strong> con altezza e direzione disponibili.</p>`:''}${location.wave_exposure?.note?`<p>${esc(location.wave_exposure.note)}</p>`:''}<p class="small muted">Runup e TWL sono calcolati senza correzioni per la direzione. I settori sono un’indicazione di esposizione: non simulano rifrazione, diffrazione o riparo e non garantiscono l’assenza di onde sulla spiaggia.</p>`;
}

function climateFrequency(percentile, stepHours) {
  const tail=Math.max(0,Math.min(100,100-percentile));
  const unit=stepHours===1?'ore':'campioni';
  if (tail===0) return 'Nella serie storica non compaiono onde più alte di questa.';
  if (tail<1) return `Nella serie storica, meno di ${stepHours===1?'un’ora':'un campione'} su 100 presenta onde più alte di questa.`;
  return `Nella serie storica, circa ${num(tail,tail<10?1:0)} ${unit} su 100 presentano onde più alte di questa.`;
}


function seaLevelReference(location) {
  const meta=location.sea_level_source||{};
  if (bulletin?.mode==='demo' || meta.reference_source==='synthetic') return {label:'riferimento sintetico',axis:'riferimento sintetico',caption:'Onde e livello marino sono sintetici: non sono una previsione.',detail:'Lo zero appartiene al segnale sintetico usato per la dimostrazione.'};
  if (meta.mode==='constant_msl') return {label:'livello medio mare assunto',axis:'livello medio assunto',caption:`Contributo del livello marino fissato a ${num(meta.offset_m)} m rispetto al livello medio assunto.`,detail:'Questa configurazione usa un livello costante; non rappresenta una previsione di marea o di variazioni meteorologiche.'};
  const ref=meta.historical_reference||location.sea_level_reference;
  if (ref?.kind==='copernicus_historical_mean') {
    return {label:`media Copernicus ${ref.year}`,axis:`zero = media ${ref.year}`,
      caption:`Lo zero è la media del livello del mare del modello Copernicus nell’intero ${ref.year}, mantenuta fissa per tutti gli aggiornamenti. Il segnale comprende la marea e le variazioni atmosferiche e oceanografiche. Il raccordo con le quote locali rimane da verificare.`,
      detail:`Media calcolata su ${num(ref.n_records,0)} ore, dal 1 gennaio al 31 dicembre ${ref.year}, nella cella ${num(ref.selected_point.latitude,5)}° N, ${num(ref.selected_point.longitude,5)}° E. Media della SSH originale: ${num(ref.mean_ssh_m,4)} m; versione del prodotto: ${ref.dataset_version}. Correzione locale aggiuntiva: ${num(location.datum_offset_m||0)} m.`};
  }
  if (location.mean_reference_m!==undefined && location.mean_reference_m!==null) return {label:'riferimento fisso configurato',axis:'riferimento fisso',caption:'Livello marino Copernicus riferito al valore fisso configurato per la località. Il raccordo con le quote locali rimane da verificare.',detail:`Riferimento SSH configurato: ${num(location.mean_reference_m,4)} m. Correzione locale: ${num(location.datum_offset_m||0)} m.`};
  return {label:'MDT Copernicus provvisoria',axis:'zero = MDT provvisoria',caption:'Lo zero deriva dalla superficie media dinamica (MDT) del prodotto Copernicus. Non è un riferimento del livello medio mare locale verificato. Marea e altre variazioni del modello sono comprese nel segnale.',detail:'Il riferimento MDT va verificato o sostituito con un riferimento storico documentato della stessa cella. La differenza dalle quote locali non è ancora calibrata.'};
}

function noticeDate(value) {
  if (!Number.isFinite(Date.parse(value))) return 'data non disponibile';
  return new Date(value).toLocaleString('it-IT',{timeZone:'Europe/Rome',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
}

function nextWavePublication(now=Date.now()) {
  const configured=bulletin.wave_model?.publication_hours_utc;
  const fallback=bulletin.source?.product_id==='MEDSEA_ANALYSISFORECAST_WAV_006_017'?[6,20]:[];
  const hours=(configured||fallback).filter(h=>Number.isInteger(h)&&h>=0&&h<24).sort((a,b)=>a-b);
  const today=new Date(now);
  for (let day=0;day<2;day++) {
    for (const hour of hours) {
      const time=Date.UTC(today.getUTCFullYear(),today.getUTCMonth(),today.getUTCDate()+day,hour);
      if (time>now) return new Date(time).toISOString();
    }
  }
  return null;
}

function noticeWaveSource(location=null) {
  const sources=location?[location.source||{}]:Object.values(bulletin.locations||{}).map(loc=>loc.source||{});
  const reference=sources.map(src=>src.forecast_reference_time).filter(value=>Number.isFinite(Date.parse(value)));
  if (reference.length===sources.length && reference.length && new Set(reference).size===1) return {kind:'cycle',time:reference[0]};
  return reference.length===sources.length && reference.length?{kind:'mixed'}:{kind:'unknown'};
}

function setNotice(extra='',location=null,now=Date.now()) {
  const demo = bulletin.mode === 'demo';
  const age = (now-new Date(bulletin.generated_at))/hourMs;
  $('notice').className = `notice${demo ? ' demo' : ''}`;
  const source=noticeWaveSource(location);
  const next=nextWavePublication(now);
  const sourceText=source.kind==='cycle'?`Corsa del modello Copernicus del <strong>${esc(noticeDate(source.time))}</strong>`:source.kind==='mixed'?'Corse del modello Copernicus diverse: consultare la singola località':'Corsa del modello Copernicus non disponibile in questo bollettino';
  const message=demo?`<strong>Modalità dimostrativa.</strong> Elaborazione del ${esc(noticeDate(bulletin.generated_at))}. Onde e livello del mare sintetici.`:`Elaborazione del <strong>${esc(noticeDate(bulletin.generated_at))}</strong>. ${sourceText}.${next?` Prossima uscita prevista: <strong>${esc(noticeDate(next))}</strong> (ora italiana).`:' Orari italiani.'}`;
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
    const date=new Date(group[0].time).toLocaleDateString('it-IT',{timeZone:'Europe/Rome',weekday:'long',day:'numeric',month:'long'});
    const intervals=result.focus?exceedanceEvents(result.focus.samples):[];
    const window=intervals.length?intervals.map(event=>`${local(event.start,{day:undefined,month:undefined})}–${local(event.end,{day:undefined,month:undefined})}`).join(' · '):'Nessuna fascia di superamento delle soglie attive';
    return `<article class="day-card impact-day"><h3>${esc(date)}</h3><div class="day-impact">${esc(result.title)}</div><p>${esc(result.explanation)}</p><div class="day-time">${esc(window)}</div><p class="day-range">Livello massimo degli scenari: <strong>${num(maximum)} m</strong>${peak?` · picco alle ${local(peak.time,{day:undefined,month:undefined})}`:''}</p>${result.upperNote?`<p>${esc(result.upperNote)}</p>`:''}<p class="direction-day">${esc(exposureAtPeak(location,group).text)}</p>${result.seasonal.length?'<p class="season-note">Ombrelloni / strutture stagionali: calendario da definire.</p>':''}<p>${group.length} ore disponibili${group.length<24?' · giornata parziale':''}${valid.length<group.length?' · alcuni risultati mancanti':''}</p></article>`;
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
    return `<article class="threshold-explained"><div class="threshold-level">${num(threshold.elevation_m)}<span class="small"> m</span></div><div><h3>${esc(assetName(threshold))}</h3><p>${esc(message)}</p><p class="threshold-season">${esc(state.season)}</p>${peak?`<p class="small">Il ${esc(dateInWords(peak.time))}, alle ${esc(local(peak.time,{day:undefined,month:undefined}))}, <strong>${Math.round(peak.fraction*n)} ${Math.round(peak.fraction*n)===1?'scenario':'scenari'} su ${n}</strong> ${Math.round(peak.fraction*n)===1?'supera':'superano'} questa quota. ${state.samples.some(s=>s.active===null)?'Confronto stagionale indicativo.':''}</p>`:''}<details><summary>Come leggere questa soglia</summary><p>Se il livello totale dell’acqua supera ${num(threshold.elevation_m)} m rispetto al riferimento usato, può essere raggiunta la quota associata a ${esc(assetName(threshold).toLowerCase())}. La posizione reale e l’estensione degli allagamenti richiedono quote e profili locali verificati.</p>${state.max!==null?`<p>Ogni scenario combina un modello e una pendenza della spiaggia. Nel momento con più superamenti, il ${num(state.max*100,0)}% dei calcoli supera la quota. Questa percentuale non è una probabilità di allagamento.</p>`:''}</details></div></article>`;
  }).join('');
  $('events').innerHTML = events.length ? `<h3 class="event-title">Finestre di possibile interessamento</h3><p class="small muted">Prima e ultima ora con almeno uno scenario sopra quota. Le righe estive con calendario da definire sono confronti indicativi.</p><div class="events-wrap"><table class="events-table"><thead><tr><th>Struttura e quota</th><th>Inizio (Italia)</th><th>Ultima ora (Italia)</th><th>Scenari sopra la quota (massimo)</th></tr></thead><tbody>${events.sort((a,b)=>new Date(a.start)-new Date(b.start)).map(event=>`<tr><td>${esc(assetName(event.threshold))} · ${num(event.threshold.elevation_m)} m${event.threshold.season==='summer'?' · estiva':''}</td><td>${esc(local(event.start))}</td><td>${esc(local(event.end))}</td><td>${num(event.peak*100,0)}% degli scenari</td></tr>`).join('')}</tbody></table></div>` : '<p class="small muted">Nessun superamento nelle soglie applicabili e nei campioni orari disponibili.</p>';
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
  const layout = chartLayout(`Livello totale [m; ${seaLevelReference(location).axis}]`,x);
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
  const seaLayout=chartLayout(`Livello del mare [m; ${seaLevelReference(location).axis}]`,x,260);
  Plotly.react('sealevel-chart',[{x,text,y:rows.map(r=>r.water_level_m),name:'Livello del mare',mode:'lines',line:{color:'#426b96',width:2},fill:'tozeroy',fillcolor:'#e2eaf2',hovertemplate:'%{text}<br>Livello del mare: %{y:.2f} m<extra></extra>'}],seaLayout,plotOptions);
}

function renderClimate(location,rows) {
  const climate=location.climatology;
  if (!climate || climate.status!=='available') {
    $('climate-summary').innerHTML='<h3>Le onde previste rispetto al passato</h3><p>Per capire se l’altezza al largo è comune o poco frequente serve una serie storica locale. Il riferimento ERA5 non è ancora disponibile per questa località.</p>';
    return;
  }
  const peak=wavePeak(rows.filter(r=>Number.isFinite(r.hs_percentile)));
  const step=climate.time_step_hours;
  $('climate-summary').innerHTML=`<h3>Le onde previste rispetto al passato</h3>${peak?`<div class="climate-comparison"><strong>${num(peak.hs_m)} m</strong><span>Altezza significativa massima al largo<br>Il ${esc(dateInWords(peak.time))}, alle ${esc(local(peak.time,{day:undefined,month:undefined}))}</span></div><p><strong>${esc(climateFrequency(peak.hs_percentile,step))}</strong></p>`:'<p>Il confronto non è disponibile nelle ore selezionate.</p>'}<p>Questo confronto descrive l’altezza al largo in tutte le stagioni e da tutte le direzioni. Non indica quante mareggiate raggiungono la spiaggia, né quanto è probabile un allagamento.</p><details><summary>Dati e metodo del confronto storico</summary><p>Serie ${esc(climate.source)}, ${new Date(climate.start).getUTCFullYear()}–${new Date(climate.end).getUTCFullYear()}, ${num(climate.n_records,0)} campioni${Number.isFinite(step)?`, uno ogni ${num(step,step%1?1:0)} ${step===1?'ora':'ore'}`:''}. Copertura del periodo: ${num(climate.coverage_fraction*100,1)}%.</p><p>Il 95° percentile è ${num(climate.p95_m)} m; il 99° percentile è ${num(climate.p99_m)} m. Sono riferimenti delle altezze superate rispettivamente in circa il 5% e l’1% dei campioni. Massimo storico della serie: ${num(climate.max_hs_m)} m.${peak?` L’altezza prevista corrisponde al percentile ${num(peak.hs_percentile,1)}.`:''}</p><p>${esc(climate.comparison_note)}</p><p>La frequenza delle singole ore non è la frequenza delle mareggiate: ore consecutive possono appartenere allo stesso evento. Non viene stimato un periodo di ritorno.</p></details>`;
}


function extremeComparison(location,rows,sectorId=null) {
  const extremes=location.climatology?.directional_extremes;
  if (!extremes || extremes.status!=='available') return {reason:'Il riferimento storico degli estremi per settore non è ancora disponibile per questa località. Il tempo di ritorno non può essere stimato.'};
  const valid=rows.filter(row=>row.hs_m>0 && row.wave_sector_id);
  const peak=wavePeak(sectorId?valid.filter(row=>row.wave_sector_id===sectorId):valid);
  if (!peak) return {reason:'Nessuna altezza e direzione delle onde utilizzabile nelle ore selezionate.'};
  const sector=extremes.sectors.find(s=>s.id===peak.wave_sector_id);
  if (!sector) return {reason:'Il settore della previsione non è presente nel riferimento storico.'};
  return {extremes,sector,peak,fit:sector.fit};
}

function sectorLabel(sector) {
  if (sector.width_deg===360) return 'Tutte le direzioni (360°)';
  return `${num(sector.start_deg,1)}° → ${num(sector.end_deg,1)}° (centro: ${directionLabel(sector.center_deg)})`;
}

function renderExtremes(location,rows,sectorId=null) {
  const result=extremeComparison(location,rows,sectorId);
  if (result.reason) {
    $('extremes-summary').innerHTML=`<p class="chart-caption">${esc(result.reason)}</p>`;
    return;
  }
  const {extremes,sector,peak,fit}=result;
  const represented=extremes.sectors.filter(s=>rows.some(row=>row.hs_m>0 && row.wave_sector_id===s.id));
  const period=peak.hs_return_period_years;
  const upper=fit.return_period_years?.at(-1)||100;
  const periodText=fit.status!=='available'?'Stima non disponibile per questo settore.':!Number.isFinite(period)||period>upper?`Oltre ${num(upper,0)} anni secondo il fit, fuori dall’intervallo mostrato.`:period<2?'Altezza inferiore al livello con tempo di ritorno di 2 anni in questo settore.':`Tempo di ritorno stimato: circa ${num(period,period<10?1:0)} anni per questo settore.`;
  $('extremes-summary').innerHTML=`<p class="chart-caption">Confronto con i massimi annuali delle onde provenienti dallo stesso settore. La selezione iniziale usa il settore dell’altezza massima nei quattro giorni; scegliendo un altro settore si mostra il suo picco nel periodo.</p><label class="sector-selector" for="extreme-sector">Settore presente nelle onde previste<select id="extreme-sector">${represented.map(s=>`<option value="${esc(s.id)}"${s.id===sector.id?' selected':''}>${esc(sectorLabel(s))}</option>`).join('')}</select></label><p class="extreme-peak"><strong>${num(peak.hs_m)} m al largo</strong> da ${esc(directionLabel(peak.direction_deg))}, il ${esc(dateInWords(peak.time))} alle ${esc(local(peak.time,{day:undefined,month:undefined}))}.</p><p><strong>${esc(periodText)}</strong></p>${fit.status==='available'?'<p class="chart-caption">Asse orizzontale: tempo di ritorno in anni, in scala logaritmica. Punti verdi: massimi annuali storici. Linea: Gumbel stimata. Fascia: incertezza del fit al 95%. Punto arancione: altezza massima prevista nel settore.</p><div id="extreme-chart" class="chart extreme-chart" aria-label="Curva Gumbel dei tempi di ritorno e altezza massima prevista nello stesso settore"></div>':`<p class="chart-caption">${esc(fit.reason||'Serie insufficiente per il fit.')}</p>`}<p class="chart-caption"><strong>Il tempo di ritorno riguarda le onde al largo, non gli allagamenti.</strong> Non significa che un evento si ripeta a intervalli regolari. La spiaggia può essere esposta o riparata: ${esc(exposureAtPeak(location,[peak]).text)}</p>${fit.status==='available'?`<details class="extremes-method"><summary>Metodo, dati e limiti della stima</summary><p>Fit Gumbel per massima verosimiglianza su ${fit.n_years} massimi annuali, ${fit.first_year}–${fit.last_year}. Un massimo per settore e per anno UTC con copertura oraria completa. Gli anni senza onde del settore non vengono rimossi silenziosamente. Settori statistici di ${num(extremes.sector_width_deg,0)}°, separati dai settori di esposizione della spiaggia; inizio incluso e fine esclusa.</p><p>T = 1 / P(massimo annuale del settore &gt; Hs). I punti storici usano le posizioni empiriche (n + 1) / rango. La fascia al 95% deriva da ${fit.bootstrap_replicates} ricampionamenti bootstrap degli anni. Non comprende l’incertezza della previsione, la differenza fra ERA5 e Copernicus o la trasformazione delle onde verso riva.</p><p>Gumbel è un’ipotesi da verificare, con massimi annuali assunti indipendenti e stazionari. Oltre la durata della serie, la curva è un’estrapolazione; il tratto è tratteggiato. Il confronto non applica una correzione dei bias fra prodotti e non costituisce una stima operativa del rischio.</p></details>`:''}`;
  $('extreme-sector').onchange=event=>renderExtremes(location,rows,event.target.value);
  if (fit.status!=='available') return;
  if (!window.Plotly) {
    $('extreme-chart').innerHTML='<p>Grafico non disponibile. La stima e i suoi limiti restano descritti nel testo.</p>';
    return;
  }
  const x=fit.return_period_years;
  const traces=[
    {x,y:fit.ci95_low_m,type:'scatter',mode:'lines',line:{width:0},showlegend:false,hoverinfo:'skip'},
    {x,y:fit.ci95_high_m,type:'scatter',mode:'lines',line:{width:0},fill:'tonexty',fillcolor:'#dce8dd',name:'Incertezza del fit (95%)',hoverinfo:'skip'},
    {x,y:fit.return_level_m.map((y,i)=>x[i]<=fit.n_years?y:null),type:'scatter',mode:'lines',name:'Gumbel',line:{color:'#194e4c',width:2},hovertemplate:'Ritorno: %{x:.1f} anni<br>Hs: %{y:.2f} m<extra>Gumbel</extra>'},
    {x,y:fit.return_level_m.map((y,i)=>x[i]>=fit.n_years?y:null),type:'scatter',mode:'lines',name:'Estrapolazione',line:{color:'#194e4c',width:2,dash:'dash'},hovertemplate:'Ritorno: %{x:.1f} anni<br>Hs: %{y:.2f} m<extra>Estrapolazione</extra>'},
    {x:fit.empirical.map(r=>r.return_period_years),y:fit.empirical.map(r=>r.hs_m),customdata:fit.empirical.map(r=>r.year),type:'scatter',mode:'markers',name:'Massimi annuali storici',marker:{color:'#678973',size:6},hovertemplate:'Anno: %{customdata}<br>Hs: %{y:.2f} m<br>Ritorno empirico: %{x:.1f} anni<extra></extra>'},
    {x:[Number.isFinite(period)?Math.min(period,upper):upper],y:[peak.hs_m],type:'scatter',mode:'markers',name:period>upper||!Number.isFinite(period)?'Picco previsto (oltre il grafico)':'Picco previsto nel settore',marker:{color:'#b86b30',size:12,symbol:period>upper||!Number.isFinite(period)?'triangle-right':'diamond'},hovertemplate:'Hs prevista: %{y:.2f} m<extra>Picco del settore nei quattro giorni</extra>'}
  ];
  const layout={height:390,margin:{l:58,r:22,t:20,b:100},paper_bgcolor:'transparent',plot_bgcolor:'transparent',separators:',.',font:{family:'DM Sans, Arial',size:11,color:'#294b42'},xaxis:{title:'Tempo di ritorno [anni]',type:'log',range:[0,Math.log10(upper)],tickvals:[1,2,5,10,20,50,100],gridcolor:'#e5ebe2'},yaxis:{title:'Altezza significativa Hs [m]',rangemode:'nonnegative',gridcolor:'#e5ebe2'},legend:{orientation:'h',y:-.26,font:{size:9}},hovermode:'closest'};
  Plotly.react('extreme-chart',traces,layout,plotOptions);
}

function renderDetail(slug) {
  const location=bulletin.locations[slug];
  const rows=windowRows(location);
  document.title=`${location.name} · Onde a riva`;
  $('location-title').textContent=location.name;
  $('area').textContent=location.area;
  $('water-level-title').textContent=bulletin.mode==='demo'?'Livello marino dimostrativo':'Onde + livello marino Copernicus';
  const reference=seaLevelReference(location);
  $('water-level-note').textContent=reference.caption;
  $('twl-reference-label').textContent=`metri · zero: ${reference.label}`;
  $('sealevel-caption').textContent=reference.caption;
  $('reference-description').textContent=reference.detail;
  $('download').href=location.csv;
  const valid=rows.filter(r=>Number.isFinite(r.twl_max_m));
  const futureEnd=Math.floor(Date.now()/hourMs)*hourMs + bulletin.display_hours*hourMs;
  const insufficient = new Date(location.valid_to).getTime()<futureEnd;
  const invalid=rows.filter(r=>!r.n_estimates).length;
  setNotice(!rows.length ? 'Bollettino scaduto: nessun campione futuro disponibile. È necessario un aggiornamento.' : `${insufficient?'Copertura parziale: non sono disponibili tutte le prossime 96 ore. ':''}${invalid?`${invalid} ore senza risultati validi dei modelli.`:''}`,location);
  $('period').textContent=rows.length ? `${local(rows[0].time)} — ${local(rows[rows.length-1].time)} · ${rows.length} campioni orari · ora italiana` : 'Nessuna previsione futura disponibile';
  const peak=valid.length ? valid.reduce((best,row)=>row.twl_max_m>best.twl_max_m?row:best) : null;
  const hs=rows.length ? Math.max(...rows.map(r=>r.hs_m)) : null;
  $('metrics').innerHTML=[
    ['Massimo livello totale stimato',`${num(peak?.twl_max_m)} <small>m</small>`,peak ? `Scenario superiore · ${local(peak.time)} · quote provvisorie` : 'Dati non disponibili'],
    ['Massima altezza delle onde',`${num(hs)} <small>m</small>`,'Hs nel punto offshore'],
    ['Modelli con risultati validi',`${location.valid_models.length} <small>/ ${bulletin.model_order.length}</small>`,`${location.slopes.length} pendenze configurate · numero di scenari variabile`]
  ].map(([label,value,note])=>`<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${value}</div><div class="metric-note">${esc(note)}</div></div>`).join('');
  renderExposure(location,rows);
  renderDaily(location,rows);
  renderClimate(location,rows);
  renderExtremes(location,rows);
  renderThresholds(location,rows);
  $('parameters').innerHTML=`<dl><dt>Pendenze β</dt><dd>${location.slopes.map(s=>num(s,3)).join(' · ')} (valori configurati)</dd><dt>Rugosità</dt><dd>${num(location.roughness_m,4)} m</dd><dt>Punto offshore richiesto</dt><dd>${num(location.wave_point.latitude,5)}° N, ${num(location.wave_point.longitude,5)}° E</dd><dt>Cella estratta</dt><dd>${location.source.selected_point ? esc(JSON.stringify(location.source.selected_point)) : 'Non applicabile ai dati dimostrativi'}</dd><dt>Modelli disponibili</dt><dd>${esc(location.valid_models.join('; '))}</dd><dt>Senza risultati validi</dt><dd>${esc(location.missing_models.join('; ')||'Nessuno')}</dd><dt>Motore di calcolo</dt><dd>${esc(bulletin.model_backend)}</dd><dt>Settori di esposizione</dt><dd>${location.wave_exposure?.sectors_deg?.length?esc(location.wave_exposure.sectors_deg.map(([a,b])=>`${num(a,0)}° → ${num(b,0)}° in senso orario`).join('; ')):'Da definire'}</dd><dt>Riferimento verticale</dt><dd>${esc(reference.label)}. ${esc(reference.detail)}</dd><dt>Note della località</dt><dd>${esc(location.notes)}</dd><dt>Download CSV</dt><dd>Contiene tutti gli scenari sull’intero periodo scaricato (120 ore); tempi in UTC.</dd></dl>`;
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
