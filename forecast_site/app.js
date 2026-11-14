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
  return location.hourly.filter(row => new Date(row.time).getTime() >= start && new Date(row.time).getTime() < (bulletin.display_to ? Date.parse(bulletin.display_to) : start + bulletin.display_hours*hourMs));
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
  if (meta.mode==='noaa_tide_meteocean_surge') return {label:'media del modello · raccordo locale provvisorio',axis:'riferimento medio del modello',caption:'Marea astronomica NOAA STOFS + sovralzo meteorologico MeteOcean. Non è applicata la media storica Copernicus. Il raccordo con le quote locali rimane da validare.',detail:'Somma della sola marea NOAA HTP e del surge MeteOcean, confermato come anomalia rispetto al livello medio. Il livello completo NOAA CWL non viene sommato al surge. Lo zero non certifica il riferimento dei rilievi sulla spiaggia.'};
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

function nextScheduledUtc(hours,minute,now) {
  if (!Number.isInteger(minute) || minute<0 || minute>59) return null;
  const validHours=hours.filter(h=>Number.isInteger(h)&&h>=0&&h<24).sort((a,b)=>a-b);
  const today=new Date(now);
  for (let day=0;day<2;day++) {
    for (const hour of validHours) {
      const time=Date.UTC(today.getUTCFullYear(),today.getUTCMonth(),today.getUTCDate()+day,hour,minute);
      if (time>now) return new Date(time).toISOString();
    }
  }
  return null;
}

function nextWavePublication(now=Date.now()) {
  const configured=bulletin.wave_model?.publication_hours_utc;
  const fallback=bulletin.source?.product_id==='MEDSEA_ANALYSISFORECAST_WAV_006_017'?[6,20]:[];
  return nextScheduledUtc(configured||fallback,bulletin.wave_model?.publication_minute_utc??0,now);
}

function nextSiteAcquisition(now=Date.now()) {
  const schedule=bulletin.update_schedule;
  return nextScheduledUtc(schedule?.hours_utc||[6],schedule?(schedule.minute_utc??0):40,now);
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
  let sourceSummary=sourceText;
  let updateText=next?` Prossima uscita prevista: <strong>${esc(noticeDate(next))}</strong> (ora italiana).`:' Orari italiani.';
  if (bulletin.mode==='meteocean') {
    sourceSummary='Onde e storm surge <a href="https://meteocean.science/" target="_blank" rel="noopener">MeteOcean – UniGE</a>; marea astronomica NOAA';
    const nextUpdate=nextSiteAcquisition(now);
    updateText=nextUpdate?` Prossima acquisizione prevista: <strong>${esc(noticeDate(nextUpdate))}</strong> (ora italiana).`:'';
  }
  const message=demo?`<strong>Modalità dimostrativa.</strong> Elaborazione del ${esc(noticeDate(bulletin.generated_at))}. Onde e livello del mare sintetici.`:`Elaborazione del <strong>${esc(noticeDate(bulletin.generated_at))}</strong>. ${sourceSummary}.${updateText}`;
  const staleAfter=Number.isFinite(bulletin.stale_after_hours)?bulletin.stale_after_hours:18;
  $('notice').innerHTML = message + (age > staleAfter ? ` <strong>Aggiornamento in ritardo: il bollettino ha più di ${staleAfter} ore.</strong>` : '') + (extra ? ' '+esc(extra) : '');
}

function locationCards() {
  $('location-cards').innerHTML = Object.entries(bulletin.locations).map(([slug, location], index) => {
    const units=Object.values(location.sectors||{});
    const rows = units.length?units.flatMap(unit=>windowRows(unit)):windowRows(location);
    const valid=rows.filter(r=>hasFilteredStatistics(r) && Number.isFinite(r.twl_p95_m));
    const maximum=valid.length?Math.max(...valid.map(r=>r.twl_p95_m)):NaN;
    return `<a class="location-card" href="?localita=${encodeURIComponent(slug)}"><div><div class="card-top"><span class="card-index">LOCALITÀ / 0${index+1}</span><span class="card-arrow" aria-hidden="true">↗</span></div><h3>${esc(location.name)}</h3><p>${esc(location.area)}</p></div><div class="card-bottom"><span>${valid.length ? `Livello alto stimato: <strong>${num(maximum)} m</strong>` : rows.length?'Stime da aggiornare':'Nessun dato futuro disponibile'}</span><span>Esplora le previsioni →</span></div></a>`;
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
  url.searchParams.delete('settore');
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
  {key:'white',name:'Bianco',label:'La fascia delle stime non supera la quota',title:'La fascia delle stime non supera la quota di riferimento.'},
  {key:'yellow',name:'Giallo',label:'Le stime più alte superano la quota',title:'Le stime più alte superano la quota di riferimento.'},
  {key:'orange',name:'Arancione',label:'La quota è superata da una parte più ampia delle stime',title:'La quota di riferimento è superata anche da una parte più ampia delle stime.'}
];

function percentage(fraction) {
  if (!Number.isFinite(fraction)) return '—';
  if (fraction>0 && fraction<.001) return '<0,1%';
  if (fraction<1 && fraction>.999) return '>99,9%';
  const value=fraction*100;
  return `${num(value,Math.abs(value-Math.round(value))<1e-8?0:1)}%`;
}

// Choose the Italian article from the spoken percentage (zero, uno, otto...).
function percentageWithArticle(fraction) {
  const value=percentage(fraction);
  if (value.startsWith('<')) return 'meno dello 0,1%';
  if (value.startsWith('>')) return 'oltre il 99,9%';
  const integer=Math.floor(fraction*100);
  const article=integer===0?'lo ':integer===1 || integer===8 || integer===11 || (integer>=80 && integer<=89)?'l’':'il ';
  return article+value;
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

function referenceThreshold(location) {return location.thresholds.find(t=>t.id==='strutture_turistiche_fisse')||location.thresholds.find(t=>t.season==='all_year')||location.thresholds[0]||null;}

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
  const inactiveCount=results.filter(r=>r.kind==='inactive').length;
  const inactive=results.length>0 && inactiveCount===results.length;
  const gray=!peak && nonfrontalCount>0 && !unknownCount;
  const level=peak?impactLevels[peak.rank]:gray?{key:'gray',name:'Grigio',title:'Le onde provengono da direzioni diverse da quelle di esposizione della spiaggia.'}:null;
  return {threshold,peak,level,key:level?.key||'unavailable',title:!threshold?'Nessuna struttura esposta configurata per questo tratto.':inactive?'Struttura fuori dal periodo di attività configurato.':level?.title||'Non ci sono informazioni sufficienti per completare il confronto.',nonfrontalCount,inactive,
    missingCount:results.filter(r=>!['numeric','nonfrontal','inactive'].includes(r.kind)).length};
}

function exposureAtPeak(location,rows) {
  const peak=wavePeak(rows);
  if (!peak || peak.hs_m<=0) return {peak,status:null,text:'Non possiamo confrontare la direzione delle onde con la spiaggia: il mare è calmo oppure mancano i dati.'};
  const status=isExposed(peak.direction_deg,location.wave_exposure);
  return {peak,status,text:`Le onde più alte arrivano da ${directionLabel(peak.direction_deg)}. `+(status===false?'Provengono da una direzione diversa da quelle a cui questa spiaggia è esposta. Il loro effetto a riva potrebbe essere minore, ma non è escluso.':status===true?'Provengono da una delle direzioni a cui questa spiaggia è esposta.':'Il confronto con l’orientamento della spiaggia non è ancora disponibile.')};
}

function directionSummary(location,rows,compact=false) {
  const result=exposureAtPeak(location,rows);
  const key=result.status===false?'away':result.status===true?'toward':'unknown';
  const label=result.status===false?'Onde da altre direzioni':result.status===true?'Onde verso la costa':'Direzione da verificare';
  const available=rows.filter(r=>r.hs_m>0 && isExposed(r.direction_deg,location.wave_exposure)!==null);
  const frontal=available.filter(r=>isExposed(r.direction_deg,location.wave_exposure)).length;
  return `<span class="direction-badge direction-${key}">${esc(label)}</span><p>${esc(result.text)}</p>${!compact && available.length?`<p>Onde provenienti dalle direzioni di esposizione della spiaggia in <strong>${frontal} ${frontal===1?'ora':'ore'} su ${available.length}</strong> con dati disponibili.</p>`:''}${result.status===false?'<p class="small">Questa indicazione non esclude onde sulla spiaggia.</p>':''}`;
}

function impactLegend() {
  return `<div class="impact-legend" aria-label="Legenda dei colori della tendenza">${[...impactLevels,{key:'gray',name:'Grigio',label:'Onde da altre direzioni: confronto non applicato'}].map(l=>`<div class="legend-item impact-${l.key}"><span class="impact-swatch" aria-hidden="true"></span><span><strong>${l.name}</strong>${l.label}</span></div>`).join('')}</div><p class="legend-note">I colori confrontano le stime con la quota di riferimento, soltanto nelle ore con onde provenienti dalle direzioni di esposizione della spiaggia. Non sono livelli di allerta ufficiali. <a href="metodo.html#colori">Come leggere colori e percentuali ↗</a></p>`;
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
  if (result.inactive) return 'La struttura di riferimento è fuori stagione: il confronto con la sua quota non viene applicato.';
  if (!result.threshold) return 'I grafici del livello dell’acqua e la mappa restano consultabili anche senza strutture esposte configurate.';
  if (result.key==='gray') return 'In queste condizioni non assegniamo una categoria al contributo delle onde. Questo non esclude effetti sulla spiaggia o allagamenti dovuti al livello del mare.';
  if (!result.peak) return 'Per il confronto servono i risultati aggiornati dei calcoli e le direzioni da cui la spiaggia è esposta alle onde.';
  return `Il giorno ${esc(dateInWords(result.peak.row.time))}, alle ${esc(timeOnly(result.peak.row.time))}, <strong>${esc(percentageWithArticle(result.peak.fraction))}</strong> dei calcoli supera la quota di ${num(result.threshold.elevation_m)} m.${result.peak.rank===0 && result.peak.fraction>0?' Si tratta di risultati al di sopra della fascia mostrata nel grafico.':''}`;
}

function renderDaily(location,rows) {
  const threshold=referenceThreshold(location),trend=assessTrend(location,rows,threshold),days=Math.ceil(bulletin.display_hours/24);
  $('outlook-title').textContent=`Tendenza a ${days} ${days===1?'giorno':'giorni'}`;
  $('outlook-panel').className=`panel outlook-panel impact-${trend.key}`;
  $('outlook').innerHTML=`<div class="trend-content"><div><span class="impact-badge impact-${trend.key}">${esc(trend.level?.name||'Non disponibile')}</span><h3>${esc(trend.title)}</h3><p>Il confronto usa una quota di <strong>${threshold?num(threshold.elevation_m)+' m':'altezza da definire'}</strong>, associata a <strong>${threshold?esc(assetName(threshold)):"struttura non configurata"}</strong>. Le quote reali delle strutture devono ancora essere verificate.</p><p class="model-agreement">${modelAgreement(trend)}</p></div><div class="trend-direction">${directionSummary(location,rows)}</div></div>${impactLegend()}<p class="small muted">${rows.length} ore disponibili su ${bulletin.display_hours}${trend.nonfrontalCount?` · ${trend.nonfrontalCount} ${trend.nonfrontalCount===1?'ora con onde da altre direzioni esclusa':'ore con onde da altre direzioni escluse'} dal confronto`:''}${trend.missingCount?` · ${trend.missingCount} ${trend.missingCount===1?'ora':'ore'} con confronto incompleto`:''}. Ogni calcolo combina un modello con una pendenza della spiaggia. Le percentuali non sono probabilità di allagamento.</p>`;
  $('daily').innerHTML=groupsByDay(rows).map(group=>{
    const r=assessTrend(location,group,threshold),valid=group.filter(row=>hasFilteredStatistics(row) && Number.isFinite(row.twl_p95_m));
    const date=new Date(group[0].time).toLocaleDateString('it-IT',{timeZone:'Europe/Rome',weekday:'long',day:'numeric',month:'long'});
    const intervals=threshold?exceedanceEvents(thresholdState(threshold,group,location).samples):[];
    return `<article class="day-card impact-day impact-${r.key}"><div class="day-heading"><h3>${esc(date)}</h3><span class="impact-badge impact-${r.key}">${esc(r.level?.name||'Non disponibile')}</span></div><div class="day-impact">${esc(r.title)}</div><p>${modelAgreement(r)}</p><p class="day-time">${intervals.length?'Orari del possibile superamento della quota di riferimento<br><strong>'+intervals.map(e=>esc(eventLabel(e,true))).join(' · ')+'</strong>':r.peak?'La fascia delle stime non supera la quota di riferimento nelle ore con onde dalle direzioni di esposizione della spiaggia.':'Confronto non applicato'}</p><p class="day-range">${r.key==='gray'?'Livello alto calcolato, senza correggere l’effetto della direzione':'Livello alto stimato'}: <strong>${num(valid.length?Math.max(...valid.map(row=>row.twl_p95_m)):NaN)} m</strong></p><div class="direction-day">${directionSummary(location,group,true)}</div><p class="day-coverage">${group.length} ore disponibili${group.length<24?' · giornata parziale':''}${r.missingCount?' · confronto incompleto':''}${r.nonfrontalCount?` · ${r.nonfrontalCount} ${r.nonfrontalCount===1?'ora con onde da altre direzioni':'ore con onde da altre direzioni'}`:''}</p></article>`;
  }).join('');
}

function renderThresholds(location,rows) {
  if (!location.thresholds.length) {$("thresholds").innerHTML="<p>Nessuna struttura esposta configurata per questo tratto. Runup, livello totale dell’acqua e mappa restano disponibili.</p>";return;}
  $('thresholds').innerHTML=location.thresholds.map(threshold=>{
    const s=thresholdState(threshold,rows,location),r=assessTrend(location,rows,threshold),events=exceedanceEvents(s.samples),crossed=s.available.filter(sample=>sample.above_p95);
    const peak=crossed.reduce((best,sample)=>!best || sample.fraction>best.fraction?sample:best,null);
    const message=r.key==='gray'?'Le onde provengono da altre direzioni: non assegniamo una categoria a questa struttura. Il livello del mare può comunque causare effetti sulla costa.':s.max===null?'Il confronto non è disponibile per questo periodo. Controlla la stagione di utilizzo e la disponibilità dei dati.':!crossed.length?'La fascia delle stime non supera questa quota nelle ore con onde dalle direzioni di esposizione della spiaggia.':`Le stime più alte superano questa quota in ${crossed.length} ${crossed.length===1?'ora':'ore'} con onde dalle direzioni di esposizione della spiaggia.`;
    return `<article class="threshold-explained impact-${r.key}"><div class="impact-asset">${impactIcon(threshold.id)}<span class="threshold-level">${num(threshold.elevation_m)}<small> m</small></span></div><div><div class="impact-title"><h3>${esc(assetName(threshold))}</h3><span class="impact-badge impact-${r.key}">${esc(r.level?.name||'Non applicabile')}</span></div><p>${esc(message)}</p>${peak?`<p class="impact-agreement">Il giorno ${esc(dateInWords(peak.time))}, alle ${esc(timeOnly(peak.time))}, <strong>${esc(percentageWithArticle(peak.fraction))}</strong> dei calcoli supera la quota di ${num(threshold.elevation_m)} m.</p><div class="agreement-meter" role="img" aria-label="${esc(percentage(peak.fraction))} dei calcoli supera la quota"><span style="width:${peak.fraction*100}%"></span></div>`:''}<p class="threshold-season">Quota provvisoria: ${num(threshold.elevation_m)} m · ${esc(s.season)}</p>${events.length?`<div class="impact-windows"><h4>Orari del possibile superamento della quota</h4><ul>${events.map(e=>`<li><span>${esc(eventLabel(e))}</span><span>fino al <strong>${esc(percentage(e.peak))}</strong> dei calcoli</span></li>`).join('')}</ul></div>`:''}</div></article>`;
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
  $('wave-series-key').innerHTML='<span><i style="--series-color:#194e4c"></i>Altezza delle onde (Hs)</span><span><i style="--series-color:#c49b54"></i>Tempo tra le onde (Tp)</span>'+(historical?`<span><i class="dashed" style="--series-color:#a6a15c"></i>Onde alte · superate in 5 ${unit} su 100</span><span><i class="dashed" style="--series-color:#bd784f"></i>Onde molto alte · superate in 1 ${unit==='ore'?'ora':'campione'} su 100</span>`:'');
  $('wave-history-note').textContent=historical?'Le due linee orizzontali indicano altezze superate raramente nella serie storica ERA5 della località.':'';
  if (!window.Plotly) {
    for (const id of ['twl-chart','wave-chart']) $(id).innerHTML='<p class="muted">Grafico non disponibile. I riepiloghi e il download CSV restano accessibili.</p>';
    return;
  }
  const x=rows.map(row=>new Date(row.time).getTime()),text=rows.map(row=>local(row.time));
  const line=(key,name,color,width=1,extra={})=>({x,text,y:rows.map(r=>hasFilteredStatistics(r)?r[key]:null),name,type:'scatter',mode:'lines',connectgaps:false,line:{color,width},hovertemplate:'%{text}<br>%{y:.2f} m<extra>'+name+'</extra>',...extra});
  const traces=[
    line('twl_p05_m','Fascia più ampia delle stime','#dbe7d5',0,{showlegend:false,hoverinfo:'skip'}),
    line('twl_p95_m','Fascia più ampia delle stime','#dbe7d5',0,{fill:'tonexty',fillcolor:'#e5eddf',hoverinfo:'skip'}),
    line('twl_p25_m','Fascia centrale delle stime','#99b690',0,{showlegend:false,hoverinfo:'skip'}),
    line('twl_p75_m','Fascia centrale delle stime','#99b690',0,{fill:'tonexty',fillcolor:'#b9cfad',hoverinfo:'skip'}),
    line('twl_mean_m','Media dei calcoli','#194e4c',2.5)
  ];
  location.thresholds.forEach((t,i)=>traces.push({x,y:rows.map(()=>t.elevation_m),name:assetName(t),showlegend:false,mode:'lines',line:{color:thresholdColors[i%thresholdColors.length],width:1,dash:'dash'},hovertemplate:`${esc(assetName(t))}: ${num(t.elevation_m)} m<extra></extra>`}));
  const twlLayout=chartLayout(`Livello totale [m; ${seaLevelReference(location).axis}]`,x);
  twlLayout.legend.font.size=9;
  Plotly.react('twl-chart',traces,twlLayout,plotOptions);
  // Every panel uses the same xaxis, so zoom and pan keep the times aligned.
  const separateSea=rows.some(r=>Number.isFinite(r.tide_m)) && rows.some(r=>Number.isFinite(r.surge_m));
  const height=separateSea?1150:650;
  if ($('wave-chart').style) $('wave-chart').style.height=height+'px';
  const layout=chartLayout('Altezza onde [m]',x,height);
  layout.margin.r=48;layout.showlegend=false;layout.yaxis.domain=[.59,1];layout.xaxis.anchor='y4';
  layout.yaxis2={title:{text:'Tempo tra le onde [s]',font:{size:10}},overlaying:'y',side:'right',showgrid:false,rangemode:'tozero'};
  layout.yaxis3={title:{text:'Provenienza',font:{size:10}},domain:[.40,.49],anchor:'x',range:[-10,370],tickvals:[0,90,180,270,360],ticktext:['N','E','S','O','N'],gridcolor:'#e8ede5',zeroline:false};
  layout.yaxis4={title:{text:'Livello [m]',font:{size:10}},domain:[0,.21],anchor:'x',gridcolor:'#e8ede5',zerolinecolor:'#c7d5c5'};
  layout.annotations=[
    {xref:'paper',yref:'paper',x:0,y:.32,xanchor:'left',yanchor:'bottom',showarrow:false,text:'<b>Marea + Storm surge</b>',font:{size:16,color:'#123f41'}},
    {xref:'paper',yref:'paper',x:0,y:.235,xanchor:'left',yanchor:'bottom',showarrow:false,align:'left',text:bulletin.mode==='meteocean'?'Marea astronomica NOAA + sovralzo da vento e pressione MeteOcean.':'Oscillazioni della marea ed effetti di vento e pressione.<br>Include anche la circolazione marina del modello.',font:{size:10,color:'#637775'}}
  ];
  if (separateSea) {
    layout.yaxis.domain=[.81,1];
    layout.yaxis3.domain=[.68,.75];
    layout.xaxis.anchor='y6';
    const values=rows.flatMap(r=>[r.tide_m,r.surge_m,r.water_level_m]).filter(Number.isFinite);
    const bound=Math.max(.05,...values.map(Math.abs))*1.15;
    const seaAxis=domain=>({title:{text:'metri',font:{size:10}},domain,anchor:'x',range:[-bound,bound],gridcolor:'#e8ede5',zeroline:true,zerolinecolor:'#94aaa1',zerolinewidth:1.5});
    layout.yaxis4=seaAxis([.46,.59]);
    layout.yaxis5=seaAxis([.23,.36]);
    layout.yaxis6=seaAxis([0,.13]);
    const label=(y,text,color,size)=>({xref:'paper',yref:'paper',x:0,y,xanchor:'left',yanchor:'bottom',showarrow:false,align:'left',text,font:{size,color}});
    layout.annotations=[
      label(.645,'<b>Marea astronomica</b>','#287f85',16),
      label(.603,'Oscillazioni dovute a Luna e Sole.<br>Fonte: NOAA.','#637775',10),
      label(.415,'<b>Storm surge · effetto del meteo</b>','#b7703c',16),
      label(.373,'Variazioni del livello causate da vento e pressione.<br>Fonte: MeteOcean – UniGE.','#637775',10),
      label(.185,'<b>Livello del mare · marea + surge</b>','#426b96',16),
      label(.143,'Somma dei due contributi.<br>La risalita delle onde si aggiunge nel grafico del livello totale.','#637775',10)
    ];
  }
  const waveTraces=[
    {x,text,y:rows.map(r=>r.hs_m),name:'Altezza delle onde (Hs)',mode:'lines',connectgaps:false,line:{color:'#194e4c',width:2},fill:'tozeroy',fillcolor:'#e6eddf',customdata:rows.map(r=>directionLabel(r.direction_deg)),hovertemplate:'%{text}<br>Hs: %{y:.2f} m<br>Da %{customdata}<extra></extra>'},
    {x,text,y:rows.map(r=>r.tp_s),name:'Tempo tra le onde (Tp)',mode:'lines',yaxis:'y2',connectgaps:false,line:{color:'#c49b54',width:2,shape:'spline',smoothing:.8},hovertemplate:'%{text}<br>Tempo tra le onde: %{y:.1f} s<extra></extra>'}
  ];
  for (const [status,name,color] of [[false,'Onde da altre direzioni','#347e4b'],[true,'Onde verso la costa','#b45b2b'],[null,'Direzione non valutabile','#7b8984']]) {
    const state=r=>r.hs_m>0?isExposed(r.direction_deg,location.wave_exposure):null;
    waveTraces.push({x,text,y:rows.map(r=>state(r)===status && Number.isFinite(r.direction_deg)?((r.direction_deg%360)+360)%360:null),yaxis:'y3',name,type:'scatter',mode:'markers',marker:{color,size:6},customdata:rows.map(r=>directionLabel(r.direction_deg)),hovertemplate:'%{text}<br>Da %{customdata}<extra>'+name+'</extra>'});
  }
  if (historical) {
    for (const [key,label,color] of [['p95_m','Onde alte · superate in 5 '+unit+' su 100','#a6a15c'],['p99_m','Onde molto alte · superate in 1 '+(unit==='ore'?'ora':'campione')+' su 100','#bd784f']]) {
      waveTraces.push({x,y:rows.map(()=>location.climatology[key]),name:label,mode:'lines',line:{color,width:1,dash:'dot'},hovertemplate:label+': %{y:.2f} m<extra>ERA5</extra>'});
    }
  }
  if (separateSea) {
    waveTraces.push({x,text,y:rows.map(r=>r.tide_m),yaxis:'y4',name:'Marea astronomica NOAA',mode:'lines',connectgaps:false,line:{color:'#287f85',width:2},fill:'tozeroy',fillcolor:'rgba(40,127,133,.10)',hovertemplate:'%{text}<br>Marea NOAA: %{y:.2f} m<extra></extra>'});
    waveTraces.push({x,text,y:rows.map(r=>r.surge_m),yaxis:'y5',name:'Storm surge MeteOcean',mode:'lines',connectgaps:false,line:{color:'#b7703c',width:2},fill:'tozeroy',fillcolor:'rgba(183,112,60,.10)',hovertemplate:'%{text}<br>Surge MeteOcean: %{y:.2f} m<extra></extra>'});
  }
  waveTraces.push({x,text,y:rows.map(r=>r.water_level_m),yaxis:separateSea?'y6':'y4',name:'Marea + Storm surge',mode:'lines',connectgaps:false,line:{color:'#426b96',width:2},fill:'tozeroy',fillcolor:'#e2eaf2',hovertemplate:'%{text}<br>Livello del mare: %{y:.2f} m<extra>Marea + Storm surge</extra>'});
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
  return `Da ${directionLabel(sector.center_deg).split(" (")[0]} · ${num(sector.start_deg,1)}°–${num(sector.end_deg,1)}°`;
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
  const periodText=fit.status!=='available'?'Stima non disponibile per questo settore.':!Number.isFinite(period)||period>upper?`La curva storica indica un tempo medio di attesa superiore a ${num(upper,0)} anni. La stima è oltre il limite del grafico ed è particolarmente incerta.`:period<2?'Questa altezza è inferiore a quella che, secondo la stima storica per questa direzione, viene raggiunta o superata in media una volta ogni 2 anni.':`Secondo la stima storica, onde di questa altezza o superiori, provenienti da questa direzione, hanno un tempo medio di attesa di circa ${num(period,period<10?1:0)} anni.`;
  $('extremes-summary').innerHTML=`<p class="chart-caption">Confrontiamo le onde più alte previste con le più alte di ciascun anno del passato provenienti dalla stessa direzione. Puoi scegliere un’altra direzione fra quelle presenti nel periodo mostrato: il confronto userà le onde più alte previste da quella direzione.</p><label class="sector-selector" for="extreme-sector">Direzione delle onde da confrontare<select id="extreme-sector">${represented.map(s=>`<option value="${esc(s.id)}"${s.id===sector.id?' selected':''}>${esc(sectorLabel(s))}</option>`).join('')}</select></label><p class="extreme-peak"><strong>${num(peak.hs_m)} m al largo</strong> da ${esc(directionLabel(peak.direction_deg))}, il ${esc(dateInWords(peak.time))} alle ${esc(local(peak.time,{day:undefined,month:undefined}))}.</p><p><strong>${esc(periodText)}</strong></p>${fit.status==='available'?'<p class="chart-caption">Il punto arancione indica le onde più alte previste dalla direzione selezionata. I punti verdi mostrano le più alte di ciascun anno del passato. La linea riassume la stima storica e la fascia ne mostra l’incertezza. Più il punto si trova a destra, più l’altezza risulta rara secondo questa stima.</p><div id="extreme-chart" class="chart extreme-chart" aria-label="Curva Gumbel dei tempi di ritorno e altezza massima prevista nello stesso settore"></div>':`<p class="chart-caption">${esc(fit.reason||'Serie insufficiente per il fit.')}</p>`}<p class="chart-caption"><strong>Il tempo di ritorno riguarda le onde al largo, non gli allagamenti.</strong> È una media statistica: eventi simili possono verificarsi anche a breve distanza. La spiaggia può essere esposta o riparata: ${esc(exposureAtPeak(location,[peak]).text)}</p><p class="small"><a href="metodo.html#storico">Metodo, dati e limiti della stima ↗</a></p>`;
  $('extreme-sector').onchange=event=>renderExtremes(location,rows,event.target.value);
  if (fit.status!=='available') return;
  if (!window.Plotly) {
    $('extreme-chart').innerHTML='<p>Grafico non disponibile. La stima e i suoi limiti restano descritti nel testo.</p>';
    return;
  }
  const x=fit.return_period_years;
  const traces=[
    {x,y:fit.ci95_low_m,type:'scatter',mode:'lines',line:{width:0},showlegend:false,hoverinfo:'skip'},
    {x,y:fit.ci95_high_m,type:'scatter',mode:'lines',line:{width:0},fill:'tonexty',fillcolor:'#dce8dd',name:'Incertezza della stima',hoverinfo:'skip'},
    {x,y:fit.return_level_m.map((y,i)=>x[i]<=fit.n_years?y:null),type:'scatter',mode:'lines',name:'Curva stimata dallo storico',line:{color:'#194e4c',width:2},hovertemplate:'Ritorno: %{x:.1f} anni<br>Hs: %{y:.2f} m<extra>Gumbel</extra>'},
    {x,y:fit.return_level_m.map((y,i)=>x[i]>=fit.n_years?y:null),type:'scatter',mode:'lines',name:'Stima oltre la durata dello storico',line:{color:'#194e4c',width:2,dash:'dash'},hovertemplate:'Ritorno: %{x:.1f} anni<br>Hs: %{y:.2f} m<extra>Estrapolazione</extra>'},
    {x:fit.empirical.map(r=>r.return_period_years),y:fit.empirical.map(r=>r.hs_m),customdata:fit.empirical.map(r=>r.year),type:'scatter',mode:'markers',name:'Massimi annuali storici',marker:{color:'#678973',size:6},hovertemplate:'Anno: %{customdata}<br>Hs: %{y:.2f} m<br>Ritorno empirico: %{x:.1f} anni<extra></extra>'},
    {x:[Number.isFinite(period)?Math.min(period,upper):upper],y:[peak.hs_m],type:'scatter',mode:'markers',name:period>upper||!Number.isFinite(period)?'Picco previsto (oltre il grafico)':'Picco previsto nel settore',marker:{color:'#b86b30',size:12,symbol:period>upper||!Number.isFinite(period)?'triangle-right':'diamond'},hovertemplate:'Hs prevista: %{y:.2f} m<extra>Picco del settore nei quattro giorni</extra>'}
  ];
  const layout={height:390,margin:{l:58,r:22,t:20,b:100},paper_bgcolor:'transparent',plot_bgcolor:'transparent',separators:',.',font:{family:'DM Sans, Arial',size:11,color:'#294b42'},xaxis:{title:'Tempo di ritorno [anni]',type:'log',range:[0,Math.log10(upper)],tickvals:[1,2,5,10,20,50,100],gridcolor:'#e5ebe2'},yaxis:{title:'Altezza significativa Hs [m]',rangemode:'nonnegative',gridcolor:'#e5ebe2'},legend:{orientation:'h',y:-.26,font:{size:9}},hovermode:'closest'};
  Plotly.react('extreme-chart',traces,layout,plotOptions);
}

function locationParameters(location) {
  const reference=seaLevelReference(location);
  const sampling=location.slope_sampling;
  const slopeLabel=sampling?`${location.slopes.length} valori · da ${num(sampling.source_min,4)} a ${num(sampling.source_max,4)} · ${sampling.method==="truncated_normal"?"Monte Carlo, normale troncata":sampling.method==="linear_range"?"intervallo regolare":"pendenze misurate"}. ${sampling.source_count} transetti; media misurata ${num(sampling.source_mean,4)}, deviazione standard ${num(sampling.source_std,4)}; seme ${sampling.seed}.`:location.slopes.map(s=>num(s,3)).join(" · ")+" (valori configurati)";
  const content=`<dl><dt>Pendenze β</dt><dd>${esc(slopeLabel)}</dd><dt>Rugosità</dt><dd>${num(location.roughness_m,4)} m</dd><dt>Punto offshore richiesto</dt><dd>${num(location.wave_point.latitude,5)}° N, ${num(location.wave_point.longitude,5)}° E</dd><dt>Cella estratta</dt><dd>${location.source.selected_point ? esc(JSON.stringify(location.source.selected_point)) : bulletin.mode==='demo'?'Non applicabile ai dati dimostrativi':'Coordinate del campione non esposte nel CSV'}</dd><dt>Modelli disponibili</dt><dd>${esc(location.valid_models.join('; '))}</dd><dt>Senza risultati validi</dt><dd>${esc(location.missing_models.join('; ')||'Nessuno')}</dd><dt>Motore di calcolo</dt><dd>${esc(bulletin.model_backend)}</dd><dt>Settori di esposizione</dt><dd>${location.wave_exposure?.sectors_deg?.length?esc(location.wave_exposure.sectors_deg.map(([a,b])=>`${num(a,0)}° → ${num(b,0)}° in senso orario`).join('; ')):'Da definire'}</dd><dt>Riferimento verticale</dt><dd>${esc(reference.label)}. ${esc(reference.detail)}</dd><dt>Note della località</dt><dd>${esc(location.notes)}</dd><dt>Download CSV</dt><dd>Contiene tutti i risultati dei modelli sull’intero periodo disponibile; tempi in UTC. Con MeteOcean include anche i contributi separati di marea e surge.</dd></dl>`;
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
    $('method-locations').innerHTML=Object.entries(bulletin.locations).map(([slug,loc])=>`<details class="location-technical" id="parametri-${esc(slug)}"><summary>${esc(loc.name)}</summary><div>${locationParameters(loc)}${Object.entries(loc.sectors||{}).map(([id,sector])=>`<h3>${esc(sector.name)}</h3>${locationParameters(sector)}`).join('')}</div></details>`).join('');
    if ($('hero-provider')) $('hero-provider').textContent=bulletin.mode==='meteocean'?'MeteOcean + NOAA':bulletin.mode==='demo'?'Dati dimostrativi':'Copernicus Marine';
    $('updated').textContent=`Metadati del bollettino: ${local(bulletin.generated_at)} · Italia`;
    const slug=new URL(window.location.href).searchParams.get('localita');
    if (slug && Object.hasOwn(bulletin.locations,slug)) {$('method-return').href=`./?localita=${encodeURIComponent(slug)}`;$('method-return').textContent=`← Torna a ${bulletin.locations[slug].name}`;}
  } catch(error) {$('method-locations').innerHTML='<p>Parametri momentaneamente non disponibili. Le spiegazioni del metodo restano consultabili.</p>';}
}

let inundationMap;

function selectedBeachUnit(location,sectorId) {
  return sectorId && location.sectors && Object.hasOwn(location.sectors,sectorId) ? location.sectors[sectorId] : location;
}

function renderSectorSelector(location,sectorId) {
  const node=$('sector-selection'), sectors=Object.entries(location.sectors||{});
  if (!node) return;
  node.hidden=!sectors.length;
  if (!sectors.length) return;
  node.innerHTML=`<label for="beach-sector">Settore costiero</label><select id="beach-sector">${sectors.map(([id,sector])=>`<option value="${esc(id)}" ${id===sectorId?'selected':''}>${esc(sector.name)}</option>`).join('')}</select><p class="small muted">Direzioni di esposizione, onde, marea, surge e riferimento storico sono comuni all’area. Transetti, strutture esposte, quote e risultati appartengono al settore costiero scelto.</p>`;
  $('beach-sector').addEventListener('change',event=>{
    const url=new URL(window.location.href);
    if (event.target.value) url.searchParams.set('settore',event.target.value); else url.searchParams.delete('settore');
    history.pushState({},'',url);renderRoute();
  });
}

function inundationExtentLabel(percentile) {
  return percentile===95?'Estensione più ampia':'Estensione più contenuta';
}

function inundationMapText(data,now=Date.now()) {
  if (!data) return 'DEM e cartografia non configurati per questo tratto.';
  if (data.status!=='available') return `Mappa non disponibile: ${data.reason||'dati da verificare'}`;
  const expired=now>=Date.parse(data.period_to);
  const direction=data.hours_non_frontal?` In ${data.hours_non_frontal} ore le onde provengono da altre direzioni: l’estensione non tiene conto del riparo della costa e richiede particolare cautela.`:'';
  const unknown=data.hours_direction_unknown?` In ${data.hours_direction_unknown} ore il confronto con l’esposizione non è disponibile.`:'';
  return `${expired?'Periodo concluso: questa mappa non descrive le prossime ore. ':''}Inviluppo delle 96 ore dell’elaborazione: ${local(data.period_from)} — ${local(data.period_to)}. Le due aree mostrano quanto cambia l’estensione usando stime diverse dei modelli, considerando le quote più alte del periodo. Non sono probabilità di inondazione né profondità d’acqua.${direction}${unknown}`;
}

function inundationDownloads(data) {
  if (data?.status!=='available' || !data.geojson_export) return '';
  if (data.geojson_export.status!=='available') return `GeoJSON non disponibile per questa elaborazione: ${esc(data.geojson_export.reason||'esportazione da verificare')}.`;
  return data.geojson_export.files.filter(file=>['aree','limiti'].includes(file.kind) && /^data\/maps\/[a-z0-9-]+\/[a-z0-9-]+-\d{8}T\d{6}Z-(?:aree|limiti)\.geojson$/.test(file.url))
    .map(file=>`<a href="${esc(file.url)}" download="${esc(file.filename)}">${file.kind==='aree'?'Scarica le aree':'Scarica i limiti'} (GeoJSON) ↓</a>`).join(' · ');
}

function renderInundation(location) {
  const panel=$('inundation-panel');
  if (!panel) return;
  if (inundationMap) {inundationMap.remove();inundationMap=null;}
  const data=location.inundation_map;
  panel.hidden=!location.mapping && !data;
  if (panel.hidden) return;
  $('inundation-description').textContent=inundationMapText(data);
  $('inundation-credit').textContent=data?.status==='available'?`Rilievo: ${data.survey_credit} · ${data.survey_date}. Licenza: ${data.license}. Quote: ${data.vertical_reference}.`:'';
  const downloads=$('inundation-downloads');
  if (downloads) downloads.innerHTML=inundationDownloads(data);
  $('inundation-legend').innerHTML=data?.status==='available'?data.layers.slice().sort((a,b)=>b.percentile-a.percentile).map(layer=>`<span class="map-key map-key-${layer.percentile}">${inundationExtentLabel(layer.percentile)} · quota ${num(layer.level_m)} m · ${local(layer.peak_time)}</span>`).join(''):'';
  if (data?.status==='available' && data.terrain && data.terrain_scale) {
    const scale=data.terrain_scale;
    const colors=scale.colors.filter(c=>/^#[0-9a-f]{6}$/i.test(c));
    $('inundation-legend').innerHTML+=`<span class="terrain-key" title="${esc(scale.scale_note)}">Sfondo DEM · quota del terreno: ${num(scale.min_m)} m <span style="display:inline-block;width:100px;height:12px;background:linear-gradient(to right,${colors.join(',')})"></span> ${num(scale.max_m)} m. Colori ai limiti della scala per le quote esterne.</span>`;
  }
  const canvas=$('inundation-map');canvas.hidden=data?.status!=='available';
  if (data?.status!=='available') return;
  if (!window.L) {canvas.hidden=true;$('inundation-description').textContent+=' Mappa interattiva momentaneamente non disponibile.';return;}
  inundationMap=L.map('inundation-map',{scrollWheelZoom:false});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22,maxNativeZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(inundationMap);
  const overlays={};
  if (data.orthophoto) {
    overlays['Ortofotomosaico']=L.imageOverlay(data.orthophoto,data.bounds,{opacity:1,attribution:esc(data.survey_credit)}).addTo(inundationMap);
  } else if (data.terrain) {
    overlays['DEM · quote del terreno']=L.imageOverlay(data.terrain,data.bounds,{opacity:1,attribution:esc(data.survey_credit)}).addTo(inundationMap);
  }
  // Larger envelope underneath; P75 remains distinguishable where they overlap.
  for (const layer of data.layers.slice().sort((a,b)=>b.percentile-a.percentile)) {
    overlays[inundationExtentLabel(layer.percentile)]=L.imageOverlay(layer.image,data.bounds).addTo(inundationMap);
  }
  L.control.layers(null,overlays,{collapsed:false}).addTo(inundationMap);
  inundationMap.fitBounds(data.bounds,{padding:[12,12]});
}

function renderDetail(slug) {
  const parent=bulletin.locations[slug];
  const requestedSector=new URL(window.location.href).searchParams.get('settore');
  const sectorId=parent.sectors && Object.hasOwn(parent.sectors,requestedSector)?requestedSector:Object.keys(parent.sectors||{})[0]||null;
  const location=selectedBeachUnit(parent,sectorId);
  renderSectorSelector(parent,sectorId);
  renderInundation(location);
  const rows=windowRows(location);
  document.title=`${location.name} · Onde a riva`;
  $('location-title').textContent=location.name;
  $('area').textContent=location===parent?location.area:`${parent.name} · ${location.area}`;
  const reference=seaLevelReference(location);
  $('twl-reference-label').textContent=`metri · zero: ${reference.label}`;
  $('sealevel-caption').innerHTML=`${location.sea_level_source?.mode==='noaa_tide_meteocean_surge'?'Marea, storm surge e loro somma sono separati e usano la stessa scala verticale. I valori negativi indicano un livello sotto il riferimento. ':''}Zero del livello marino: ${esc(reference.label)}. <a href="metodo.html?localita=${encodeURIComponent(slug)}#zero">Riferimento delle quote ↗</a>`;
  $('technical-link').href=`metodo.html?localita=${encodeURIComponent(slug)}`;
  $('download').href=location.csv;
  const valid=rows.filter(r=>hasFilteredStatistics(r) && Number.isFinite(r.twl_p95_m));
  const futureEnd=bulletin.display_to ? Date.parse(bulletin.display_to) : Math.floor(Date.now()/hourMs)*hourMs + bulletin.display_hours*hourMs;
  const insufficient = new Date(location.valid_to).getTime()<futureEnd;
  const invalid=rows.filter(r=>!r.n_estimates).length;
  const staleStatistics=rows.some(r=>!hasFilteredStatistics(r));
  setNotice(!rows.length ? 'Bollettino scaduto: nessun campione futuro disponibile. È necessario un aggiornamento.' : `${staleStatistics?'Le stime devono essere ricalcolate con il metodo attuale: il grafico dell’acqua e i colori non sono disponibili per questi dati. ':''}${insufficient?'Copertura parziale: non sono disponibili tutte le prossime 96 ore. ':''}${invalid?`${invalid} ore senza risultati validi dei modelli.`:''}`,location);
  $('period').textContent=rows.length ? `${local(rows[0].time)} — ${local(rows[rows.length-1].time)} · dati ogni ora · ora italiana` : 'Nessuna previsione futura disponibile';
  const peak=valid.length ? valid.reduce((best,row)=>row.twl_p95_m>best.twl_p95_m?row:best) : null;
  const hs=rows.length ? Math.max(...rows.map(r=>r.hs_m)) : null;
  $('metrics').innerHTML=[
    ['Livello alto stimato',`${num(peak?.twl_p95_m)} <small>m</small>`,peak ? `Valore più alto del bordo superiore della fascia delle stime · ${local(peak.time)} · quote provvisorie` : 'Dati non disponibili'],
    ['Massima altezza delle onde',`${num(hs)} <small>m</small>`,'Altezza significativa: un valore rappresentativo delle onde più alte, calcolato al largo della località'],
    ['Modelli a confronto',`${location.valid_models.length} <small>/ ${bulletin.model_order.length}</small>`,`${location.slopes.length} ${location.slopes.length===1?"pendenza della spiaggia: il calcolo usa questa pendenza":"pendenze della spiaggia: ripetiamo il calcolo con ciascuna pendenza"}`]
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
    if (inundationMap) {inundationMap.remove();inundationMap=null;}
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
    if (bulletin.schema_version!==1 || !bulletin.locations || !['demo','copernicus','meteocean'].includes(bulletin.mode)) throw new Error('Formato del bollettino non riconosciuto');
    if ($('hero-provider')) $('hero-provider').textContent=bulletin.mode==='meteocean'?'MeteOcean + NOAA':bulletin.mode==='demo'?'Dati dimostrativi':'Copernicus Marine';
    $('updated').textContent=`Ultima elaborazione: ${local(bulletin.generated_at)} · Italia`;
    document.addEventListener('click',event=>{
      const link=event.target.closest('a[href]');
      if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button!==0) return;
      const url=new URL(link.href);
      if (url.origin===location.origin && url.pathname===location.pathname && !url.hash && !link.hasAttribute('download')) {
        event.preventDefault(); history.pushState({},'',url);renderRoute();window.scrollTo({top:0,behavior:'smooth'});
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
