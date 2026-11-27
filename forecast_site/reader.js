'use strict';
// Presentation only. Classification, original hours and model outputs stay in app.js.
let coastSectorMap=null,coastMapSignature='',readerChartHours=0,readerPlotRows=[],readerExpanded=null,readerPreviousFocus=null,readerCurrentUnit=null,readerResizeTimer=null;
function readerSmallScreen(){return !!window.matchMedia?.('(max-width: 600px)').matches;}
function readerUrl(){return new URL(window.location?.href||'https://example.test/');}
function readerDay(){const day=readerUrl().searchParams.get('giorno');return /^\d{4}-\d{2}-\d{2}$/.test(day||'')?day:null;}
function readerAllRows(unit){const a=Date.parse(bulletin.display_from),b=Date.parse(bulletin.display_to);return (unit.hourly||[]).filter(r=>(!Number.isFinite(a)||Date.parse(r.time)>=a)&&(!Number.isFinite(b)||Date.parse(r.time)<b));}
function readerViewRows(unit,now=Date.now()){const day=readerDay();return day?readerAllRows(unit).filter(r=>italianTime(r.time).slice(0,10)===day):windowRows(unit,now);}
function readerChooseDay(day){const url=readerUrl();if(day)url.searchParams.set('giorno',day);else url.searchParams.delete('giorno');url.hash='daily-summary';history.replaceState({},'',url);readerChartHours=0;renderRoute();}
function readerDayLabel(date,now=Date.now()){
  const today=italianTime(now).slice(0,10),tomorrow=new Date(Date.parse(today+'T12:00Z')+86400000).toISOString().slice(0,10);
  const label=new Date(date+'T12:00Z').toLocaleDateString('it-IT',{timeZone:'Europe/Rome',day:'numeric',month:'short'});
  return (date===today?'Oggi · ':date===tomorrow?'Domani · ':'')+label;
}
function readerShortName(name){return String(name).replace(/^Da\s+/i,'').replace(/\s+a\s+(?=Molo|Piazza)/gi,' – ').replace(/Molo\s+/g,'').replace(/poseidon/gi,'Poseidon');}
function readerImpactLabel(key,fraction){return key==='gray'?'Direzione da verificare':key==='white'?(fraction>0?'Superamenti isolati':'Stime sotto quota'):key==='yellow'?'Risultati sopra quota':key==='orange'?'Più risultati sopra quota':'Confronto non disponibile';}
function readerHelp(id,text,anchor){const node=$(id);if(!node)return;node.innerHTML=`<button type="button" class="info-close" aria-label="Chiudi spiegazione">×</button><span>${esc(text)}</span><a class="info-more" href="metodo.html#${anchor}">Approfondisci il metodo ↗</a>`;}
function readerBindInfo(id){
  const button=$(id);if(!button)return;const parent=button.parentElement,popup=button.nextElementSibling;
  button.onclick=()=>{button.setAttribute('aria-expanded','true');};button.onfocus=()=>button.setAttribute('aria-expanded','true');
  button.onblur=event=>{if(!parent?.contains(event.relatedTarget))button.setAttribute('aria-expanded','false');};
  button.onkeydown=event=>{if(event.key==='Escape'){button.setAttribute('aria-expanded','false');button.blur();}};
  if(parent){parent.onmouseenter=()=>button.setAttribute('aria-expanded','true');parent.onmouseleave=()=>{if(!parent.contains(document.activeElement))button.setAttribute('aria-expanded','false');};}
  const close=popup?.querySelector('.info-close');if(close)close.onclick=()=>{button.focus();button.setAttribute('aria-expanded','false');};
}
function readerAssets(unit){const all=unit.thresholds||[];const preferred=all.filter(t=>/chiosc|passeggiat|strutture_turistiche_fisse|infrastrutture_fisse/i.test(t.id+' '+assetName(t)));return preferred.length?preferred:all.slice(0,2);}
function readerSetNotice(extra='',location=null,now=Date.now()){
  const node=$('notice'),age=(now-Date.parse(bulletin.generated_at))/hourMs,stale=age>(bulletin.stale_after_hours||30),expired=Number.isFinite(Date.parse(bulletin.display_to))&&now>=Date.parse(bulletin.display_to);
  const demo=bulletin.mode==='demo',state=demo?'Dati dimostrativi':expired?'Periodo concluso':stale?'Aggiornamento in ritardo':'Dati aggiornati';
  node.className='notice reader-notice'+(demo?' demo':stale||expired?' error':'');
  const source=noticeWaveSource(location),next=bulletin.mode==='meteocean'?nextSiteAcquisition(now):nextWavePublication(now);
  const provider=demo?'Dati sintetici.':bulletin.mode==='meteocean'?'Onde e sovralzo meteorologico MeteOcean – UniGE; marea astronomica NOAA.':source.kind==='cycle'?'Corsa del modello Copernicus del '+noticeDate(source.time)+'.':'Copernicus Marine; corsa del modello non disponibile o diversa fra località.';
  node.innerHTML=`<div><strong>${stale||expired?'◷':'•'} ${esc(state)}</strong><span> · Bollettino del ${esc(noticeDate(bulletin.generated_at))}</span></div><details><summary>Informazioni sui dati</summary><p>${esc(provider)} ${next?esc((bulletin.mode==='meteocean'?'Prossima acquisizione prevista: ':'Prossima uscita prevista: ')+noticeDate(next)+', ora italiana.'):''}</p>${extra?`<p>${esc(extra)}</p>`:''}<a href="metodo.html">Fonti e limiti ↗</a></details>${expired?'<p>Le stime ancora future non sono disponibili. Attendere un nuovo bollettino.</p>':stale?'<p>Consulta la data dell’elaborazione: l’aggiornamento atteso non è ancora disponibile.</p>':''}`;
  if(extra&&!expired)node.innerHTML+=`<p class="coverage-note">${esc(extra)}</p>`;
}
function readerRenderLocations(){
  $('location-cards').innerHTML=Object.entries(bulletin.locations).map(([slug,parent],i)=>{
    const units=Object.values(parent.sectors||{}),all=units.length?units:[parent];
    const summaries=all.map(u=>({u,rows:windowRows(u)}));const results=summaries.map(s=>assessTrend(s.u,s.rows));
    const label=results.some(r=>['orange','yellow'].includes(r.key))?'Consulta quote e orari dei settori':results.some(r=>r.key==='gray')?'Confronto con le quote limitato dalla direzione':'Esplora le stime disponibili';
    return `<a class="location-card" href="?localita=${esc(slug)}"><div><div class="card-top"><span class="card-index">LOCALITÀ / ${i+1}</span><span class="card-arrow" aria-hidden="true">↗</span></div><h3>${esc(parent.name)}</h3><p>${esc(parent.area)}</p></div><div class="card-bottom"><span>${units.length?units.length+' settori costieri':'Spiaggia intera'}<br>${esc(label)}</span><span>Apri il bollettino →</span></div></a>`;
  }).join('');
}
function readerRenderSectorSelector(parent,sectorId){
  const node=$('sector-selection'),entries=Object.entries(parent.sectors||{}),disclosure=$('sector-map-disclosure');if(!node)return;
  node.hidden=!entries.length;if(disclosure)disclosure.hidden=!entries.length;
  if(!entries.length){if(coastSectorMap){coastSectorMap.remove();coastSectorMap=null;}return;}
  node.innerHTML=`<label for="beach-sector">Tratto di spiaggia</label><select id="beach-sector">${entries.map(([key,s],i)=>`<option value="${esc(key)}"${key===sectorId?' selected':''}>Settore ${i+1} · ${esc(readerShortName(s.name))}</option>`).join('')}</select>`;
  $('beach-sector').onchange=event=>{const url=readerUrl();url.searchParams.set('settore',event.target.value);history.pushState({},'',url);renderRoute();};
  const draw=()=>{
    if(!window.L||!disclosure?.open)return;
    if(coastSectorMap)coastSectorMap.remove();
    coastSectorMap=L.map('sector-map',{scrollWheelZoom:false});
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(coastSectorMap);
    const bounds=[];
    for(const [key,s] of entries){
      const meta=s.inundation_map,selected=key===sectorId;let feature;
      if(meta?.sector_geometry)feature=L.geoJSON(meta.sector_geometry,{style:{color:selected?'#154f55':'#647e74',weight:selected?3:1,fillOpacity:selected ? .35 : .08}}).addTo(coastSectorMap);
      else if(meta?.bounds)feature=L.rectangle(meta.bounds,{color:selected?'#154f55':'#647e74',weight:2,fillOpacity:.12}).addTo(coastSectorMap);
      if(!feature)continue;
      bounds.push(feature.getBounds());feature.bindTooltip(esc(readerShortName(s.name)),{sticky:true});
      feature.on('click',()=>{const url=readerUrl();url.searchParams.set('settore',key);history.pushState({},'',url);renderRoute();});
    }
    if(bounds.length)coastSectorMap.fitBounds(L.latLngBounds(bounds.map(b=>[b.getSouthWest(),b.getNorthEast()]).flat()),{padding:[16,16]});
    else{$('sector-map').textContent='Cartografia dei settori non ancora disponibile; usa il menu dei tratti.';coastSectorMap.remove();coastSectorMap=null;}
  };
  if(disclosure){disclosure.ontoggle=draw;draw();}
}
function readerSynthesis(assets,trend){
  const events=assets.filter(a=>['yellow','orange'].includes(a.trend.key));
  if(events.length)return events.map(a=>`${assetName(a.threshold)}: risultati sopra quota${a.events.length?' ('+eventLabel(a.events[0])+')':''}.`).join(' ');
  if(trend.key==='gray')return 'Le onde non provengono dalle direzioni considerate per questa spiaggia: il confronto con le quote richiede cautela.';
  if(assets.some(a=>a.peak))return assets.some(a=>a.peak?.fraction>0)?'Compaiono soltanto superamenti isolati delle quote delle strutture.':'I risultati restano sotto le quote delle strutture confrontate.';
  return trend.inactive?'Le strutture stagionali sono fuori dal periodo di confronto.':'Il confronto non è disponibile per le ore selezionate.';
}
function readerRenderOutlook(unit,rows,trend){
  if(typeof renderBeachProfile==='function')return renderBeachProfile(unit,rows);
  const all=(unit.thresholds||[]).map(t=>outlookAsset(t,rows,unit));
  $('outlook-title').textContent=readerDay()?'Sintesi del giorno':'Sintesi dei prossimi giorni';$('outlook-panel').className=`panel outlook-panel reader-outlook impact-${trend.key}`;
  const cards=all.map(a=>{const fraction=a.peak?.fraction,key=a.trend.key;
    return `<article class="outlook-asset impact-${key}"><div class="outlook-asset-name">${impactIcon(a.threshold.id)}<div><strong>${esc(assetName(a.threshold))}</strong><span>Quota ${num(a.threshold.elevation_m)} m</span></div></div><span class="impact-badge impact-${key}">${esc(a.trend.inactive?'Fuori stagione':readerImpactLabel(key,fraction))}</span><div class="outlook-percentage"><span>${a.peak?'Risultati sopra quota':'Non valutato'}</span><strong>${maximumPercentage(fraction)}</strong></div>${a.peak?`<div class="outlook-colorbar" role="img" aria-label="${esc(assetName(a.threshold))}: ${esc(percentage(fraction))} dei risultati sopra quota"><span style="width:${fraction*100}%"></span></div>`:''}${a.events.length?`<p class="outlook-asset-time"><strong>Quando:</strong> ${esc(eventLabel(a.events[0]))}</p>`:fraction>0?'<p class="outlook-asset-time">Superamenti isolati, fuori dalla fascia di confronto.</p>':''}${a.events.length>1?`<details class="outlook-windows"><summary>Tutti gli orari (${a.events.length})</summary><ul>${a.events.map(e=>`<li>${esc(eventLabel(e))} · ${esc(maximumPercentage(e.peak))} dei risultati</li>`).join('')}</ul></details>`:''}</article>`;
  }).join('');
  $('outlook').innerHTML=`<h3 class="outlook-summary">${esc(readerSynthesis(all,trend))}</h3><div class="outlook-assets">${cards}</div><p class="reader-meaning"><strong>Confronto tra quote, non probabilità di allagamento.</strong> Le percentuali riguardano risultati dei modelli, non porzioni di spiaggia.</p>${trend.key==='gray'?'<p>Il grigio non indica condizioni sicure. Il livello del mare può comunque avere effetti sulla costa.</p>':''}`;
  readerHelp('outlook-info','Ogni risultato combina un modello e una pendenza misurata. I colori confrontano le quote con il 75° e 95° percentile dopo il filtro; il grigio esclude il confronto per onde da altre direzioni.','colori');bindInfoButton('outlook-info-toggle');
}
function readerRenderDaily(unit,rows){
  const reference=referenceThreshold(unit),trend=assessTrend(unit,rows,reference);readerRenderOutlook(unit,rows,trend);
  const all=readerAllRows(unit),groups=groupsByDay(all.length?all:rows);$('daily-summary').hidden=!groups.length;
  $('daily-reference').textContent=reference?`Colore riferito a ${assetName(reference)} · quota ${num(reference.elevation_m)} m`:'';
  readerHelp('daily-info','Scegli una data per leggere il suo bollettino e la sua mappa. La percentuale è il maggiore superamento orario fra i risultati valutabili, non una probabilità. Le giornate parziali mostrano solo le ore disponibili.','colori');bindInfoButton('daily-info-toggle');
  const selected=readerDay();
  $('daily').innerHTML=groups.map(group=>{
    const date=italianTime(group[0].time).slice(0,10),r=assessTrend(unit,group,reference),assets=readerAssets(unit).map(t=>outlookAsset(t,group,unit));
    const finish=new Date(Date.parse(group.at(-1).time)+hourMs),end=italianTime(finish).slice(0,10)!==date?'24:00':timeOnly(finish),begin=timeOnly(group[0].time),partial=begin!=='00:00'||end!=='24:00';
    return `<button type="button" class="day-card impact-day compact-day impact-${r.key}${selected===date?' selected-day':''}" data-reader-day="${date}" aria-pressed="${selected===date}"><span class="day-heading"><strong>${esc(readerDayLabel(date))}</strong><span class="day-color" aria-label="${esc(readerImpactLabel(r.key))}"></span></span><span class="day-hours">${begin}–${end}${partial?' · giornata parziale':''}</span>${assets.map(a=>`<span class="day-structure">${impactIcon(a.threshold.id)}<span>${esc(assetName(a.threshold))}</span><strong>${esc(percentage(a.peak?.fraction))}</strong></span>`).join('')}${r.key==='gray'?'<span class="day-note">Direzione da verificare</span>':''}</button>`;
  }).join('');
  for(const button of $('daily').querySelectorAll('[data-reader-day]'))button.onclick=()=>readerChooseDay(button.dataset.readerDay);
  if($('all-days')){$('all-days').onclick=()=>readerChooseDay(null);$('all-days').setAttribute('aria-pressed',String(!selected));}
  if($('reader-scope'))$('reader-scope').textContent=selected?`${readerDayLabel(selected)} · include eventuali ore trascorse.`:`${rows.length} ore ancora disponibili nel bollettino. Le schede giornaliere includono l’intera data.`;
}
function readerRenderMetrics(unit,rows){
  const valid=rows.filter(r=>hasFilteredStatistics(r)&&Number.isFinite(r.twl_p95_m)),peak=valid.reduce((b,r)=>!b||r.twl_p95_m>b.twl_p95_m?r:b,null),wave=wavePeak(rows);
  const cards=[{id:'ingression',label:'Quota alta stimata dell’acqua (TWL)',value:`${num(peak?.twl_p95_m)} <small>m</small>`,time:peak?.time,info:'È la quota più alta del 95° percentile filtrato nelle ore mostrate. Comprende onde e livello del mare, rispetto allo zero del modello: non è una profondità d’acqua.',anchor:'zero'},
  {id:'wave',label:'Onde al largo · altezza, periodo e provenienza',value:`${num(wave?.hs_m)} <small>m</small><span class="metric-period"> · ${num(wave?.tp_s,1)} <small>s</small></span><span class="metric-direction"> · da ${compass16(wave?.direction_deg)}</span>`,time:wave?.time,info:'Altezza significativa massima con periodo e provenienza alla stessa ora. Singole onde possono essere più alte. Onde e TWL possono avere picchi in orari diversi.',anchor:'modelli'}];
  $('metrics').innerHTML=cards.map(c=>`<div class="metric"><div class="metric-header"><div class="metric-label">${c.label}</div><span class="metric-info"><button type="button" id="metric-${c.id}-toggle" class="metric-info-toggle" aria-label="Informazioni: ${esc(c.label)}" aria-controls="metric-${c.id}-info" aria-expanded="false">i</button><span id="metric-${c.id}-info" class="metric-tooltip" role="tooltip"></span></span></div><div class="metric-value">${c.value}</div><div class="metric-note">${c.time?esc(local(c.time)):'Dati non disponibili'}</div></div>`).join('');
  for(const c of cards){readerHelp(`metric-${c.id}-info`,c.info,c.anchor);bindInfoButton(`metric-${c.id}-toggle`);}
}
function readerMapPeriod(data){const day=readerDay();if(day&&data?.daily){const selected=data.daily.find(d=>d.date===day);if(selected)return {...data,...selected};return {...data,status:'unavailable',reason:'Nessuna mappa disponibile per la data selezionata.'};}return data;}
function readerRenderInundation(unit,requested){
  const panel=$('inundation-panel');if(!panel)return;const original=unit.inundation_map,data=readerMapPeriod(original);
  panel.hidden=!unit.mapping&&!data;if(panel.hidden){if(inundationMap){inundationMap.remove();inundationMap=null;}coastMapSignature='';return;}
  const canvas=$('inundation-map'),available=data?.status==='available';canvas.hidden=!available;
  $('inundation-description').textContent=inundationMapText(data);$('inundation-credit').textContent=available?`Rilievo: ${data.survey_credit} · ${data.survey_date}. ${data.license}. Quote: ${data.vertical_reference}.`:'';
  if($('inundation-downloads'))$('inundation-downloads').innerHTML=inundationDownloads(data);
  if(!available){coastMapSignature='';if(inundationMap){inundationMap.remove();inundationMap=null;}return;}
  requested=requested||readerUrl().searchParams.get('stima');const layer=selectedMapLayer(data,requested);if(!layer)return;
  const selector=$('inundation-estimate');selector.innerHTML=data.layers.map(l=>`<option value="${esc(mapLayerId(l))}">${l.kind==='mean'?'Stima media':'Stima più elevata · fascia centrale'}</option>`).join('');selector.value=mapLayerId(layer);
  selector.onchange=()=>{const url=readerUrl();url.searchParams.set('stima',selector.value);history.replaceState({},'',url);readerRenderInundation(unit,selector.value);};
  $('inundation-when').innerHTML=mapLayerTiming(layer).html;
  $('inundation-quality').textContent=layer.quality_note||(layer.exposed_at_peak===false?'Le onde di quest’ora provengono da altre direzioni: la mappa non tiene conto del riparo della costa.':'');
  $('inundation-legend').innerHTML=`<span class="map-key map-key-${layer.kind==='mean'?'mean':'central'}">${layer.kind==='mean'?'Stima media':'Stima più elevata della fascia centrale'} · quota ${num(layer.level_m)} m</span><span>Ora più intensa ${readerDay()?'del giorno selezionato':'dell’intero bollettino'}. Non è una profondità d’acqua.</span>`;
  if(!data.orthophoto&&data.terrain_scale){const scale=data.terrain_scale,colors=(scale.colors||[]).filter(c=>/^#[0-9a-f]{6}$/i.test(c));$('inundation-legend').innerHTML+=`<span class="terrain-legend">DEM · ${num(scale.min_m)}–${num(scale.max_m)} m <i style="background:linear-gradient(90deg,${colors.join(',')})"></i></span>`;}
  if($('map-day-note'))$('map-day-note').textContent=readerDay()&&!original.daily?'Questa elaborazione non contiene ancora mappe giornaliere: è mostrata la mappa dell’intero bollettino.':'La mappa media e la quota alta nel riquadro possono avere valori e orari differenti.';
  if($('inundation-permalink')){const url=readerUrl();url.searchParams.set('stima',mapLayerId(layer));url.hash='inundation-panel';$('inundation-permalink').href=url.toString();}
  const fit=()=>inundationMap?.fitBounds(data.display_bounds||data.bounds,{padding:[14,14]});
  if($('map-fit'))$('map-fit').onclick=fit;if($('map-fullscreen'))$('map-fullscreen').onclick=()=>readerFullscreen('inundation-panel','map-fullscreen');
  if(!window.L){canvas.hidden=true;return;}
  const signature=layer.image+JSON.stringify(data.bounds);if(signature===coastMapSignature&&inundationMap){const badge=$('reader-map-time');if(badge)badge.textContent=(layer.kind==='mean'?'Media':'Fascia centrale')+' · '+local(layer.peak_time);return;}
  if(inundationMap)inundationMap.remove();coastMapSignature=signature;
  inundationMap=L.map('inundation-map',{scrollWheelZoom:false});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22,maxNativeZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(inundationMap);
  const overlays={};if(data.orthophoto)overlays.Ortofoto=L.imageOverlay(data.orthophoto,data.bounds,{attribution:esc(data.survey_credit)}).addTo(inundationMap);else if(data.terrain)overlays['DEM · terreno']=L.imageOverlay(data.terrain,data.bounds,{attribution:esc(data.survey_credit)}).addTo(inundationMap);
  const water=L.layerGroup().addTo(inundationMap);L.imageOverlay(layer.image,data.bounds).addTo(water);if(layer.line_geometry)L.geoJSON(layer.line_geometry,{style:{color:'#14699b',weight:2,opacity:.9}}).addTo(water);overlays['Estensione potenziale']=water;
  if(data.sector_geometry)L.geoJSON(data.sector_geometry,{style:{color:'#294f4c',weight:1,fill:false,dashArray:'5 4'}}).addTo(inundationMap);
  if(data.structure_points?.length){const points=L.layerGroup();for(const p of data.structure_points){const t=(unit.thresholds||[]).find(t=>t.id===p.threshold_id);L.marker([p.latitude,p.longitude],{icon:L.divIcon({className:'structure-map-point',html:impactIcon(p.threshold_id),iconSize:[24,26]})}).bindPopup(`<strong>${esc(p.label)}</strong><br>Punto rilevato: ${num(p.elevation_m)} m.${t?'<br>Quota media usata nel confronto: '+num(t.elevation_m)+' m.':''}<br>Non indica che la struttura sia allagata.`).addTo(points);}overlays['Punti rilevati delle strutture']=points;}
  L.control.layers(null,overlays,{collapsed:true}).addTo(inundationMap);
  const badge=L.control({position:'bottomleft'});badge.onAdd=()=>{const div=L.DomUtil.create('div','map-time-badge reader-map-badge');div.id='reader-map-time';div.textContent=(layer.kind==='mean'?'Media':'Fascia centrale')+' · '+local(layer.peak_time);return div;};badge.addTo(inundationMap);fit();
}
function readerChartRange(hours){
  readerChartHours=Number(hours)||0;for(const button of document.querySelectorAll('[data-chart-hours]'))button.setAttribute('aria-pressed',String(Number(button.dataset.chartHours)===readerChartHours));
  if(!readerPlotRows.length||!window.Plotly?.relayout)return;
  const first=Date.parse(readerPlotRows[0].time),last=Date.parse(readerPlotRows.at(-1).time),end=readerChartHours?Math.min(last,first+readerChartHours*hourMs):last;
  const short=end-first<=25*hourMs,step=short?6:24,ticks=[];
  for(let t=first;t<=end;t+=step*hourMs)ticks.push(t);
  const labels=ticks.map((t,i)=>short?(readerSmallScreen()?(i===0||italianTime(t).slice(0,10)!==italianTime(ticks[i-1]).slice(0,10)?local(t,{hour:undefined,minute:undefined})+'<br>':'')+timeOnly(t):local(t)):local(t,{hour:undefined,minute:undefined}));
  for(const id of ['twl-chart','wave-chart'])if($(id))Plotly.relayout(id,{'xaxis.range':[first,end],'xaxis.autorange':false,'xaxis.tickvals':ticks,'xaxis.ticktext':labels,'xaxis.tickangle':0});
}
function readerPolishCharts(unit,rows){
  readerCurrentUnit=unit;readerPlotRows=rows;const keys=[...new Set(rows.map(r=>rowImpact(referenceThreshold(unit),r,unit)).map(r=>r.kind==='numeric'?['white','yellow','orange'][r.rank]:r.kind==='nonfrontal'?'gray':'unavailable'))];
  if($('twl-palette'))$('twl-palette').innerHTML='<span class="reader-mean-line">Media dei risultati</span>'+keys.map(k=>`<span class="impact-${k}"><i></i>${esc(readerImpactLabel(k))}</span>`).join('');
  readerHelp('twl-info','La linea mostra il TWL medio; le fasce centrale e più ampia contengono il 50% e il 90% dei risultati filtrati. Si confrontano quote rispetto allo zero dichiarato, non profondità d’acqua. Riferimento: '+seaLevelReference(unit).label+'.','zero');bindInfoButton('twl-info-toggle');
  if(!window.Plotly?.relayout)return;
  const mobile=readerSmallScreen(),x=rows.map(r=>Date.parse(r.time));let ticks=x.filter((v,i)=>i===0||italianTime(v).slice(11,16)==='00:00');
  if(ticks.length>5)ticks=ticks.filter((_,i)=>i%2===0);if(ticks.length<2&&x.length)ticks=[x[0],x.at(-1)];
  Plotly.relayout('twl-chart',{width:$('twl-chart').clientWidth||undefined,showlegend:false,height:mobile?390:365,margin:{l:mobile?44:55,r:18,t:16,b:mobile?52:70},font:{size:mobile?13:12,color:'#354f4b'},'yaxis.title.text':mobile?'Quota (m)':`Quota dell’acqua [m; ${seaLevelReference(unit).axis}]`,'xaxis.tickvals':ticks,'xaxis.ticktext':ticks.map(t=>local(t,mobile?{hour:undefined,minute:undefined}:{})),'xaxis.tickangle':0,'xaxis.title.text':mobile?'':'Ora italiana',dragmode:mobile?false:'zoom'});
  if(mobile)Plotly.relayout('wave-chart',{width:$('wave-chart').clientWidth||$('twl-chart').clientWidth||undefined,'xaxis.tickvals':ticks,'xaxis.ticktext':ticks.map(t=>local(t,{hour:undefined,minute:undefined})),'xaxis.tickangle':0,'xaxis.title.text':'','yaxis.title.text':'Onde (m)','yaxis2.title.text':'Periodo (s)',margin:{l:48,r:44,t:20,b:50},font:{size:13,color:'#354f4b'},dragmode:false});
  readerChartRange(readerChartHours);
}
function readerFullscreen(panelId,buttonId){
  const panel=panelId?$(panelId):null,button=buttonId?$(buttonId):null;if(!readerExpanded&&(!panel||!button))return;
  if(readerExpanded){const old=readerExpanded;old.panel.classList.remove('reader-expanded');old.panel.removeAttribute('aria-modal');old.panel.removeAttribute('role');old.button.textContent='Schermo intero';old.button.setAttribute('aria-expanded','false');document.body.style.overflow=old.overflow;readerExpanded=null;readerPreviousFocus?.focus();}
  else{readerPreviousFocus=document.activeElement;readerExpanded={panel,button,overflow:document.body.style.overflow};panel.classList.add('reader-expanded');panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-label',panel.querySelector('h2')?.textContent||'Mappa o grafico');document.body.style.overflow='hidden';button.textContent='Chiudi schermo intero';button.setAttribute('aria-expanded','true');button.focus();}
  requestAnimationFrame(()=>{inundationMap?.invalidateSize();for(const id of ['twl-chart','wave-chart'])if($(id)&&window.Plotly?.Plots){Plotly.Plots.resize($(id));if($(id).clientWidth)Plotly.relayout(id,{width:$(id).clientWidth});}});
}
function readerRenderDetail(slug){
  const parent=bulletin.locations[slug],requested=readerUrl().searchParams.get('settore'),sectorId=parent.sectors&&Object.hasOwn(parent.sectors,requested)?requested:Object.keys(parent.sectors||{})[0]||null,unit=selectedBeachUnit(parent,sectorId);
  readerRenderSectorSelector(parent,sectorId);const rows=readerViewRows(unit);
  document.title=parent.name+' · '+(unit===parent?'Onde a riva':readerShortName(unit.name));$('location-title').textContent=parent.name;$('sector-title').textContent=unit===parent?'':readerShortName(unit.name);$('area').textContent=parent.area;
  $('period').textContent=rows.length?(readerDay()?'Giornata selezionata · ':'Ore ancora future · ')+local(rows[0].time)+' → '+local(new Date(Date.parse(rows.at(-1).time)+hourMs))+' · ora italiana':'Nessun dato disponibile per questo periodo';
  const ref=seaLevelReference(unit);if($('twl-reference-label'))$('twl-reference-label').textContent=ref.label;$('sealevel-caption').innerHTML=`I grafici mostrano il livello del mare e i suoi contributi. Zero: ${esc(ref.label)}. <a href="metodo.html#zero">Riferimento delle quote ↗</a>`;
  const technical=new URL('metodo.html',window.location.href);technical.searchParams.set('localita',slug);if(sectorId)technical.searchParams.set('settore',sectorId);$('technical-link').href=technical.toString();$('download').href=unit.csv;renderSocialDownload(unit);
  if($('social-period'))$('social-period').textContent=unit.social_card?.status==='available'?`La PNG fotografa il bollettino del ${noticeDate(bulletin.generated_at)}: ${local(unit.social_card.period_from)} → ${local(unit.social_card.period_to)}. Il sito può mostrare una selezione diversa.`:'';
  setNotice(!rows.length?'Nessun dato per il periodo selezionato.':rows.some(r=>!r.n_estimates)?'Alcune ore non hanno risultati validi.':'',unit);
  readerRenderDaily(unit,rows);readerRenderMetrics(unit,rows);readerRenderInundation(unit);renderExtremes(unit,rows);renderCharts(unit,rows);
  if($('twl-fullscreen'))$('twl-fullscreen').onclick=()=>readerFullscreen('twl-panel','twl-fullscreen');if($('waves-fullscreen'))$('waves-fullscreen').onclick=()=>readerFullscreen('waves-disclosure','waves-fullscreen');
}
function readerSetup(){
  window.addEventListener('resize',()=>{clearTimeout(readerResizeTimer);readerResizeTimer=setTimeout(()=>{if(readerCurrentUnit)readerPolishCharts(readerCurrentUnit,readerPlotRows);inundationMap?.invalidateSize();coastSectorMap?.invalidateSize();},120);});
  for(const button of document.querySelectorAll('[data-chart-hours]'))button.onclick=()=>readerChartRange(button.dataset.chartHours);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&readerExpanded){event.preventDefault();readerFullscreen();}else if(event.key==='Tab'&&readerExpanded){const nodes=[...readerExpanded.panel.querySelectorAll('button,a[href],select,summary,[tabindex="0"]')].filter(n=>n.offsetParent!==null),first=nodes[0],last=nodes.at(-1);if(event.shiftKey&&document.activeElement===first){last?.focus();event.preventDefault();}else if(!event.shiftKey&&document.activeElement===last){first?.focus();event.preventDefault();}}});
  document.addEventListener('click',event=>{for(const parent of document.querySelectorAll('.metric-info'))if(!parent.contains(event.target))parent.querySelector('button')?.setAttribute('aria-expanded','false');});
  const copy=$('copy-sector-link');if(copy)copy.onclick=async()=>{try{const url=readerUrl();if(!url.searchParams.has('settore')){const select=$('beach-sector');if(select)url.searchParams.set('settore',select.value);}await navigator.clipboard.writeText(url.toString());$('copy-status').textContent='Link del settore copiato.';}catch{$('copy-status').textContent='Puoi copiare il collegamento dalla barra degli indirizzi.';}};
  const download=$('download-feedback');if(download)download.onclick=()=>{const entries=new FormData($('reader-feedback-form')),text='Onde a riva — riscontro sulla prova\n\n'+[...entries].map(([k,v])=>k+': '+v).join('\n\n');const blob=new Blob([text],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='ondeariva-riscontro.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('feedback-status').textContent='File preparato. Le risposte non sono state inviate.';};
}
