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
    const valid=rows.filter(r=>hasFilteredStatistics(r) && Number.isFinite(r.twl_p95_m));
    const maximum=valid.length?Math.max(...valid.map(r=>r.twl_p95_m)):NaN;
    return `<a class="location-card" href="?localita=${encodeURIComponent(slug)}"><div><div class="card-top"><span class="card-index">LOCALITÀ / 0${index+1}</span><span class="card-arrow" aria-hidden="true">↗</span></div><h3>${esc(location.name)}</h3><p>${esc(location.area)}</p></div><div class="card-bottom"><span>${valid.length ? `Fascia alta filtrata (P95): <strong>${num(maximum)} m</strong>` : rows.length?'Statistiche filtrate da aggiornare':'Nessun dato futuro disponibile'}</span><span>Esplora le previsioni →</span></div></a>`;
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

const impactLevels=[
  {key:'white',name:'Bianco',label:'P95 non supera la quota',title:'Nelle ore frontali, la fascia alta non supera la quota'},
  {key:'yellow',name:'Giallo',label:'P95 supera la quota',title:'Nelle ore frontali, la fascia alta supera la quota'},
  {key:'orange',name:'Arancione',label:'Anche P75 supera la quota',title:'Nelle ore frontali, anche P75 supera la quota'}
];

function percentage(fraction) {
  if (!Number.isFinite(fraction)) return '—';
  if (fraction>0 && fraction<.001) return '<0,1%';
  if (fraction<1 && fraction>.999) return '>99,9%';
  const value=fraction*100;
  return `${num(value,Math.abs(value-Math.round(value))<1e-8?0:1)}%`;
}

function timeOnly(value) {
  return new Date(value).toLocaleTimeString('it-IT',{timeZone:'Europe/Rome',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
}

function hasFilteredStatistics(row) {
  return row.statistics_method==='sigma_clip_3_population_v1';
}


function forecastExposure(location,row) {
  return row.hs_m>0?isExposed(row.direction_deg,location?.wave_exposure):null;
}


function thresholdState(threshold,rows,location) {
  const original=rows.map(row=>({time:row.time,...row.thresholds?.find(t=>t.id===threshold.id)}));
  const samples=original.map((sample,i)=>({...sample,
    active:sample.active===false || !hasFilteredStatistics(rows[i]) || forecastExposure(location,rows[i])!==true?false:sample.active,
    above_p95:Number.isFinite(rows[i].twl_p95_m) && rows[i].twl_p95_m>threshold.elevation_m}));
  const available=samples.filter(s=>s.active!==false && Number.isFinite(s.fraction));
  const max=available.length?Math.max(...available.map(s=>s.fraction)):null;
  const season=threshold.season!=='summer'?'Tutto l’anno':original.some(s=>s.active===null)?'Calendario estivo da definire · confronto indicativo':original.some(s=>s.active===true)?'Struttura stagionale · nel periodo estivo':'Fuori stagione · confronto non applicato';
  return {samples,available,max,season};
}

function assetName(threshold) {return threshold.short_label||threshold.description;}

function impactIcon(id) {
  const shapes={
    prima_fila_ombrelloni:'<path d="M3 14a11 11 0 0 1 22 0H3Zm11-11v22c0 3 4 3 4 0M6 14c0-7 4-11 8-11s8 4 8 11M4 29h24"/>',
    strutture_turistiche_stagionali:'<path d="m3 14 8-8 8 8M5 13v15h12V13M9 28v-8h4v8M19 12a5 5 0 0 1 10 0H19Zm5-5v21M2 29h28"/>',
    strutture_turistiche_fisse:'<path d="m3 13 4-7h18l4 7H3Zm3 0v16h20V13M6 19h20M10 19v10M22 19v10M11 6V3h10v3M3 29h26"/>',
    infrastrutture_fisse:'<path d="M3 7h26M5 7v13M13 7v13M21 7v13M29 7v13M3 20h26M3 25c4-4 6 4 10 0s6 4 10 0 6 4 8 0M3 30h26"/>'
  };
  return `<svg class="asset-icon" viewBox="0 0 32 34" width="32" height="34" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[id]||shapes.strutture_turistiche_fisse}</svg>`;
}

function referenceThreshold(location) {return location.thresholds.find(t=>t.id==='strutture_turistiche_fisse')||null;}

function rowImpact(threshold,row,location) {
  const sample=row.thresholds?.find(t=>t.id===threshold?.id);
  const result={rank:null,row,fraction:sample?.fraction??null};
  if (!threshold || !sample || !(row.n_estimates>0) || !Number.isFinite(sample.fraction) || ![row.twl_p75_m,row.twl_p95_m].every(Number.isFinite)) return {...result,kind:'missing'};
  if (!hasFilteredStatistics(row)) return {...result,kind:'unfiltered'};
  if (sample.active===false) return {...result,kind:'inactive'};
  const exposure=location?forecastExposure(location,row):true;
  if (exposure===false) return {...result,kind:'nonfrontal'};
  if (exposure===null) return {...result,kind:'unknown-direction'};
  return {...result,kind:'numeric',rank:row.twl_p75_m>threshold.elevation_m?2:row.twl_p95_m>threshold.elevation_m?1:0};
}

function assessTrend(location,rows,threshold=referenceThreshold(location)) {
  const results=rows.map(row=>rowImpact(threshold,row,location));
  const available=results.filter(r=>r.kind==='numeric');
  const peak=available.reduce((best,r)=>!best || r.rank>best.rank || (r.rank===best.rank && (r.fraction>best.fraction || (r.fraction===best.fraction && r.row.twl_p95_m>best.row.twl_p95_m)))?r:best,null);
  const nonfrontalCount=results.filter(r=>r.kind==='nonfrontal').length;
  const unknownCount=results.filter(r=>['unknown-direction','unfiltered'].includes(r.kind)).length;
  const gray=!peak && nonfrontalCount>0 && !unknownCount;
  const level=peak?impactLevels[peak.rank]:gray?{key:'gray',name:'Grigio',title:'Onde non frontali: categoria non applicata'}:null;
  return {threshold,peak,level,key:level?.key||'unavailable',title:level?.title||'Dati o direzione insufficienti per assegnare una categoria',nonfrontalCount,
    missingCount:results.filter(r=>!['numeric','nonfrontal','inactive'].includes(r.kind)).length};
}

function exposureAtPeak(location,rows) {
  const peak=wavePeak(rows);
  if (!peak || peak.hs_m<=0) return {peak,status:null,text:'La direzione non è valutabile: altezza delle onde nulla o dati mancanti.'};
  const status=isExposed(peak.direction_deg,location.wave_exposure);
  return {peak,status,text:`Le onde più alte arrivano da ${directionLabel(peak.direction_deg)}. `+(status===false?'Non arrivano frontalmente verso questa spiaggia: il loro effetto a riva potrebbe essere minore.':status===true?'Arrivano da una direzione rivolta verso questa spiaggia.':'Il confronto con l’orientamento della spiaggia non è ancora disponibile.')};
}

function directionSummary(location,rows,compact=false) {
  const result=exposureAtPeak(location,rows);
  const key=result.status===false?'away':result.status===true?'toward':'unknown';
  const label=result.status===false?'Onde non frontali':result.status===true?'Onde verso la costa':'Direzione da verificare';
  const available=rows.filter(r=>r.hs_m>0 && isExposed(r.direction_deg,location.wave_exposure)!==null);
  const frontal=available.filter(r=>isExposed(r.direction_deg,location.wave_exposure)).length;
  return `<span class="direction-badge direction-${key}">${esc(label)}</span><p>${esc(result.text)}</p>${!compact && available.length?`<p>Direzione rivolta verso la spiaggia in <strong>${frontal} ${frontal===1?'ora':'ore'} su ${available.length}</strong> con dati disponibili.</p>`:''}${result.status===false?'<p class="small">Questa indicazione non esclude onde sulla spiaggia.</p>':''}`;
}

function impactLegend() {
  return `<div class="impact-legend" aria-label="Legenda dei colori della tendenza">${[...impactLevels,{key:'gray',name:'Grigio',label:'Onde non frontali'}].map(l=>`<div class="legend-item impact-${l.key}"><span class="impact-swatch" aria-hidden="true"></span><span><strong>${l.name}</strong>${l.label}</span></div>`).join('')}</div><p class="legend-note">Percentili dopo il filtro ±3σ, riferiti alla quota dei chioschi. La categoria usa soltanto le ore con onde rivolte verso la costa. <a href="metodo.html#colori">Come leggere colori e percentuali ↗</a></p>`;
}

function exceedanceEvents(samples) {
  const events=[];let event=null;
  for (const sample of samples) {
    if (sample.active===false || !Number.isFinite(sample.fraction) || sample.fraction<=0 || sample.above_p95===false) {event=null;continue;}
    const time=new Date(sample.time).getTime();
    if (!event || time-event.lastTime!==hourMs) {event={start:sample.time,end:sample.time,lastTime:time,peak:sample.fraction};events.push(event);}
    else {event.end=sample.time;event.lastTime=time;event.peak=Math.max(event.peak,sample.fraction);}
  }
  return events;
}

function eventLabel(event,compact=false) {
  if (event.start===event.end) return `${compact?'':dateInWords(event.start)+' · '}${timeOnly(event.start)}`;
  if (italianTime(event.start).slice(0,10)===italianTime(event.end).slice(0,10)) return `${compact?'':dateInWords(event.start)+' · '}${timeOnly(event.start)}–${timeOnly(event.end)}`;
  return `${dateInWords(event.start)}, ${timeOnly(event.start)} → ${dateInWords(event.end)}, ${timeOnly(event.end)}`;
}

function modelAgreement(result) {
  if (result.key==='gray') return 'Il confronto non viene applicato alle ore con onde non frontali. Il livello marino resta da considerare.';
  if (!result.peak) return 'Il confronto richiede statistiche filtrate e direzioni della costa definite.';
  return `Risultati filtrati dei modelli sopra quota (ora frontale): <strong>${esc(percentage(result.peak.fraction))}</strong>.<br><span class="agreement-time">${esc(dateInWords(result.peak.row.time))}, ore ${esc(timeOnly(result.peak.row.time))}.</span>${result.peak.rank===0?' Il 95° percentile non supera la quota.':''}`;
}

function renderDaily(location,rows) {
  const threshold=referenceThreshold(location),trend=assessTrend(location,rows,threshold),days=Math.ceil(bulletin.display_hours/24);
  $('outlook-title').textContent=`Tendenza a ${days} ${days===1?'giorno':'giorni'}`;
  $('outlook-panel').className=`panel outlook-panel impact-${trend.key}`;
  $('outlook').innerHTML=`<div class="trend-content"><div><span class="impact-badge impact-${trend.key}">${esc(trend.level?.name||'Non disponibile')}</span><h3>${esc(trend.title)}</h3><p>Riferimento: <strong>${threshold?esc(assetName(threshold))+' · '+num(threshold.elevation_m)+' m':'quota dei chioschi da definire'}</strong>.</p><p class="model-agreement">${modelAgreement(trend)}</p></div><div class="trend-direction">${directionSummary(location,rows)}</div></div>${impactLegend()}<p class="small muted">${rows.length} ore disponibili su ${bulletin.display_hours}${trend.nonfrontalCount?` · ${trend.nonfrontalCount} ${trend.nonfrontalCount===1?'ora non frontale esclusa':'ore non frontali escluse'} dalla categoria`:''}${trend.missingCount?` · ${trend.missingCount} ${trend.missingCount===1?'ora':'ore'} con confronto incompleto`:''}. Quote delle strutture ancora illustrative. Le percentuali non sono probabilità di allagamento.</p>`;
  $('daily').innerHTML=groupsByDay(rows).map(group=>{
    const r=assessTrend(location,group,threshold),valid=group.filter(row=>hasFilteredStatistics(row) && Number.isFinite(row.twl_p95_m));
    const date=new Date(group[0].time).toLocaleDateString('it-IT',{timeZone:'Europe/Rome',weekday:'long',day:'numeric',month:'long'});
    const intervals=threshold?exceedanceEvents(thresholdState(threshold,group,location).samples):[];
    return `<article class="day-card impact-day impact-${r.key}"><div class="day-heading"><h3>${esc(date)}</h3><span class="impact-badge impact-${r.key}">${esc(r.level?.name||'Non disponibile')}</span></div><div class="day-impact">${esc(r.title)}</div><p>${modelAgreement(r)}</p><p class="day-time">${intervals.length?'Ore con P95 sopra la quota dei chioschi<br><strong>'+intervals.map(e=>esc(eventLabel(e,true))).join(' · ')+'</strong>':r.peak?'Nessuna ora frontale con P95 sopra quota':'Categoria non applicata'}</p><p class="day-range">${r.key==='gray'?'P95 teorico, onde non frontali':'Fascia alta filtrata (P95)'}: <strong>${num(valid.length?Math.max(...valid.map(row=>row.twl_p95_m)):NaN)} m</strong></p><div class="direction-day">${directionSummary(location,group,true)}</div><p class="day-coverage">${group.length} ore disponibili${group.length<24?' · giornata parziale':''}${r.missingCount?' · confronto incompleto':''}${r.nonfrontalCount?` · ${r.nonfrontalCount} ${r.nonfrontalCount===1?'ora non frontale':'ore non frontali'}`:''}</p></article>`;
  }).join('');
}

function renderThresholds(location,rows) {
  $('thresholds').innerHTML=location.thresholds.map(threshold=>{
    const s=thresholdState(threshold,rows,location),r=assessTrend(location,rows,threshold),events=exceedanceEvents(s.samples),crossed=s.available.filter(sample=>sample.above_p95);
    const peak=crossed.reduce((best,sample)=>!best || sample.fraction>best.fraction?sample:best,null);
    const message=r.key==='gray'?'Onde non frontali: confronto con le strutture non applicato. Il livello marino resta da considerare.':s.max===null?'Confronto non disponibile o non applicabile nel periodo.':!crossed.length?'Il 95° percentile non supera la quota nelle ore frontali disponibili.':`P95 sopra quota in ${crossed.length} ${crossed.length===1?'ora':'ore'} con onde frontali.`;
    return `<article class="threshold-explained impact-${r.key}"><div class="impact-asset">${impactIcon(threshold.id)}<span class="threshold-level">${num(threshold.elevation_m)}<small> m</small></span></div><div><div class="impact-title"><h3>${esc(assetName(threshold))}</h3><span class="impact-badge impact-${r.key}">${esc(r.level?.name||'Non applicabile')}</span></div><p>${esc(message)}</p>${peak?`<p class="impact-agreement">Al momento più condiviso: <strong>${esc(percentage(peak.fraction))}</strong> dei risultati filtrati dei modelli supera la quota.<br><span>${esc(dateInWords(peak.time))}, ore ${esc(timeOnly(peak.time))}.</span></p><div class="agreement-meter" role="img" aria-label="${esc(percentage(peak.fraction))} dei risultati filtrati sopra la quota"><span style="width:${peak.fraction*100}%"></span></div>`:''}<p class="threshold-season">${esc(s.season)}</p>${events.length?`<div class="impact-windows"><h4>Finestre con P95 sopra quota e onde frontali</h4><ul>${events.map(e=>`<li><span>${esc(eventLabel(e))}</span><span>fino al <strong>${esc(percentage(e.peak))}</strong> dei risultati filtrati</span></li>`).join('')}</ul></div>`:''}</div></article>`;
  }).join('');
}

function chartLayout(yTitle, x, height=350) {
  const ticks=x.filter((_,index)=>index%12===0);
  return {height,margin:{l:52,r:30,t:20,b:85},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'DM Sans, Arial, sans-serif',color:'#637775',size:11},hovermode:'closest',showlegend:true,legend:{orientation:'h',y:-.25,x:0,font:{size:10}},xaxis:{type:'date',title:{text:'Ora italiana · Europe/Rome',font:{size:10}},showgrid:false,tickvals:ticks,ticktext:ticks.map(t=>local(t)),automargin:true},yaxis:{title:{text:yTitle,font:{size:11}},gridcolor:'#e8ede5',zerolinecolor:'#c7d5c5',rangemode:'tozero'},hoverlabel:{font:{family:'DM Sans, Arial, sans-serif',size:11}}};
}
const plotOptions = {responsive:true,displaylogo:false,modeBarButtonsToRemove:['select2d','lasso2d'],toImageButtonOptions:{format:'png',filename:'onde-a-riva'}};

function renderCharts(location,rows) {
  $('threshold-key').innerHTML=location.thresholds.map((t,i)=>`<div style="--threshold-color:${thresholdColors[i%thresholdColors.length]}"><span class="threshold-swatch"></span><strong>${num(t.elevation_m)} m</strong><span>${esc(assetName(t))}${t.season==='summer'?' · estiva':''}</span></div>`).join('');
  const historical=location.climatology?.status==='available',unit=location.climatology?.time_step_hours===1?'ore':'campioni';
  $('wave-series-key').innerHTML='<span><i style="--series-color:#194e4c"></i>Altezza delle onde (Hs)</span><span><i style="--series-color:#c49b54"></i>Periodo fra le onde (Tp)</span>'+(historical?`<span><i class="dashed" style="--series-color:#a6a15c"></i>Onde alte · superate in 5 ${unit} su 100</span><span><i class="dashed" style="--series-color:#bd784f"></i>Onde molto alte · superate in 1 ${unit==='ore'?'ora':'campione'} su 100</span>`:'');
  $('wave-history-note').textContent=historical?'Le due linee orizzontali indicano altezze superate raramente nella serie storica ERA5 della località.':'';
  if (!window.Plotly) {
    for (const id of ['twl-chart','wave-chart']) $(id).innerHTML='<p class="muted">Grafico non disponibile. I riepiloghi e il download CSV restano accessibili.</p>';
    return;
  }
  const x=rows.map(row=>new Date(row.time).getTime()),text=rows.map(row=>local(row.time));
  const line=(key,name,color,width=1,extra={})=>({x,text,y:rows.map(r=>hasFilteredStatistics(r)?r[key]:null),name,type:'scatter',mode:'lines',connectgaps:false,line:{color,width},hovertemplate:'%{text}<br>%{y:.2f} m<extra>'+name+'</extra>',...extra});
  const traces=[
    line('twl_p05_m','5–95%','#dbe7d5',0,{showlegend:false,hoverinfo:'skip'}),
    line('twl_p95_m','5–95%','#dbe7d5',0,{fill:'tonexty',fillcolor:'#e5eddf',hoverinfo:'skip'}),
    line('twl_p25_m','25–75%','#99b690',0,{showlegend:false,hoverinfo:'skip'}),
    line('twl_p75_m','25–75%','#99b690',0,{fill:'tonexty',fillcolor:'#b9cfad',hoverinfo:'skip'}),
    line('twl_mean_m','Media dei risultati filtrati','#194e4c',2.5)
  ];
  location.thresholds.forEach((t,i)=>traces.push({x,y:rows.map(()=>t.elevation_m),name:assetName(t),showlegend:false,mode:'lines',line:{color:thresholdColors[i%thresholdColors.length],width:1,dash:'dash'},hovertemplate:`${esc(assetName(t))}: ${num(t.elevation_m)} m<extra></extra>`}));
  const twlLayout=chartLayout(`Livello totale [m; ${seaLevelReference(location).axis}]`,x);
  twlLayout.legend.font.size=9;
  Plotly.react('twl-chart',traces,twlLayout,plotOptions);
  // All three panels use xaxis, so zoom and pan always keep the times aligned.
  const layout=chartLayout('Altezza onde [m]',x,650);
  layout.margin.r=48;layout.showlegend=false;layout.yaxis.domain=[.59,1];layout.xaxis.anchor='y4';
  layout.yaxis2={title:{text:'Periodo [s]',font:{size:10}},overlaying:'y',side:'right',showgrid:false,rangemode:'tozero'};
  layout.yaxis3={title:{text:'Provenienza',font:{size:10}},domain:[.40,.49],anchor:'x',range:[-10,370],tickvals:[0,90,180,270,360],ticktext:['N','E','S','O','N'],gridcolor:'#e8ede5',zeroline:false};
  layout.yaxis4={title:{text:'Livello [m]',font:{size:10}},domain:[0,.21],anchor:'x',gridcolor:'#e8ede5',zerolinecolor:'#c7d5c5'};
  layout.annotations=[
    {xref:'paper',yref:'paper',x:0,y:.32,xanchor:'left',yanchor:'bottom',showarrow:false,text:'<b>Marea + Storm surge</b>',font:{size:16,color:'#123f41'}},
    {xref:'paper',yref:'paper',x:0,y:.235,xanchor:'left',yanchor:'bottom',showarrow:false,align:'left',text:'Oscillazioni della marea ed effetti di vento e pressione.<br>Include anche la circolazione marina del modello.',font:{size:10,color:'#637775'}}
  ];
  const waveTraces=[
    {x,text,y:rows.map(r=>r.hs_m),name:'Altezza delle onde (Hs)',mode:'lines',connectgaps:false,line:{color:'#194e4c',width:2},fill:'tozeroy',fillcolor:'#e6eddf',customdata:rows.map(r=>directionLabel(r.direction_deg)),hovertemplate:'%{text}<br>Hs: %{y:.2f} m<br>Da %{customdata}<extra></extra>'},
    {x,text,y:rows.map(r=>r.tp_s),name:'Periodo (Tp)',mode:'lines',yaxis:'y2',connectgaps:false,line:{color:'#c49b54',width:2,shape:'spline',smoothing:.8},hovertemplate:'%{text}<br>Tp orario: %{y:.1f} s<extra></extra>'}
  ];
  for (const [status,name,color] of [[false,'Onde non frontali','#347e4b'],[true,'Onde verso la costa','#b45b2b'],[null,'Direzione non valutabile','#7b8984']]) {
    const state=r=>r.hs_m>0?isExposed(r.direction_deg,location.wave_exposure):null;
    waveTraces.push({x,text,y:rows.map(r=>state(r)===status && Number.isFinite(r.direction_deg)?((r.direction_deg%360)+360)%360:null),yaxis:'y3',name,type:'scatter',mode:'markers',marker:{color,size:6},customdata:rows.map(r=>directionLabel(r.direction_deg)),hovertemplate:'%{text}<br>Da %{customdata}<extra>'+name+'</extra>'});
  }
  if (historical) {
    for (const [key,label,color] of [['p95_m','Onde alte · superate in 5 '+unit+' su 100','#a6a15c'],['p99_m','Onde molto alte · superate in 1 '+(unit==='ore'?'ora':'campione')+' su 100','#bd784f']]) {
      waveTraces.push({x,y:rows.map(()=>location.climatology[key]),name:label,mode:'lines',line:{color,width:1,dash:'dot'},hovertemplate:label+': %{y:.2f} m<extra>ERA5</extra>'});
    }
  }
  waveTraces.push({x,text,y:rows.map(r=>r.water_level_m),yaxis:'y4',name:'Marea + Storm surge',mode:'lines',connectgaps:false,line:{color:'#426b96',width:2},fill:'tozeroy',fillcolor:'#e2eaf2',hovertemplate:'%{text}<br>Livello del mare: %{y:.2f} m<extra>Marea + Storm surge</extra>'});
  Plotly.react('wave-chart',waveTraces,layout,plotOptions);
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
  $('extremes-summary').innerHTML=`<p class="chart-caption">Confronto con i massimi annuali delle onde provenienti dallo stesso settore. La selezione iniziale usa il settore dell’altezza massima nei quattro giorni; scegliendo un altro settore si mostra il suo picco nel periodo.</p><label class="sector-selector" for="extreme-sector">Settore presente nelle onde previste<select id="extreme-sector">${represented.map(s=>`<option value="${esc(s.id)}"${s.id===sector.id?' selected':''}>${esc(sectorLabel(s))}</option>`).join('')}</select></label><p class="extreme-peak"><strong>${num(peak.hs_m)} m al largo</strong> da ${esc(directionLabel(peak.direction_deg))}, il ${esc(dateInWords(peak.time))} alle ${esc(local(peak.time,{day:undefined,month:undefined}))}.</p><p><strong>${esc(periodText)}</strong></p>${fit.status==='available'?'<p class="chart-caption">Asse orizzontale: tempo di ritorno in anni, in scala logaritmica. Punti verdi: massimi annuali storici. Linea: Gumbel stimata. Fascia: incertezza del fit al 95%. Punto arancione: altezza massima prevista nel settore.</p><div id="extreme-chart" class="chart extreme-chart" aria-label="Curva Gumbel dei tempi di ritorno e altezza massima prevista nello stesso settore"></div>':`<p class="chart-caption">${esc(fit.reason||'Serie insufficiente per il fit.')}</p>`}<p class="chart-caption"><strong>Il tempo di ritorno riguarda le onde al largo, non gli allagamenti.</strong> Non significa che un evento si ripeta a intervalli regolari. La spiaggia può essere esposta o riparata: ${esc(exposureAtPeak(location,[peak]).text)}</p><p class="small"><a href="metodo.html#storico">Metodo, dati e limiti della stima ↗</a></p>`;
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

function locationParameters(location) {
  const reference=seaLevelReference(location);
  const content=`<dl><dt>Pendenze β</dt><dd>${location.slopes.map(s=>num(s,3)).join(' · ')} (valori configurati)</dd><dt>Rugosità</dt><dd>${num(location.roughness_m,4)} m</dd><dt>Punto offshore richiesto</dt><dd>${num(location.wave_point.latitude,5)}° N, ${num(location.wave_point.longitude,5)}° E</dd><dt>Cella estratta</dt><dd>${location.source.selected_point ? esc(JSON.stringify(location.source.selected_point)) : 'Non applicabile ai dati dimostrativi'}</dd><dt>Modelli disponibili</dt><dd>${esc(location.valid_models.join('; '))}</dd><dt>Senza risultati validi</dt><dd>${esc(location.missing_models.join('; ')||'Nessuno')}</dd><dt>Motore di calcolo</dt><dd>${esc(bulletin.model_backend)}</dd><dt>Settori di esposizione</dt><dd>${location.wave_exposure?.sectors_deg?.length?esc(location.wave_exposure.sectors_deg.map(([a,b])=>`${num(a,0)}° → ${num(b,0)}° in senso orario`).join('; ')):'Da definire'}</dd><dt>Riferimento verticale</dt><dd>${esc(reference.label)}. ${esc(reference.detail)}</dd><dt>Note della località</dt><dd>${esc(location.notes)}</dd><dt>Download CSV</dt><dd>Contiene tutti i risultati dei modelli sull’intero periodo scaricato (120 ore); tempi in UTC.</dd></dl>`;
  const c=location.climatology,e=c?.directional_extremes;
  const filtered=location.hourly.filter(hasFilteredStatistics);
  const filterInfo=filtered.length?`<h4>Filtro dei risultati di runup</h4><p>Filtro ±3σ per ora, un passaggio. ${num(filtered.reduce((sum,r)=>sum+r.n_outliers,0),0)} esclusioni su ${num(filtered.reduce((sum,r)=>sum+r.n_estimates_raw,0),0)} calcoli grezzi nell’intero periodo scaricato. I CSV conservano tutti i risultati con il campo included_in_summary.</p>`:'<p>Statistiche filtrate non disponibili: occorre aggiornare il bollettino.</p>';
  return content+filterInfo+(c?.status==='available'?`<h4>Serie storica ERA5</h4><p>${esc(c.source)}, ${new Date(c.start).getUTCFullYear()}–${new Date(c.end).getUTCFullYear()}; ${num(c.n_records,0)} campioni; passo ${num(c.time_step_hours,1)} ore; copertura ${num(c.coverage_fraction*100,1)}%.</p><p>95° percentile: ${num(c.p95_m)} m; 99° percentile: ${num(c.p99_m)} m; massimo: ${num(c.max_hs_m)} m. ${esc(c.comparison_note||'')}</p>`:'')+(e?.status==='available'?`<h4>Massimi annuali per settore</h4><p>Settori statistici di ${num(e.sector_width_deg,0)}°, distinti dalle direzioni di esposizione.</p><ul>${e.sectors.map(s=>`<li>${esc(sectorLabel(s))}: ${s.fit.status==='available'?`${s.fit.n_years} anni, ${s.fit.first_year}–${s.fit.last_year}; ${s.fit.bootstrap_replicates} ricampionamenti bootstrap.`:esc(s.fit.reason||'Fit non disponibile.')}</li>`).join('')}</ul>`:'');
}

async function bootMethod() {
  try {
    const response=await fetch(`data/forecast.json?t=${Math.floor(Date.now()/300000)}`,{cache:'no-cache'});
    if (!response.ok) throw new Error('Metadati non disponibili');
    bulletin=await response.json();
    if (bulletin.schema_version!==1 || !bulletin.locations) throw new Error('Metadati non riconosciuti');
    $('model-references').innerHTML=bulletin.model_order.map(name=>`<p>${esc(bulletin.citations[name]||name)}</p>`).join('');
    $('method-locations').innerHTML=Object.entries(bulletin.locations).map(([slug,loc])=>`<details class="location-technical" id="parametri-${esc(slug)}"><summary>${esc(loc.name)}</summary><div>${locationParameters(loc)}</div></details>`).join('');
    $('updated').textContent=`Metadati del bollettino: ${local(bulletin.generated_at)} · Italia`;
    const slug=new URL(window.location.href).searchParams.get('localita');
    if (slug && Object.hasOwn(bulletin.locations,slug)) {$('method-return').href=`./?localita=${encodeURIComponent(slug)}`;$('method-return').textContent=`← Torna a ${bulletin.locations[slug].name}`;}
  } catch(error) {$('method-locations').innerHTML='<p>Parametri momentaneamente non disponibili. Le spiegazioni del metodo restano consultabili.</p>';}
}

function renderDetail(slug) {
  const location=bulletin.locations[slug];
  const rows=windowRows(location);
  document.title=`${location.name} · Onde a riva`;
  $('location-title').textContent=location.name;
  $('area').textContent=location.area;
  const reference=seaLevelReference(location);
  $('twl-reference-label').textContent=`metri · zero: ${reference.label}`;
  $('sealevel-caption').innerHTML=`Zero del livello marino: ${esc(reference.label)}. <a href="metodo.html?localita=${encodeURIComponent(slug)}#zero">Riferimento delle quote ↗</a>`;
  $('technical-link').href=`metodo.html?localita=${encodeURIComponent(slug)}`;
  $('download').href=location.csv;
  const valid=rows.filter(r=>hasFilteredStatistics(r) && Number.isFinite(r.twl_p95_m));
  const futureEnd=Math.floor(Date.now()/hourMs)*hourMs + bulletin.display_hours*hourMs;
  const insufficient = new Date(location.valid_to).getTime()<futureEnd;
  const invalid=rows.filter(r=>!r.n_estimates).length;
  const staleStatistics=rows.some(r=>!hasFilteredStatistics(r));
  setNotice(!rows.length ? 'Bollettino scaduto: nessun campione futuro disponibile. È necessario un aggiornamento.' : `${staleStatistics?'Serve un nuovo bollettino con filtro ±3σ: categorie e curve TWL non applicate ai vecchi dati. ':''}${insufficient?'Copertura parziale: non sono disponibili tutte le prossime 96 ore. ':''}${invalid?`${invalid} ore senza risultati validi dei modelli.`:''}`,location);
  $('period').textContent=rows.length ? `${local(rows[0].time)} — ${local(rows[rows.length-1].time)} · ${rows.length} campioni orari · ora italiana` : 'Nessuna previsione futura disponibile';
  const peak=valid.length ? valid.reduce((best,row)=>row.twl_p95_m>best.twl_p95_m?row:best) : null;
  const hs=rows.length ? Math.max(...rows.map(r=>r.hs_m)) : null;
  $('metrics').innerHTML=[
    ['Livello alto stimato (P95)',`${num(peak?.twl_p95_m)} <small>m</small>`,peak ? `Picco del 95° percentile filtrato · ${local(peak.time)} · quote provvisorie` : 'Dati non disponibili'],
    ['Massima altezza delle onde',`${num(hs)} <small>m</small>`,'Hs nel punto offshore'],
    ['Modelli calcolati',`${location.valid_models.length} <small>/ ${bulletin.model_order.length}</small>`,`${location.slopes.length} pendenze della spiaggia · ogni modello è applicato a ciascuna pendenza`]
  ].map(([label,value,note])=>`<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${value}</div><div class="metric-note">${esc(note)}</div></div>`).join('');
  renderDaily(location,rows);
  renderExtremes(location,rows);
  renderThresholds(location,rows);
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
if (document.body?.dataset?.page==='method') bootMethod(); else boot();
