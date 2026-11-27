'use strict';
// Display-only sketch: common hour, common datum, no horizontal reach calculation.
let beachProfileObserver=null;
function beachProfileSnapshot(unit,rows){
  const valid=rows.filter(r=>hasFilteredStatistics(r)&&r.n_estimates>0&&Number.isFinite(r.twl_mean_m)&&Number.isFinite(r.twl_p95_m));
  if(!valid.length)return {status:'unavailable',structures:[]};
  const states=valid.map(r=>forecastExposure(unit,r)),coverage={exposure_policy:'frontal_hours_only_v1',hours_total:valid.length,hours_frontal:states.filter(s=>s===true).length,hours_non_frontal:states.filter(s=>s===false).length,hours_direction_unknown:states.filter(s=>s===null).length};
  const eligible=valid.filter((r,i)=>states[i]===true),peak=eligible.reduce((best,r)=>!best||r.twl_mean_m>best.twl_mean_m?r:best,null);
  if(!peak)return {status:coverage.hours_direction_unknown?'unavailable':'not_applicable',reason_code:coverage.hours_direction_unknown?'unknown_direction':'nonfrontal',key:coverage.hours_direction_unknown?'unavailable':'gray',structures:[],...coverage};
  const state=rowImpact(referenceThreshold(unit),peak,unit),trend=assessTrend(unit,[peak]);
  const tail=Number.isFinite(peak.twl_p995_m)&&peak.twl_p995_m>=peak.twl_p95_m?peak.twl_p995_m:null;
  return {status:'available',selection:'peak_of_filtered_mean_frontal',time:peak.time,mean_m:peak.twl_mean_m,p95_m:peak.twl_p95_m,p995_m:tail,
    n_estimates:peak.n_estimates,...coverage,exposed:forecastExposure(unit,peak),state:state.kind,key:trend.key,direction_deg:peak.direction_deg,
    structures:(unit.thresholds||[]).map(t=>{const s=rowImpact(t,peak,unit),fraction=s.kind==='numeric'&&s.fraction>=0&&s.fraction<=1?s.fraction:null;
      return {id:t.id,label:assetName(t)||t.id,elevation_m:t.elevation_m,state:s.kind,fraction,count:fraction===null?null:Math.round(fraction*peak.n_estimates),season_unconfirmed:peak.thresholds?.find(s=>s.id===t.id)?.active==null};})};
}
function beachProfilePoint(value,width,levels){
  const floor=Math.min(0,...levels),ceiling=Math.max(.5,...levels)*1.15,shore=width*.18,right=width-24;
  return {x:shore+(right-shore)*Math.min(1,Math.max(0,value/ceiling)),y:226-(value-floor)/(ceiling-floor)*156,shore,right,ceiling,floor};
}
function beachProfileSvg(data,width){
  width=Math.max(250,width||640);
  const levels=[0,data.mean_m,data.p95_m,data.p995_m,...data.structures.map(s=>s.elevation_m)].filter(Number.isFinite),point=v=>beachProfilePoint(v,width,levels),zero=point(0),top=point(zero.ceiling);
  const wet=z=>{const p=point(z),sy=z<=0?p.y:zero.y;
    return `M5 ${sy-3} C${zero.shore*.18} ${sy-10} ${zero.shore*.34} ${sy+5} ${zero.shore*.48} ${sy-3} S${zero.shore*.8} ${sy-10} ${zero.shore} ${sy-3} C${zero.shore+(p.x-zero.shore)*.22} ${sy-12} ${p.x-(p.x-zero.shore)*.2} ${p.y-12} ${p.x} ${p.y}`;};
  const fill=z=>wet(z)+(z>0?`L${zero.shore} ${zero.y}L5 ${zero.y+18}Z`:`L${zero.shore} 248L5 248Z`);
  const tail=data.p995_m===null?'':(()=>{const p=point(data.p995_m);return `<path class="beach-tail-line" d="M${zero.shore} ${zero.y}L${p.x} ${p.y}"/><circle class="beach-tail-end" cx="${p.x}" cy="${p.y}" r="3.5"/>`;})();
  const size=data.structures.length>2?20:32;
  const markers=data.structures.filter(s=>Number.isFinite(s.elevation_m)).map(s=>{const index=data.structures.indexOf(s)+1,p=point(s.elevation_m),icon=impactIcon(s.id).replace('<svg ',`<svg x="${p.x-size/2}" y="${p.y-size-11}" `).replace('width="32" height="34"',`width="${size}" height="${size}"`);
    return `<g aria-label="${esc(s.label)}: quota ${num(s.elevation_m)} metri"><title>${esc(s.label)} · quota ${num(s.elevation_m)} m</title>${icon}<circle class="beach-structure-dot" cx="${p.x}" cy="${p.y}" r="8"/><text class="beach-index" x="${p.x}" y="${p.y+4}" text-anchor="middle">${index}</text></g>`;}).join('');
  return `<svg viewBox="0 0 ${width} 280" role="img" aria-labelledby="beach-profile-title beach-profile-desc"><title id="beach-profile-title">Stime del livello dell’acqua e quote delle strutture</title><desc id="beach-profile-desc">Profilo schematico, distanze non in scala. Media, 95° percentile e linea punteggiata al 99,5° percentile dei risultati filtrati, tutti alla stessa ora. Le percentuali comprendono anche risultati oltre le linee mostrate.</desc><path class="beach-sand" d="M${zero.shore} ${zero.y}L${top.right} ${top.y}V248H${zero.shore}Z"/><path class="beach-surface" d="M${zero.shore} ${zero.y}L${top.right} ${top.y}"/><path class="beach-upper-water" d="${fill(data.p95_m)}"/><path class="beach-mean-water" d="${fill(data.mean_m)}"/><path class="beach-wave-line" d="${wet(data.mean_m)}"/><line class="beach-zero" x1="5" y1="${zero.y}" x2="${zero.right}" y2="${zero.y}"/>${tail}${markers}<text class="beach-small" x="5" y="${Math.max(25,zero.y-29)}">Mare</text><text class="beach-small" x="${zero.right}" y="266" text-anchor="end">Spiaggia · verso terra →</text><text class="beach-small" x="5" y="279">Zero di riferimento</text></svg>`;
}
function beachProfilePhrase(asset){
  if(asset.state==='inactive')return 'Fuori stagione';
  if(asset.state==='nonfrontal')return 'Confronto non disponibile: onde da altre direzioni';
  if(asset.fraction===null)return 'Confronto non disponibile';
  const article=asset.fraction*100<1?'nello':'nel';
  return `quota superata ${article} <strong>${percentage(asset.fraction)}</strong> delle stime`;
}
function renderBeachProfile(unit,rows){
  if(beachProfileObserver){beachProfileObserver.disconnect();beachProfileObserver=null;}
  const data=beachProfileSnapshot(unit,rows),panel=$('outlook-panel');
  $('outlook-title').textContent='Fin dove potrebbe risalire l’acqua?';panel.className=`panel outlook-panel reader-outlook beach-profile-panel impact-${data.key||'unavailable'}`;
  if(data.status!=='available'){
    const away=data.reason_code==='nonfrontal',unknown=data.reason_code==='unknown_direction';
    if(away||unknown)$('outlook-title').textContent=away?'Le onde non sono dirette verso questa spiaggia':'Direzione delle onde non valutabile';
    $('outlook').innerHTML=away||unknown?'<p class="beach-direction-note"><strong>Risalita e percentuali non rappresentate per il periodo selezionato.</strong></p><p>Questo non indica mare calmo o assenza di effetti del livello marino.</p><p class="small"><a href="#waves-disclosure">Consulta onde al largo, marea e surge ↓</a></p>':'<p>Nessun risultato filtrato valido nelle ore selezionate.</p>';
    readerHelp('outlook-info','Profilo e sintesi TWL usano soltanto ore con onde nei settori di esposizione configurati. Ore fuori settore o senza direzione verificata sono escluse, senza modificare le onde al largo, il livello del mare o i calcoli originali nel CSV. Il filtro non simula il riparo della costa e non dimostra assenza di pericolo.','modelli');bindInfoButton('outlook-info-toggle');return;
  }
  const direction=data.exposed===false?'Le onde provengono da altre direzioni: il riparo della costa non è simulato.':data.state==='unknown-direction'?'La direzione delle onde non è valutabile.':'';
  $('outlook').innerHTML=`<p class="beach-profile-time"><strong>Ora rappresentata: ${esc(local(data.time))}–${esc(timeOnly(new Date(Date.parse(data.time)+hourMs)))} · ora italiana</strong><span>Picco della media nelle ore con onde dirette verso la spiaggia ${readerDay()?'nel giorno selezionato':'nelle ore future mostrate'}.</span></p>${direction?`<p class="beach-direction-note">${esc(direction)}</p>`:''}<div id="beach-profile-drawing" class="beach-profile-drawing${data.exposed===false?' beach-away':''}"></div><div class="beach-profile-legend${data.exposed===false?' beach-away':''}"><span><i class="beach-mean-key"></i>Quota media ${num(data.mean_m)} m</span><span><i class="beach-upper-key"></i>Stime più alte (P95) ${num(data.p95_m)} m</span>${data.p995_m!==null?`<span><i class="beach-tail-key"></i>Coda delle stime (P99,5) ${num(data.p995_m)} m</span>`:'<span>P99,5 non disponibile in questa elaborazione.</span>'}</div><div class="beach-profile-assets">${data.structures.map((a,i)=>`<article><div class="beach-asset-heading"><span class="beach-asset-number">${i+1}</span>${impactIcon(a.id)}<strong>${esc(a.label)}</strong><span>quota ${num(a.elevation_m)} m</span></div><p class="beach-reach">${beachProfilePhrase(a)}</p>${a.fraction!==null?`<div class="beach-meter" role="img" aria-label="${esc(a.label)}: ${percentage(a.fraction)} delle stime sopra quota all’ora rappresentata"><span style="width:${a.fraction*100}%"></span></div>`:''}${a.season_unconfirmed?'<span class="beach-season-note">Stagione di attività da confermare.</span>':''}</article>`).join('')}</div><p class="beach-profile-note">Profilo schematico, distanze non in scala. Le quote del modello e del rilievo richiedono un raccordo locale validato.</p><p class="beach-profile-note">Percentuali all’ora rappresentata, calcolate sulle stime filtrate (modelli × pendenze), anche oltre la linea punteggiata. Non sono probabilità di allagamento. Le schede giornaliere sotto mostrano i massimi del giorno.</p>`;
  const canvas=$('beach-profile-drawing'),draw=()=>{canvas.innerHTML=beachProfileSvg(data,canvas.clientWidth||640);};draw();
  if(typeof ResizeObserver!=='undefined'){beachProfileObserver=new ResizeObserver(draw);beachProfileObserver.observe(canvas);}
  readerHelp('outlook-info','Il disegno usa l’ora con il TWL medio filtrato più alto fra le ore con onde nei settori di esposizione del periodo mostrato. TWL = runup delle onde + livello del mare. Il P99,5 è un riferimento della coda, non il massimo, e non modifica colori, soglie o mappe. Le percentuali contano le combinazioni modello × pendenza sopra quota nella stessa ora, dopo il filtro ±3σ. Il profilo e le posizioni delle strutture sono illustrativi; non sono un transetto misurato o una distanza prevista di inondazione.','zero');bindInfoButton('outlook-info-toggle');
}

// Copies for drawing only: preserve offshore waves, tide, surge and original CSVs.
function coastalChartRows(unit,rows){
  const fields=['twl_mean_m','twl_p05_m','twl_p25_m','twl_p75_m','twl_p95_m','twl_p995_m'];
  return rows.map(row=>forecastExposure(unit,row)===true?row:{...row,...Object.fromEntries(fields.map(k=>[k,null]))});
}
